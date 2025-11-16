# backend/services/ai/career_match_agent.py

from .gemini_client import generate_json

SYSTEM_PROMPT = """
You are an AI career-matching assistant.

Your job is to compare a candidate's CV with a specific job description
and return a structured, machine-readable JSON analysis.

Be concise, specific, and practical. Focus on how well the candidate fits
the role, what they already bring, and what they should improve.

You must ALWAYS respond with valid JSON only. No extra commentary.
"""

async def analyze_career_match(cv_text: str, job_text: str, user_goal: str | None = None) -> dict:
    """
    Uses Gemini (via generate_json) to get a structured career-match analysis.

    Expected JSON response shape:

    {
      "match_score": number (0-100),
      "seniority_fit": "Excellent" | "Good" | "Weak",
      "skills_matched": number,
      "skills_required": number,
      "strengths": [string],
      "gaps": [string],
      "next_steps": [string]
    }
    """

    payload = {
        "cv_text": cv_text,
        "job_description": job_text,
        "user_goal": user_goal,
        "response_schema": {
            "match_score": "number 0-100 indicating overall fit",
            "seniority_fit": "string: Excellent, Good, or Weak",
            "skills_matched": "integer: how many key skills the CV clearly shows",
            "skills_required": "integer: total key skills in the job",
            "strengths": "list of short bullet points (strings)",
            "gaps": "list of short bullet points (strings)",
            "next_steps": "list of short, actionable bullet points (strings)"
        }
    }

    result = await generate_json(SYSTEM_PROMPT, payload)
    # result is already a dict (or {"error": "..."} if something broke)
    return result
