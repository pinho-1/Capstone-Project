from __future__ import annotations

from typing import Any, Dict, List

from langfuse import observe

from backend.services.ai.gemini_client import generate_json


def _language_name(lang: str) -> str:
    return "Portuguese" if (lang or "").lower().startswith("pt") else "English"


def _turn_instruction(turn_index: int, total_turns: int, lang: str) -> str:
    if turn_index < total_turns:
        return (
            "Write ONE recruiter message. It must be a natural follow-up question based on the user's last answer "
            "and the role/seniority. Do NOT include numbered questions like Q2/5. Do NOT end the interview."
        )

    return (
        "Write ONE final recruiter message that politely concludes the interview. "
        "Do NOT include a score here (score is computed separately)."
    )


def _safe_str(x: Any) -> str:
    return str(x or "").strip()


def _safe_bool(x: Any) -> bool:
    return bool(x) if isinstance(x, (bool, int)) else str(x).strip().lower() in {"true", "1", "yes"}


@observe()
async def generate_interview_reply(
    role: str,
    seniority: str,
    language: str,
    total_turns: int,
    turn_index: int,
    history: List[Dict[str, str]],
    user_message: str,
) -> Dict[str, Any]:
    sys = f"""
You are a strict mock-interview recruiter for the role: {role} (seniority: {seniority}).
Language: {_language_name(language)}.

Rules:
- Output MUST be valid JSON.
- Schema: {{ "reply": string, "done": boolean }}
- "reply" must be ONE message only.
- Never output multiple questions numbered like Q1/5, Q2/5, etc.
- No long lectures, keep it interview-realistic.
- Be consistent with the user's last answer and the role.
"""

    payload = {
        "instruction": _turn_instruction(turn_index, total_turns, language),
        "turn_index": int(turn_index),
        "total_turns": int(total_turns),
        "history": history[-12:],
        "last_user_message": user_message,
    }

    out = await generate_json(sys, payload, temperature=0.4)

    reply = _safe_str(out.get("reply")) if isinstance(out, dict) else ""
    done = _safe_bool(out.get("done")) if isinstance(out, dict) else False

    if not reply:
        reply = "Thanks. Could you expand on that with a concrete example?"
        done = False

    if int(turn_index) >= int(total_turns):
        done = True

    return {"reply": reply, "done": done}


@observe()
async def evaluate_interview(
    role: str,
    seniority: str,
    language: str,
    history: List[Dict[str, str]],
) -> Dict[str, Any]:
    sys = f"""
You are evaluating a mock interview for role: {role} (seniority: {seniority}).
Language of feedback: {_language_name(language)}.

Rules:
- Output MUST be valid JSON.
- Schema: {{
    "final_score": integer (0..100),
    "feedback": array of 4 to 6 concise bullet strings
  }}
- Score should reflect clarity, relevance, specificity, structure, and role fit.
- Do NOT be overly generous.
"""

    payload = {
        "history": history,
        "rubric": ["clarity", "relevance", "specificity", "structure", "role_fit"],
    }

    out = await generate_json(sys, payload, temperature=0.2)

    score = None
    feedback = None

    if isinstance(out, dict):
        score = out.get("final_score")
        feedback = out.get("feedback")

    try:
        score = int(score)
    except Exception:
        score = 70

    score = max(0, min(100, score))

    if not isinstance(feedback, list):
        feedback = []

    feedback = [str(x).strip() for x in feedback if str(x).strip()]

    if len(feedback) < 4:
        feedback = [
            "Good baseline, but increase specificity with concrete examples.",
            "Use a clearer structure (Situation, Task, Action, Result).",
            "Tie each answer directly to the role’s responsibilities.",
            "Quantify impact when possible (time saved, revenue, accuracy, scale).",
        ]
    feedback = feedback[:6]

    return {"final_score": score, "feedback": feedback}