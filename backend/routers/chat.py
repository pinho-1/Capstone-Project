from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from langfuse import observe, get_client

from backend.database import get_db
from backend.routers.auth import get_current_user
from backend.models.chat_model import ChatMessage, JobApplication
from backend.services.ai.chatbot_service import orch
from backend.models.cv_model import CV

from datetime import datetime, timedelta
import os
import uuid

router = APIRouter(tags=["chat"])

FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "../frontend/pages"
)
templates = Jinja2Templates(directory=FRONTEND_DIR)

def safe_langfuse_client():
    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        return get_client()
    return None

# ========== Guest helpers ==========
def get_guest_id(request: Request) -> str:
    """
    Stable per-browser-session guest id. Requires SessionMiddleware.
    """
    if "guest_id" not in request.session:
        request.session["guest_id"] = f"guest_{uuid.uuid4().hex}"
    return request.session["guest_id"]

def stable_guest_int_id(guest_id: str) -> int:
    """
    Orchestrator expects int user_id for session keys.
    This creates a stable-ish int for current guest session.
    """
    return abs(hash(guest_id)) % (10**9)

# ========== Send Message ==========
def chat_session_id(actor_id: str) -> str:
    return f"talentum_chat_{actor_id}"

@router.post("/message", response_class=JSONResponse)
@observe()
async def send_message(
    request: Request,
    message: str = Form(...),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    is_guest = user is None

    # Identify actor (user.id or guest session id)
    if is_guest:
        guest_id = get_guest_id(request)
        actor_id = guest_id
        orch_user_id = stable_guest_int_id(guest_id)
    else:
        actor_id = str(user.id)
        orch_user_id = user.id

    # Langfuse (safe metadata)
    langfuse = safe_langfuse_client()
    if langfuse:
        langfuse.update_current_trace(
            session_id=chat_session_id(actor_id),
            tags=["chatbot", "multi-turn", "talentum", "guest" if is_guest else "user"],
            metadata={
                "actor": "guest" if is_guest else "user",
                "endpoint": "/chat/message",
            }
        )

    # -----------------------------
    # Context building
    # -----------------------------
    cv_text = None
    user_context = {"guest": True} if is_guest else {}

    if not is_guest:
        # Save user message (logged-in only)
        user_msg = ChatMessage(user_id=user.id, role="user", content=message)
        db.add(user_msg)
        db.commit()

        # CV context
        latest_cv = db.query(CV).filter(
            CV.user_id == user.id,
            CV.raw_text != None
        ).order_by(CV.updated_at.desc()).first()

        cv_text = latest_cv.raw_text if latest_cv else None

        # Applications context
        applications = db.query(JobApplication).filter(
            JobApplication.user_id == user.id
        ).order_by(JobApplication.applied_date.desc()).all()

        user_context = {
            "name": user.name,
            "onboarding": {
                "career_stage": user.career_stage,
                "interest": user.interest,
                "goal": user.goal,
                "experience_years": user.experience,
                "focus": user.focus,
                "onboarding_complete": user.onboarding_complete
            },
            "apps": {
                "total": len(applications),
                "recent": [{"id": a.id, "company": a.company, "role": a.role, "status": a.status} for a in applications[:3]]
            },
            "cv_meta": {
                "has_cv": cv_text is not None,
                "scores": {
                    "overall": latest_cv.overall_score if latest_cv else None
                } if latest_cv else None
            }
        }
    else:
        # Guest: no private context, no cv_text
        user_context = {
            "name": "Guest",
            "guest": True,
            "limits": {
                "applications_tracking": "requires_login",
                "cv_personalization": "requires_login",
                "history_saving": "disabled"
            }
        }

    # -----------------------------
    # Orchestrator call
    # -----------------------------
    ai_result = await orch.handle(
        user_id=orch_user_id,
        user_message=message,
        user_cv_text=cv_text,         # None for guests
        user_context=user_context
    )

    if ai_result.get("response") and "overloaded" in ai_result["response"].lower():
        return JSONResponse({"response": ai_result["response"]}, status_code=503)

    # -----------------------------
    # Tool call path
    # -----------------------------
    if ai_result.get("function_call"):
        tool_payload = await handle_function_call(
            function_call=ai_result["function_call"],
            user=user,
            is_guest=is_guest,
            db=db,
            cv_text=cv_text
        )

        agent_name = ai_result.get("agent_name") or "general"

        final = await orch.handle(
            user_id=orch_user_id,
            user_message="IGNORED",
            user_cv_text=cv_text,
            user_context=user_context,
            tool_result={
                "name": ai_result["tool_name"],
                "response": {
                    "message": tool_payload["message"],
                    "data": tool_payload.get("data")
                }
            },
            forced_agent=ai_result.get("agent_name")
        )

        final_text = final.get("response") or tool_payload["message"]

        # Save assistant msg only if logged-in
        if not is_guest:
            assistant_msg = ChatMessage(
                user_id=user.id,
                role="assistant",
                content=final_text,
                function_call=ai_result["function_call"],
                agent_name=agent_name
            )
            db.add(assistant_msg)
            db.commit()

        return JSONResponse({
            "response": final_text,
            "function_used": ai_result.get("tool_name"),
            "agent": agent_name,
            "guest": is_guest,
            "requires_login": bool(tool_payload.get("data", {}).get("requires_login")),
        })

    # -----------------------------
    # Normal response path
    # -----------------------------
    if not is_guest:
        assistant_msg = ChatMessage(
            user_id=user.id,
            role="assistant",
            content=ai_result.get("response"),
            agent_name=ai_result.get("agent_name")
        )
        db.add(assistant_msg)
        db.commit()

    return JSONResponse({
        "response": ai_result.get("response"),
        "agent": ai_result.get("agent_name"),
        "guest": is_guest
    })


# ========== Handle Function Calls ==========
@observe()
async def handle_function_call(
    function_call: dict,
    user,
    is_guest: bool,
    db: Session,
    cv_text: str = None
) -> dict:
    """Execute the requested function and return results."""
    func_name = function_call["name"]
    args = function_call["args"]

    # Guest gating for DB + personal tools
    LOGIN_REQUIRED_TOOLS = {
        "track_application",
        "list_applications",
        "update_application_status",
        "set_follow_up_reminder",
    }

    if is_guest and func_name in LOGIN_REQUIRED_TOOLS:
        return {
            "message": "Guest Mode: tracking applications needs an account so I can save your data. Log in to unlock it.",
            "data": {"requires_login": True, "tool": func_name}
        }

    # Web search fallback
    if func_name == "web_search":
        query = args.get("query")
        return {
            "message": f"Web search isn't implemented yet, but I can still give general guidance. What specifically do you want to know about: {query}?",
            "data": {"query": query}
        }

    # From here down, user must exist
    if not user:
        return {
            "message": "You need to be logged in for this feature.",
            "data": {"requires_login": True, "tool": func_name}
        }

    user_id = user.id

    # Track application
    if func_name == "track_application":
        company = args.get("company")
        role = args.get("role")
        applied_date_str = args.get("applied_date", "today")
        job_url = args.get("job_url")
        notes = args.get("notes")

        # Parse date
        if applied_date_str and applied_date_str.lower() in ["today", "now"]:
            applied_date = datetime.utcnow()
        elif applied_date_str and applied_date_str.lower() == "yesterday":
            applied_date = datetime.utcnow() - timedelta(days=1)
        else:
            try:
                applied_date = datetime.fromisoformat(applied_date_str)
            except:
                applied_date = datetime.utcnow()

        app = JobApplication(
            user_id=user_id,
            company=company,
            role=role,
            applied_date=applied_date,
            job_url=job_url,
            notes=notes
        )
        db.add(app)
        db.commit()
        db.refresh(app)

        return {
            "message": f"✓ Tracked your application to {company} for {role}! I recommend following up in 2 weeks. Want me to set a reminder?",
            "data": {"application_id": app.id}
        }

    # List applications
    elif func_name == "list_applications":
        apps = db.query(JobApplication).filter(
            JobApplication.user_id == user_id
        ).order_by(JobApplication.applied_date.desc()).all()

        if not apps:
            return {
                "message": "You haven't tracked any applications yet. Apply to a job and tell me the company + role so I can track it.",
                "data": {"applications": []}
            }

        app_list = []
        for app in apps:
            status_emoji = {
                "applied": "📤",
                "interview": "📞",
                "rejected": "❌",
                "offer": "🎉",
                "accepted": "✅"
            }.get(app.status, "📄")

            app_list.append(
                f"{status_emoji} {app.company} - {app.role} ({app.status}) - Applied: {app.applied_date.strftime('%b %d, %Y')}"
            )

        message = "Here are your tracked applications:\n\n" + "\n".join(app_list)
        message += "\n\nNeed help with any of these?"

        return {
            "message": message,
            "data": {"applications": [
                {"id": app.id, "company": app.company, "role": app.role, "status": app.status}
                for app in apps
            ]}
        }

    # Update status
    elif func_name == "update_application_status":
        app_id = args.get("application_id")
        new_status = args.get("new_status")

        app = db.query(JobApplication).filter(
            JobApplication.id == app_id,
            JobApplication.user_id == user_id
        ).first()

        if not app:
            return {"message": "I couldn't find that application. Tell me the company name and I’ll locate it."}

        app.status = new_status
        app.updated_at = datetime.utcnow()
        db.commit()

        status_messages = {
            "interview": f"🎉 Congrats on getting an interview at {app.company}! Want some prep questions?",
            "rejected": f"Sorry about {app.company}. Want me to help you improve the next application?",
            "offer": f"🎊 Offer from {app.company}! Want help evaluating or negotiating?",
            "accepted": f"🚀 Congrats on accepting at {app.company}! Want help planning your first 30 days?"
        }

        message = status_messages.get(new_status, f"Updated {app.company} application status to {new_status}.")
        return {"message": message, "data": {"application_id": app.id}}

    # Set reminder
    elif func_name == "set_follow_up_reminder":
        app_id = args.get("application_id")
        days = args.get("days_from_now", 14)

        app = db.query(JobApplication).filter(
            JobApplication.id == app_id,
            JobApplication.user_id == user_id
        ).first()

        if not app:
            return {"message": "I couldn't find that application."}

        app.follow_up_date = datetime.utcnow() + timedelta(days=days)
        db.commit()

        return {
            "message": f"✓ Reminder set! Follow up with {app.company} on {app.follow_up_date.strftime('%B %d, %Y')}.",
            "data": {"follow_up_date": app.follow_up_date.isoformat()}
        }

    # If model calls a tool removed or don’t support
    return {"message": "That tool isn’t available. Try rephrasing your request."}


# ========== Get Chat History ==========
@router.get("/history", response_class=JSONResponse)
async def get_history(
    request: Request,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        # Guest: return empty history so frontend works
        return JSONResponse({"messages": [], "guest": True})

    messages = db.query(ChatMessage).filter(
        ChatMessage.user_id == user.id
    ).order_by(ChatMessage.created_at.asc()).all()

    return JSONResponse({
        "guest": False,
        "messages": [
            {"role": msg.role, "content": msg.content, "timestamp": msg.created_at.isoformat()}
            for msg in messages
        ]
    })


# ========== Clear Chat ==========
@router.post("/clear", response_class=JSONResponse)
async def clear_chat(
    request: Request,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        # Guest: nothing to clear
        return JSONResponse({"message": "Guest mode: nothing to clear.", "guest": True})

    db.query(ChatMessage).filter(ChatMessage.user_id == user.id).delete()
    db.commit()

    return JSONResponse({"message": "Chat cleared successfully", "guest": False})
