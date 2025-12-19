import json
from .gemini_client import generate_json
from backend.utils.sanitize import sanitize_json
from backend.services.cv_utils import route_intent, title_from_playbook, normalize_signals
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
    result = await generate_json(SYSTEM_SCORE, payload, temperature=0.0)
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

# ========== CV CLASSIFIER ==========
SYSTEM_CV_CLASSIFIER = (
    "You are a strict document classifier for a CV/resume upload feature.\n"
    "Decide if the document is a CV/resume or NOT.\n"
    "Return JSON only in this format:\n"
    "{ 'is_cv': bool, 'confidence': int, 'reason': str, 'signals': [ { 'label': str, 'tone': 'positive'|'neutral'|'warning  ' } ] }\n"
    "Rules:\n"
    "- confidence is 0-100.\n"
    "- reason is 1 sentence, plain text.\n"
    "- signals: 1 to 4 items, each with a short label and a tone.\n"
    "A CV typically contains: contact info, skills, experience/education, dates, bullet points.\n"
    "Non-CV examples: academic report, paper, slides, invoices, random notes.\n"
)

async def classify_document_is_cv(raw_text: str) -> dict:
    payload = {"cv_text": raw_text}
    result = await generate_json(SYSTEM_CV_CLASSIFIER, payload, temperature=0.0)
    result = sanitize_json(result)

    if not isinstance(result, dict):
        return {"is_cv": True, "confidence": 50, "reason": "Could not classify reliably.", "signals": ["Uncertain"]}

    result.setdefault("is_cv", True)
    result.setdefault("confidence", 50)
    result.setdefault("reason", "No reason provided.")
    result.setdefault("signals", [])
    result["signals"] = normalize_signals(result["signals"], default_tone="neutral", limit=4)
    return result

    return result

# ========== EXTRACT SECTIONS ==========
SYSTEM_CENTER = (
    "You are a career mentor reviewing a CV. "
    "Be concise, direct, and practical. Avoid academic tone. "
    "IMPORTANT RULES:\n"
    "- Summary: max 2 sentences.\n"
    "- Strengths: 3 to 5 bullet points, short phrases.\n"
    "- Improvements: 3 to 5 bullet points, actionable.\n"
    "- Recommended focus: exactly 1 sentence.\n"
    "- Signals: 2 to 4 items with tone tags.\n"
    "If the document is NOT a CV (e.g. report, paper, slides), "
    "state this clearly in the summary and recommendations.\n\n"
    "Return JSON:\n"
    "{ 'summary': str, "
    "'strengths': [str], "
    "'improvements': [str], "
    "'recommended_focus': str, "
    "'signals': [ { 'label': str, 'tone': 'positive'|'neutral'|'warning' } ], "
    "'highlights': [str] } \n"
    "Rules for highlights:\n"
    "- Return 12 to 18 phrases. (1–5 words each).\n"
    "- Each highlight MUST appear verbatim (copy-paste exact) somewhere in: summary OR strengths OR improvements OR recommended_focus.\n"
    "- Mix across categories: (skills/tools), (actions), (outcomes/impact), (issues).\n"
    "- Prefer specific multi-word phrases over single words.\n"
    "- No duplicates.\n"
    "- Plain text only.\n"
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
        result.setdefault("signals", [])
        result["signals"] = normalize_signals(result["signals"], default_tone="neutral", limit=4)
        result.setdefault("highlights", [])
        if not isinstance(result["highlights"], list):
            result["highlights"] = []
        result["highlights"] = result["highlights"][:20]

        result["strengths"] = result["strengths"][:5]
        result["improvements"] = result["improvements"][:5]

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
