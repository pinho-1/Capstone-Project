# backend/routers/interviews_api.py
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.routers.auth import get_current_user
from backend.services.ai.interviews_agent import generate_interview_reply, evaluate_interview

router = APIRouter()

_STORE = {}

def _get_state(session_id: str, total_turns: int):
    st = _STORE.setdefault(session_id, {
        "history": [],
        "turn_index": 1,          # next recruiter turn to generate (1..total_turns)
        "total_turns": total_turns,
        "done": False,
        "final_score": None,
        "feedback": []
    })
    st["total_turns"] = total_turns
    return st


@router.post("/interviews/api/message")
async def interviews_message(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "login_required"}, status_code=401)

    data = await request.json()

    session_id = (data.get("session_id") or "").strip()
    role = data.get("role") or "the role"
    seniority = data.get("seniority") or "mid"
    language = data.get("language", "en")
    total_turns = int(data.get("total_questions", 5))
    user_message = (data.get("message") or "").strip()

    if not session_id or not user_message:
        return JSONResponse({"error": "missing session_id or message"}, status_code=400)

    state = _get_state(session_id, total_turns)

    # If already done, just return final payload
    if state["done"]:
        return {
            "reply": "Interview already completed.",
            "done": True,
            "final_score": state["final_score"],
            "feedback": state["feedback"],
        }

    # Save user message
    state["history"].append({"role": "user", "content": user_message})

    # Hard stop guard (should not happen often)
    if state["turn_index"] > state["total_turns"]:
        # evaluate with LLM instead of fixed 75
        evaluation = await evaluate_interview(role, seniority, language, state["history"])
        state["done"] = True
        state["final_score"] = evaluation["final_score"]
        state["feedback"] = evaluation["feedback"]
        return {
            "reply": "Thanks — that concludes the interview.",
            "done": True,
            "final_score": state["final_score"],
            "feedback": state["feedback"],
        }

    # Generate recruiter reply for this turn
    ai = await generate_interview_reply(
        role=role,
        seniority=seniority,
        language=language,
        total_turns=state["total_turns"],
        turn_index=state["turn_index"],
        history=state["history"],
        user_message=user_message,
    )

    reply = (ai.get("reply") or "...").strip()
    done = bool(ai.get("done", False))

    # Store assistant message
    state["history"].append({"role": "assistant", "content": reply})

    if done or state["turn_index"] >= state["total_turns"]:
        evaluation = await evaluate_interview(role, seniority, language, state["history"])
        state["done"] = True
        state["final_score"] = evaluation["final_score"]
        state["feedback"] = evaluation["feedback"]
    else:
        state["turn_index"] += 1

    return {
        "reply": reply,
        "done": state["done"],
        "final_score": state["final_score"],
        "feedback": state["feedback"],
        "current_question": state["turn_index"],  # optional, helps your JS sync
    }
