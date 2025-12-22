import os
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from langfuse import observe, get_client

from backend.database import get_db
from backend.routers.auth import get_current_user
from backend.models.chat_model import ChatMessage, JobApplication
from backend.models.cv_model import CV
from backend.services.ai.chatbot_service import orch


router = APIRouter(tags=["chat"])


# -----------------------------
# Langfuse helpers
# -----------------------------

def safe_langfuse_client():
    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        return get_client()
    return None


# -----------------------------
# Guest session helpers
# -----------------------------

def get_guest_id(request: Request) -> str:
    if "guest_id" not in request.session:
        request.session["guest_id"] = f"guest_{uuid.uuid4().hex}"
    return request.session["guest_id"]


def stable_guest_int_id(guest_id: str) -> int:
    return abs(hash(guest_id)) % (10**9)


def chat_session_id(actor_id: str) -> str:
    return f"talentum_chat_{actor_id}"


# -----------------------------
# Send chat message
# -----------------------------

@router.post("/message", response_class=JSONResponse)
@observe()
async def send_message(
    request: Request,
    message: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_guest = user is None

    if is_guest:
        guest_id = get_guest_id(request)
        actor_id = guest_id
        orch_user_id = stable_guest_int_id(guest_id)
    else:
        actor_id = str(user.id)
        orch_user_id = user.id

    langfuse = safe_langfuse_client()
    if langfuse:
        langfuse.update_current_trace(
            session_id=chat_session_id(actor_id),
            tags=["chatbot", "multi-turn", "talentum", "guest" if is_guest else "user"],
            metadata={"actor": "guest" if is_guest else "user"},
        )

    # -----------------------------
    # Context building
    # -----------------------------

    cv_text = None
    user_context = {}

    if not is_guest:
        db.add(ChatMessage(user_id=user.id, role="user", content=message))
        db.commit()

        latest_cv = (
            db.query(CV)
            .filter(CV.user_id == user.id, CV.raw_text != None)  # noqa: E711
            .order_by(CV.updated_at.desc())
            .first()
        )
        cv_text = latest_cv.raw_text if latest_cv else None

        applications = (
            db.query(JobApplication)
            .filter(JobApplication.user_id == user.id)
            .order_by(JobApplication.applied_date.desc())
            .all()
        )

        user_context = {
            "name": user.name,
            "onboarding": {
                "career_stage": user.career_stage,
                "interest": user.interest,
                "goal": user.goal,
                "experience_years": user.experience,
                "focus": user.focus,
                "onboarding_complete": user.onboarding_complete,
            },
            "apps": {
                "total": len(applications),
                "recent": [
                    {"id": a.id, "company": a.company, "role": a.role, "status": a.status}
                    for a in applications[:3]
                ],
            },
            "cv_meta": {
                "has_cv": cv_text is not None,
                "scores": {"overall": latest_cv.overall_score} if latest_cv else None,
            },
        }
    else:
        user_context = {
            "name": "Guest",
            "guest": True,
            "limits": {
                "applications_tracking": "requires_login",
                "cv_personalization": "requires_login",
                "history_saving": "disabled",
            },
        }

    # -----------------------------
    # Orchestrator call
    # -----------------------------

    ai_result = await orch.handle(
        user_id=orch_user_id,
        user_message=message,
        user_cv_text=cv_text,
        user_context=user_context,
    )

    # -----------------------------
    # Tool execution path
    # -----------------------------

    if ai_result.get("function_call"):
        tool_payload = await handle_function_call(
            function_call=ai_result["function_call"],
            user=user,
            is_guest=is_guest,
            db=db,
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
                    "data": tool_payload.get("data"),
                },
            },
            forced_agent=agent_name,
        )

        final_text = final.get("response") or tool_payload["message"]

        if not is_guest:
            db.add(
                ChatMessage(
                    user_id=user.id,
                    role="assistant",
                    content=final_text,
                    function_call=ai_result["function_call"],
                    agent_name=agent_name,
                )
            )
            db.commit()

        return JSONResponse(
            {
                "response": final_text,
                "agent": agent_name,
                "guest": is_guest,
                "requires_login": bool(tool_payload.get("data", {}).get("requires_login")),
            }
        )

    # -----------------------------
    # Normal response path
    # -----------------------------

    if not is_guest:
        db.add(
            ChatMessage(
                user_id=user.id,
                role="assistant",
                content=ai_result.get("response"),
                agent_name=ai_result.get("agent_name"),
            )
        )
        db.commit()

    return JSONResponse(
        {
            "response": ai_result.get("response"),
            "agent": ai_result.get("agent_name"),
            "guest": is_guest,
        }
    )


# -----------------------------
# Function call handler
# -----------------------------

@observe()
async def handle_function_call(
    function_call: dict,
    user,
    is_guest: bool,
    db: Session,
) -> dict:
    func_name = function_call["name"]
    args = function_call.get("args") or {}

    login_required_tools = {
        "track_application",
        "list_applications",
        "update_application_status",
        "set_follow_up_reminder",
    }

    if is_guest and func_name in login_required_tools:
        return {
            "message": "Guest Mode: tracking applications needs an account so I can save your data.",
            "data": {"requires_login": True},
        }

    if not user:
        return {"message": "You need to be logged in for this feature."}

    user_id = user.id

    if func_name == "track_application":
        applied_date_str = args.get("applied_date", "today")

        if str(applied_date_str).lower() == "yesterday":
            applied_date = datetime.utcnow() - timedelta(days=1)
        elif str(applied_date_str).lower() in {"today", "now"}:
            applied_date = datetime.utcnow()
        else:
            try:
                applied_date = datetime.fromisoformat(str(applied_date_str))
            except Exception:
                applied_date = datetime.utcnow()

        app = JobApplication(
            user_id=user_id,
            company=args.get("company"),
            role=args.get("role"),
            applied_date=applied_date,
            job_url=args.get("job_url"),
            notes=args.get("notes"),
        )
        db.add(app)
        db.commit()
        db.refresh(app)

        return {
            "message": f"✓ Tracked your application to {app.company} for {app.role}.",
            "data": {"application_id": app.id},
        }

    if func_name == "list_applications":
        apps = (
            db.query(JobApplication)
            .filter(JobApplication.user_id == user_id)
            .order_by(JobApplication.applied_date.desc())
            .all()
        )

        if not apps:
            return {"message": "You haven't tracked any applications yet."}

        lines = [
            f"{app.company} - {app.role} ({app.status})"
            for app in apps
        ]

        return {
            "message": "Here are your tracked applications:\n\n" + "\n".join(lines),
            "data": {"applications": [{"id": a.id} for a in apps]},
        }

    if func_name == "update_application_status":
        app = (
            db.query(JobApplication)
            .filter(
                JobApplication.id == args.get("application_id"),
                JobApplication.user_id == user_id,
            )
            .first()
        )

        if not app:
            return {"message": "I couldn't find that application."}

        app.status = args.get("new_status")
        app.updated_at = datetime.utcnow()
        db.commit()

        return {"message": f"Updated {app.company} to {app.status}."}

    if func_name == "set_follow_up_reminder":
        app = (
            db.query(JobApplication)
            .filter(
                JobApplication.id == args.get("application_id"),
                JobApplication.user_id == user_id,
            )
            .first()
        )

        if not app:
            return {"message": "I couldn't find that application."}

        days = int(args.get("days_from_now", 14))
        app.follow_up_date = datetime.utcnow() + timedelta(days=days)
        db.commit()

        return {
            "message": f"Reminder set for {app.follow_up_date.strftime('%B %d, %Y')}.",
            "data": {"follow_up_date": app.follow_up_date.isoformat()},
        }

    return {"message": "That tool isn’t available."}


# -----------------------------
# Chat history
# -----------------------------

@router.get("/history", response_class=JSONResponse)
async def get_history(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"messages": [], "guest": True})

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )

    return JSONResponse(
        {
            "guest": False,
            "messages": [
                {"role": m.role, "content": m.content, "timestamp": m.created_at.isoformat()}
                for m in messages
            ],
        }
    )


# -----------------------------
# Clear chat
# -----------------------------

@router.post("/clear", response_class=JSONResponse)
async def clear_chat(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"guest": True})

    db.query(ChatMessage).filter(ChatMessage.user_id == user.id).delete()
    db.commit()

    return JSONResponse({"guest": False})