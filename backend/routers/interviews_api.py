# backend/routers/interviews.py

import os
import time
import uuid
from typing import Dict, Any, List, Tuple

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from langfuse import observe, get_client

from backend.database import get_db
from backend.routers.auth import get_current_user
from backend.services.ai.interviews_agent import generate_interview_reply, evaluate_interview

router = APIRouter(tags=["interviews"])

FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "../frontend/pages",
)
templates = Jinja2Templates(directory=FRONTEND_DIR)

# -----------------------------
# Observability helper
# -----------------------------

def safe_langfuse_client():
    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        return get_client()
    return None


def interview_trace_session_id(user_id: int, session_id: str) -> str:
    return f"talentum_interview_{user_id}_{session_id}"


# -----------------------------
# In-memory store (bounded)
# NOTE: process-local; resets on redeploy.
# -----------------------------

_STORE: Dict[Tuple[int, str], Dict[str, Any]] = {}
_STORE_ORDER: List[Tuple[int, str]] = []
_STORE_MAX = 300


def _store_get(key: Tuple[int, str]) -> Dict[str, Any] | None:
    return _STORE.get(key)


def _store_set(key: Tuple[int, str], value: Dict[str, Any]) -> None:
    if key in _STORE:
        _STORE[key] = value
        return

    _STORE[key] = value
    _STORE_ORDER.append(key)

    if len(_STORE_ORDER) > _STORE_MAX:
        old = _STORE_ORDER.pop(0)
        _STORE.pop(old, None)


def _get_state(user_id: int, session_id: str, total_turns: int) -> Dict[str, Any]:
    key = (user_id, session_id)
    st = _store_get(key)
    if not st:
        st = {
            "history": [],
            "turn_index": 1,
            "total_turns": int(total_turns),
            "done": False,
            "final_score": None,
            "feedback": [],
        }
        _store_set(key, st)

    st["total_turns"] = int(total_turns)
    return st


# -----------------------------
# API: message
# -----------------------------

@router.post("/interviews/api/message")
@observe()
async def interviews_message(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "login_required"}, status_code=401)

    data = await request.json()

    session_id = (data.get("session_id") or "").strip()
    role = (data.get("role") or "the role").strip()
    seniority = (data.get("seniority") or "mid").strip()
    language = (data.get("language") or "en").strip()
    total_turns = int(data.get("total_questions") or 5)
    user_message = (data.get("message") or "").strip()

    if not session_id or not user_message:
        return JSONResponse({"error": "missing session_id or message"}, status_code=400)

    state = _get_state(user.id, session_id, total_turns)

    langfuse = safe_langfuse_client()
    if langfuse:
        langfuse.update_current_trace(
            session_id=interview_trace_session_id(user.id, session_id),
            tags=["interviews", "mock_interview"],
            metadata={
                "endpoint": "/interviews/api/message",
                "user_id": user.id,
                "session_id": session_id,
                "role": role,
                "seniority": seniority,
                "language": language,
                "total_turns": total_turns,
                "turn_index": state.get("turn_index"),
            },
        )

    if state["done"]:
        return {
            "reply": "Interview already completed.",
            "done": True,
            "final_score": state["final_score"],
            "feedback": state["feedback"],
        }

    state["history"].append({"role": "user", "content": user_message})

    if state["turn_index"] > state["total_turns"]:
        t0 = time.time()
        evaluation = await evaluate_interview(role, seniority, language, state["history"])
        if langfuse:
            langfuse.update_current_trace(
                session_id=interview_trace_session_id(user.id, session_id),
                metadata={"evaluation_latency_ms": int((time.time() - t0) * 1000)},
            )

        state["done"] = True
        state["final_score"] = evaluation["final_score"]
        state["feedback"] = evaluation["feedback"]

        return {
            "reply": "Thanks — that concludes the interview.",
            "done": True,
            "final_score": state["final_score"],
            "feedback": state["feedback"],
        }

    t0 = time.time()
    ai = await generate_interview_reply(
        role=role,
        seniority=seniority,
        language=language,
        total_turns=state["total_turns"],
        turn_index=state["turn_index"],
        history=state["history"],
        user_message=user_message,
    )
    gen_ms = int((time.time() - t0) * 1000)

    reply = (ai.get("reply") or "...").strip()
    done = bool(ai.get("done", False))

    state["history"].append({"role": "assistant", "content": reply})

    if done or state["turn_index"] >= state["total_turns"]:
        t1 = time.time()
        evaluation = await evaluate_interview(role, seniority, language, state["history"])
        eval_ms = int((time.time() - t1) * 1000)

        state["done"] = True
        state["final_score"] = evaluation["final_score"]
        state["feedback"] = evaluation["feedback"]

        if langfuse:
            langfuse.update_current_trace(
                session_id=interview_trace_session_id(user.id, session_id),
                metadata={
                    "gen_latency_ms": gen_ms,
                    "evaluation_latency_ms": eval_ms,
                    "final_score": state["final_score"],
                    "done": True,
                },
            )
    else:
        state["turn_index"] += 1
        if langfuse:
            langfuse.update_current_trace(
                session_id=interview_trace_session_id(user.id, session_id),
                metadata={"gen_latency_ms": gen_ms, "done": False},
            )

    return {
        "reply": reply,
        "done": state["done"],
        "final_score": state["final_score"],
        "feedback": state["feedback"],
        "current_question": state["turn_index"],
    }


# -----------------------------
# Page: create interview session
# -----------------------------

@router.post("/interviews/session", response_class=HTMLResponse)
@observe()
async def interviews_session_page(
    request: Request,
    db: Session = Depends(get_db),
    job_role: str = Form(...),
    seniority: str = Form(...),
    language: str = Form(...),
    question_count: int = Form(...),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth?error=login_required", status_code=303)

    session_id = str(uuid.uuid4())

    _get_state(user.id, session_id, int(question_count))

    langfuse = safe_langfuse_client()
    if langfuse:
        langfuse.update_current_trace(
            session_id=interview_trace_session_id(user.id, session_id),
            tags=["interviews", "start_session"],
            metadata={
                "endpoint": "/interviews/session",
                "user_id": user.id,
                "session_id": session_id,
                "role": job_role,
                "seniority": seniority,
                "language": language,
                "question_count": int(question_count),
            },
        )

    return templates.TemplateResponse(
        "interviews_session.html",
        {
            "request": request,
            "user": user,
            "current_path": request.url.path,
            "role": job_role,
            "seniority": seniority,
            "language": language,
            "question_count": int(question_count),
            "session_id": session_id,
        },
    )
