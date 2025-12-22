# backend/services/ai/interviews_agent.py
from __future__ import annotations

from typing import Any, Dict, List

from backend.services.ai.gemini_client import generate_json


def _language_name(lang: str) -> str:
    return "Portuguese" if (lang or "").lower().startswith("pt") else "English"


def _turn_instruction(turn_index: int, total_turns: int, lang: str) -> str:
    # We want: ONE recruiter reply per user message.
    # For turn < total: ask a follow-up and continue.
    # For final turn: close interview and ask for final evaluation (but we’ll evaluate in a separate call).
    if turn_index < total_turns:
        if _language_name(lang) == "Portuguese":
            return (
                "Write ONE recruiter message. It must be a natural follow-up question based on the user's last answer "
                "and the role/seniority. Do NOT include numbered questions like Q2/5. Do NOT end the interview."
            )
        return (
            "Write ONE recruiter message. It must be a natural follow-up question based on the user's last answer "
            "and the role/seniority. Do NOT include numbered questions like Q2/5. Do NOT end the interview."
        )

    # last turn
    if _language_name(lang) == "Portuguese":
        return (
            "Write ONE final recruiter message that politely concludes the interview. "
            "Do NOT include a score here (score is computed separately)."
        )
    return (
        "Write ONE final recruiter message that politely concludes the interview. "
        "Do NOT include a score here (score is computed separately)."
    )


async def generate_interview_reply(
    role: str,
    seniority: str,
    language: str,
    total_turns: int,
    turn_index: int,
    history: List[Dict[str, str]],
    user_message: str,
) -> Dict[str, Any]:
    """
    Returns JSON:
      {
        "reply": "...",
        "done": bool
      }
    """
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

    instruction = _turn_instruction(turn_index, total_turns, language)

    payload = {
        "instruction": instruction,
        "turn_index": turn_index,
        "total_turns": total_turns,
        "history": history[-12:],  # keep prompt small
        "last_user_message": user_message,
    }

    out = await generate_json(sys, payload)

    reply = (out.get("reply") or "").strip()
    done = bool(out.get("done", False))

    # safety fallback
    if not reply:
        reply = "Thanks. Could you expand on that with a concrete example?"
        done = False

    # if it's the last turn, force done
    if turn_index >= total_turns:
        done = True

    return {"reply": reply, "done": done}


async def evaluate_interview(
    role: str,
    seniority: str,
    language: str,
    history: List[Dict[str, str]],
) -> Dict[str, Any]:
    """
    Returns JSON:
      {
        "final_score": int (0..100),
        "feedback": [string, ...]
      }
    """
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
        "history": history,  # full chat
        "rubric": ["clarity", "relevance", "specificity", "structure", "role_fit"],
    }

    out = await generate_json(sys, payload)

    score = out.get("final_score")
    feedback = out.get("feedback")

    # hard safety
    try:
        score = int(score)
    except Exception:
        score = 70

    score = max(0, min(100, score))

    if not isinstance(feedback, list) or not feedback:
        feedback = [
            "Solid overall communication, but increase specificity.",
            "Use more concrete examples and measurable impact.",
            "Keep answers structured (Situation, Task, Action, Result).",
            "Tie your experience more directly to the role requirements.",
        ]

    # keep feedback concise strings
    feedback = [str(x).strip() for x in feedback if str(x).strip()][:6]

    return {"final_score": score, "feedback": feedback}
