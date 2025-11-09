import json
from .gemini_client import generate_json
from backend.utils.sanitize import sanitize_json
from backend.services.cv_utils import route_intent, title_from_playbook
import uuid

# ========== CV SCORING ==========
SYSTEM_SCORE = (
    "You are an expert career coach evaluating a candidate's CV. "
    "Assess the CV for clarity, impact, structure, and language. "
    "Score each category from 0–100, then provide a short explanation for each — "
    "one sentence only, plain text only, no markdown. "
    "Return JSON in this format:\n"
    "{ 'clarity': int, 'impact': int, 'structure': int, 'language': int, "
    "'overall': int, 'reasons': { 'clarity': str, 'impact': str, 'structure': str, 'language': str } }."
)


async def score_cv_with_ai(raw_text: str):
    payload = {"cv_text": raw_text}
    result = await generate_json(SYSTEM_SCORE, payload)
    result = sanitize_json(result)

    if not isinstance(result, dict) or "overall" not in result:
        # fallback if model misbehaves
        return {
            "clarity": 60,
            "impact": 60,
            "structure": 60,
            "language": 60,
            "overall": 60,
            "reasons": {k: "Auto-defaulted" for k in ["clarity", "impact", "structure", "language"]}
        }
    return result

# ========== EXTRACT SECTIONS ==========
SYSTEM_CENTER = (
    "You are a career mentor summarizing the overall strengths and improvement areas "
    "of a candidate's CV. Based on the provided text, return a concise and structured analysis. "
    "Keep the tone supportive, insightful, and mentor-like — not robotic. "
    "Return JSON:\n"
    "{ 'summary': str, "
    "'strengths': [str], "
    "'improvements': [str], "
    "'recommended_focus': str }"
)

async def generate_center_insights(cv_text: str) -> dict:
    payload = {"cv_text": cv_text}
    try:
        result = await generate_json(SYSTEM_CENTER, payload)
        result = sanitize_json(result)

        if not isinstance(result, dict):
            raise ValueError("Gemini returned invalid data.")

        # Ensure all expected keys exist
        result.setdefault("summary", "No summary generated.")
        result.setdefault("strengths", [])
        result.setdefault("improvements", [])
        result.setdefault("recommended_focus", "No focus identified.")

        return result
    except Exception as e:
        print("Gemini center analysis failed:", e)
        # fallback
        return {
            "summary": "This CV demonstrates a clear effort to present relevant experience and skills.",
            "strengths": [
                "Solid overall structure.",
                "Professional language tone.",
                "Good consistency between sections."
            ],
            "improvements": [
                "Could emphasize more measurable achievements.",
                "Some sentences might be simplified for clarity."
            ],
            "recommended_focus": "Improve clarity and highlight quantifiable impact."
        }

# ========== BUILD IMPROVEMENT CARD ==========

# ===== SYSTEM PROMPTS =====
SYSTEM_TIPS = (
    "You are an expert career mentor helping candidates refine their CVs. "
    "Given a user's improvement intent and CV text, suggest 3 actionable, concrete tips "
    "tailored to that intent. Each tip must be short, written in plain English, and "
    "focus on clarity, impact, or communication quality. "
    "Return JSON: { 'tips': [str, str, str] }"
)

SYSTEM_EXAMPLE = (
    "You are an AI CV rewriting mentor. "
    "Given a playbook (theme) and the CV text, generate one example rewrite, "
    "demonstrating how to apply that advice. Use plain HTML-safe text with <em>Before</em> "
    "and <em>After</em> labels. Keep it short, professional, and realistic. "
    "Return JSON: { 'example': str }"
)


# ===== MAIN BUILDER =====
async def build_card_from_intent(intent: str, cv_text: str) -> dict:
    playbook = route_intent(intent)
    tips = await generate_tips(playbook, cv_text, intent)
    example = await generate_example(playbook, cv_text)
    return {
        "id": str(uuid.uuid4())[:8],
        "title": title_from_playbook(playbook),
        "subtitle": f"Focus: {intent}",
        "tips": tips,
        "example": example,
        "playbook": playbook,
    }


# ===== GEMINI FUNCTIONS =====
async def generate_tips(playbook: str, cv_text: str, intent: str):
    payload = {
        "playbook": playbook,
        "intent": intent,
        "cv_text": cv_text,
    }

    try:
        result = await generate_json(SYSTEM_TIPS, payload)
        result = sanitize_json(result)

        if isinstance(result, dict) and "tips" in result:
            return result["tips"]

        # fallback
        return [
            "Clarify what you achieved and the measurable impact.",
            "Keep sentences under ~24 words to maintain clarity.",
            "Start each bullet with a strong action verb.",
        ]
    except Exception as e:
        print("Gemini tip generation failed:", e)
        return [
            "Add specific achievements or quantifiable results.",
            "Replace weak verbs with impactful ones like 'led', 'built', 'improved'.",
            "Focus each bullet on results, not responsibilities.",
        ]


async def generate_example(playbook: str, cv_text: str):
    payload = {
        "playbook": playbook,
        "cv_text": cv_text,
    }

    try:
        result = await generate_json(SYSTEM_EXAMPLE, payload)
        result = sanitize_json(result)

        if isinstance(result, dict) and "example" in result:
            return result["example"]

        # fallback example
        return (
            "<em>Before:</em> Responsible for managing marketing campaigns.<br>"
            "<em>After:</em> Led multi-channel marketing campaigns increasing engagement by 22%."
        )
    except Exception as e:
        print("Gemini example generation failed:", e)
        return (
            "<em>Before:</em> Worked on data reports.<br>"
            "<em>After:</em> Built automated dashboards reducing reporting time by 30%."
        )

# ========== TAILOR FOR JOB ==========
SYSTEM_TAILOR = (
    "You are an AI CV-tailoring assistant. "
    "Match the given CV to the provided job description. "
    "short, plain text, no markdown"
    "Return JSON: { 'suggestions': [ { 'section': str, 'original': str, 'improved': str, 'why': str, 'keywords': [str] } ], "
    "'matched_keywords': [str] }"
)

async def tailor_for_job(job_desc: str, job_title: str | None, company: str | None, doc_json: str | None):
    try:
        doc = json.loads(doc_json) if doc_json else {"sections": []}
    except Exception:
        doc = {"sections": []}

    payload = {
        "job_description": job_desc,
        "job_title": job_title,
        "company": company,
        "cv_sections": doc.get("sections", []),
    }

    result = await generate_json(SYSTEM_TAILOR, payload)
    result = sanitize_json(result)
    if not isinstance(result, dict):
        return {"suggestions": [], "matched_keywords": []}
    if "suggestions" not in result:
        result["suggestions"] = []
    if "matched_keywords" not in result:
        result["matched_keywords"] = []
    return result
