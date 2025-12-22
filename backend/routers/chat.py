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

# ========== Send Message ==========
def chat_session_id(user_id: int) -> str:
    return f"talentum_chat_user_{user_id}"


@router.post("/message", response_class=JSONResponse)
@observe()
async def send_message(
    request: Request,
    message: str = Form(...),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    langfuse = safe_langfuse_client()
    if langfuse:
        langfuse.update_current_trace(
            session_id=chat_session_id(user.id),
            tags=["chatbot", "multi-turn", "talentum"],
            metadata={
                "user_id": user.id,
                "endpoint": "/chat/message"
            }
        )

    # Save user message
    user_msg = ChatMessage(user_id=user.id, role="user", content=message)
    db.add(user_msg)
    db.commit()

    # History (you can keep this if you still use it elsewhere;
    # the NEW SDK chat is stateful in memory, not DB.
    history = db.query(ChatMessage)\
        .filter(ChatMessage.user_id == user.id)\
        .order_by(ChatMessage.created_at.asc())\
        .all()

    # CV context
    latest_cv = db.query(CV).filter(
        CV.user_id == user.id,
        CV.raw_text != None
    ).order_by(CV.updated_at.desc()).first()

    cv_text = latest_cv.raw_text if latest_cv else None

    applications = db.query(JobApplication).filter(
        JobApplication.user_id == user.id
    ).order_by(JobApplication.applied_date.desc()).all()

    # IMPORTANT: Do not put cv_text in Langfuse metadata.
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

    # --- NEW: Orchestrator call (router -> agent) ---
    ai_result = await orch.handle(
        user_id=user.id,
        user_message=message,
        user_cv_text=cv_text,
        user_context=user_context
    )

    if ai_result.get("response") and "overloaded" in ai_result["response"].lower():
        return JSONResponse({"response": ai_result["response"]}, status_code=503)

    # Tool call path
    if ai_result.get("function_call"):
        # Execute tool
        tool_payload = await handle_function_call(
            ai_result["function_call"],
            user.id,
            db,
            cv_text
        )

        # IMPORTANT: Continue with SAME AGENT session that asked for the tool
        agent_name = ai_result.get("agent_name") or "general"

        # second LLM call using tool result (function_response turn)
        final = await orch.handle(
            user_id=user.id,
            user_message="",
            user_cv_text=cv_text,
            user_context=user_context,
            tool_result={
                "name": ai_result["tool_name"],
                "response": {
                    "message": tool_payload["message"],
                    "data": tool_payload.get("data")
                }
            },
        )

        final_text = final.get("response") or tool_payload["message"]

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
            "agent": agent_name
        })

    # Normal response path
    assistant_msg = ChatMessage(
        user_id=user.id,
        role="assistant",
        content=ai_result.get("response"),
        agent_name=ai_result.get("agent_name")  # <-- add this column OR remove this line
    )
    db.add(assistant_msg)
    db.commit()

    return JSONResponse({
        "response": ai_result.get("response"),
        "agent": ai_result.get("agent_name")
    })

# ========== Handle Function Calls ==========
@observe()
async def handle_function_call(
    function_call: dict,
    user_id: int,
    db: Session,
    cv_text: str = None
) -> dict:
    """Execute the requested function and return results."""

    func_name = function_call["name"]
    args = function_call["args"]
    
    # Track application
    if func_name == "track_application":
        company = args.get("company")
        role = args.get("role")
        applied_date_str = args.get("applied_date", "today")
        job_url = args.get("job_url")
        notes = args.get("notes")
        
        # Parse date
        if applied_date_str.lower() in ["today", "now"]:
            applied_date = datetime.utcnow()
        elif applied_date_str.lower() == "yesterday":
            applied_date = datetime.utcnow() - timedelta(days=1)
        else:
            try:
                applied_date = datetime.fromisoformat(applied_date_str)
            except:
                applied_date = datetime.utcnow()
        
        # Create application
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
                "message": "You haven't tracked any applications yet. Apply to a job and let me know so I can help you track it!",
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
                {
                    "id": app.id,
                    "company": app.company,
                    "role": app.role,
                    "status": app.status
                } for app in apps
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
            return {"message": "I couldn't find that application. Can you tell me which company it was for?"}
        
        app.status = new_status
        app.updated_at = datetime.utcnow()
        db.commit()
        
        status_messages = {
            "interview": f"🎉 Congrats on getting an interview at {app.company}! Want some tips for preparing?",
            "rejected": f"Sorry to hear about {app.company}. Remember, every 'no' gets you closer to a 'yes'. Want to review what went well?",
            "offer": f"🎊 Amazing news on the offer from {app.company}! Need help negotiating or evaluating it?",
            "accepted": f"🚀 Congratulations on accepting the offer at {app.company}! Wishing you success in your new role!"
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
            "message": f"✓ Reminder set! I'll remind you to follow up with {app.company} on {app.follow_up_date.strftime('%B %d, %Y')}.",
            "data": {"follow_up_date": app.follow_up_date.isoformat()}
        }
    
    # Generate cover letter
    elif func_name == "generate_cover_letter":
        if not cv_text:
            return {"message": "I need your CV to generate a cover letter. Please upload your CV first in the CV Upload tab!"}
        
        job_desc = args.get("job_description")
        tone = args.get("tone", "professional")
        
        cover_letter = await generate_cover_letter_content(cv_text, job_desc, tone)
        
        return {
            "message": f"Here's a draft cover letter:\n\n{cover_letter}\n\nFeel free to adjust it to match your voice!",
            "data": {"cover_letter": cover_letter}
        }
    
    # Generate LinkedIn summary
    elif func_name == "generate_linkedin_summary":
        if not cv_text:
            return {"message": "I need your CV to generate a LinkedIn summary. Please upload your CV first!"}
        
        focus = args.get("focus")
        
        summary = await generate_linkedin_summary_content(cv_text, focus)
        
        return {
            "message": f"Here's a LinkedIn summary for you:\n\n{summary}\n\nTweak it to sound like you!",
            "data": {"linkedin_summary": summary}
        }
    
    # Web search (placeholder - you'll need to implement actual web search)
    elif func_name == "web_search":
        query = args.get("query")
        return {
            "message": f"I would search for '{query}', but web search isn't fully implemented yet. However, I can still answer many questions about job searching, interviews, and career advice! What would you like to know?",
            "data": {"query": query}
        }
    
    return {"message": "I'm not sure how to help with that yet. Can you rephrase?"}


# ========== Get Chat History ==========
@router.get("/history", response_class=JSONResponse)
async def get_history(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get chat history for current user."""
    
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    messages = db.query(ChatMessage).filter(
        ChatMessage.user_id == user.id
    ).order_by(ChatMessage.created_at.asc()).all()
    
    return JSONResponse({
        "messages": [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.created_at.isoformat()
            }
            for msg in messages
        ]
    })


# ========== Clear Chat ==========
@router.post("/clear", response_class=JSONResponse)
async def clear_chat(
    request: Request,
    db: Session = Depends(get_db)
):
    """Clear chat history for current user."""
    
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    
    db.query(ChatMessage).filter(ChatMessage.user_id == user.id).delete()
    db.commit()
    
    return JSONResponse({"message": "Chat cleared successfully"})