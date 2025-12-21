import json
import uuid
from backend.utils.sanitize import sanitize_json
from backend.services.ai.gemini_client import generate_json
from backend.services.cv_utils import (
    route_intent,
    title_from_playbook,
    normalize_signals,
    render_example_html,
)

# -----------------------------
# NOVELTY CONTROL (IMPORTANT)
# -----------------------------

PLAYBOOK_DIMENSIONS = {
    "summary": [
        "structure",
        "value_proposition",
        "metrics",
        "role_targeting",
        "keywords_ats",
        "clarity_brevity",
        "seniority_positioning",
        "tone_confidence",
    ],
    "impact": ["metrics", "scope", "ownership", "business_value", "outcomes", "scale"],
    "language": ["verbs", "brevity", "specificity", "active_voice", "jargon_cleanup", "consistency"],
    "structure": ["ordering", "spacing", "section_titles", "length", "readability", "consistency"],
    "skills": ["grouping", "relevance", "keyword_alignment", "proficiency", "tools_vs_methods", "signals"],
    "projects": ["story", "problem_solution", "metrics", "tech_stack", "role", "results"],
    "ats": ["keywords", "titles", "formatting", "match_rate", "sections", "duplication"],
    "formatting": ["dates", "alignment", "typos", "consistency", "punctuation", "tense"],
    "experience": ["action_verbs", "impact", "scope", "ownership", "results", "tools"],
    "general": ["clarity", "impact", "structure", "language", "ats", "formatting"],
}


# -----------------------------
# CV SCORING
# -----------------------------

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
        return {
            "clarity": 60,
            "impact": 60,
            "structure": 60,
            "language": 60,
            "overall": 60,
            "reasons": {k: "Auto-defaulted" for k in ["clarity", "impact", "structure", "language"]},
        }
    return result


# -----------------------------
# CV CLASSIFIER
# -----------------------------

SYSTEM_CV_CLASSIFIER = (
    "You are a strict document classifier for a CV/resume upload feature.\n"
    "Decide if the document is a CV/resume or NOT.\n"
    "Return JSON only in this format:\n"
    "{ 'is_cv': bool, 'confidence': int, 'reason': str, 'signals': [ { 'label': str, 'tone': 'positive'|'neutral'|'warning' } ] }\n"
    "Rules:\n"
    "- confidence is 0-100.\n"
    "- reason is 1 sentence, plain text.\n"
    "- signals: 1 to 4 items, each with a short label and a tone.\n"
    "A CV typically contains: contact info, skills, experience/education, dates, bullet points.\n"
    "Non-CV examples: academic report, paper signals, slides, invoices, random notes.\n"
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


# -----------------------------
# CENTER INSIGHTS
# -----------------------------

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
    "- Return 12 to 18 phrases (1–5 words each).\n"
    "- Each highlight MUST appear verbatim somewhere in: summary OR strengths OR improvements OR recommended_focus.\n"
    "- Mix across: skills/tools, actions, outcomes/impact, issues.\n"
    "- No duplicates.\n"
    "- Plain text only.\n"
)

async def generate_center_insights(cv_text: str) -> dict:
    payload = {"cv_text": cv_text}
    try:
        result = await generate_json(SYSTEM_CENTER, payload)
        result = sanitize_json(result)
        if not isinstance(result, dict):
            raise ValueError("Model returned invalid data.")

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

        if isinstance(result["strengths"], list):
            result["strengths"] = result["strengths"][:5]
        else:
            result["strengths"] = []

        if isinstance(result["improvements"], list):
            result["improvements"] = result["improvements"][:5]
        else:
            result["improvements"] = []

        return result

    except Exception as e:
        print("Gemini center analysis failed:", e)
        return {
            "summary": "This CV shows a clear effort to present relevant experience and skills.",
            "strengths": ["Solid overall structure.", "Professional language tone.", "Good consistency between sections."],
            "improvements": ["Emphasize measurable achievements.", "Simplify long sentences for readability."],
            "recommended_focus": "Improve clarity and highlight quantifiable impact.",
            "signals": [],
            "highlights": [],
        }


# -----------------------------
# IMPROVEMENT CARDS (TIPS + EXAMPLES)
# -----------------------------

SYSTEM_TIPS = (
    "You are an expert CV mentor. Create exactly 3 tips for the given intent and CV text.\n\n"
    "You MUST choose ONE dimension from payload.allowed_dimensions.\n"
    "You MUST NOT choose a dimension listed in payload.used_dimensions unless all are used.\n"
    "All 3 tips must align to the chosen dimension.\n\n"
    "Rules:\n"
    "- Each tip must be ONE sentence.\n"
    "- Each tip must be 8–14 words.\n"
    "- Start each tip with a strong action verb.\n"
    "- Include a concrete detail whenever possible.\n"
    "- Do NOT repeat wording from payload.avoid_tips.\n"
    "- Tips must be meaningfully different from prior sets.\n"
    "- Output valid JSON only.\n\n"
    "Return JSON exactly: {\"dimension\":\"...\",\"tips\":[\"...\",\"...\",\"...\"]}"
)

SYSTEM_EXAMPLE = (
    "You are an AI CV rewriting mentor. Generate ONE rewrite example.\n\n"
    "You MUST choose ONE dimension from payload.allowed_dimensions.\n"
    "You MUST NOT choose a dimension listed in payload.used_dimensions unless all are used.\n"
    "The rewrite must match the chosen dimension.\n\n"
    "Rules:\n"
    "- Return JSON only.\n"
    "- before: 10–16 words.\n"
    "- after: 10–16 words.\n"
    "- after must include one metric when plausible.\n"
    "- Do NOT repeat wording or structure from payload.avoid_examples.\n\n"
    "Return JSON exactly: {\"dimension\":\"...\",\"before\":\"...\",\"after\":\"...\"}"
)

def _flatten_last_tips(avoid: list[dict], limit_cards: int = 3, limit_items: int = 12) -> list[str]:
    tips = []
    for a in (avoid or [])[-limit_cards:]:
        tips.extend([t for t in (a.get("tips") or []) if isinstance(t, str)])
    return tips[-limit_items:]


def _last_examples(avoid: list[dict], limit_cards: int = 3) -> list[dict]:
    out = []
    for a in (avoid or [])[-limit_cards:]:
        out.append({"before": a.get("before", ""), "after": a.get("after", "")})
    return out


async def generate_tips(playbook: str, cv_text: str, intent: str, avoid: list[dict] | None = None) -> dict:
    avoid = avoid or []
    allowed = PLAYBOOK_DIMENSIONS.get(playbook, PLAYBOOK_DIMENSIONS["general"])

    used_dimensions = [a.get("tips_dimension") for a in avoid if a.get("tips_dimension")]
    payload = {
        "playbook": playbook,
        "intent": intent,
        "cv_text": cv_text,
        "allowed_dimensions": allowed,
        "used_dimensions": used_dimensions[-8:],
        "avoid_tips": _flatten_last_tips(avoid, limit_cards=3, limit_items=12),
        "variation_seed": str(uuid.uuid4())[:8],
    }

    try:
        result = await generate_json(SYSTEM_TIPS, payload)
        result = sanitize_json(result)

        if isinstance(result, dict) and isinstance(result.get("tips"), list):
            tips = [str(t).strip() for t in result["tips"] if str(t).strip()]
            dim = str(result.get("dimension") or "").strip() or None
            return {"tips": tips[:3], "dimension": dim}

    except Exception as e:
        print("Gemini tip generation failed:", e)

    return {
        "tips": [
            "Quantify outcomes using metrics like time saved, revenue, or accuracy.",
            "Replace vague claims with specific scope, tools, and measurable results.",
            "Align summary keywords to the target role and job description.",
        ],
        "dimension": None,
    }


async def generate_example(playbook: str, cv_text: str, avoid: list[dict] | None = None) -> dict:
    avoid = avoid or []
    allowed = PLAYBOOK_DIMENSIONS.get(playbook, PLAYBOOK_DIMENSIONS["general"])

    used_dimensions = [a.get("example_dimension") for a in avoid if a.get("example_dimension")]
    payload = {
        "playbook": playbook,
        "cv_text": cv_text,
        "allowed_dimensions": allowed,
        "used_dimensions": used_dimensions[-8:],
        "avoid_examples": _last_examples(avoid, limit_cards=3),
        "variation_seed": str(uuid.uuid4())[:8],
    }

    try:
        result = await generate_json(SYSTEM_EXAMPLE, payload)
        result = sanitize_json(result)

        if isinstance(result, dict) and "before" in result and "after" in result:
            before = str(result["before"]).strip()
            after = str(result["after"]).strip()
            dim = str(result.get("dimension") or "").strip() or None
            return {
                "before": before,
                "after": after,
                "dimension": dim,
                "html": render_example_html(before, after),
            }

    except Exception as e:
        print("Gemini example generation failed:", e)

    fallback = {
        "before": "Responsible for managing marketing campaigns across multiple channels.",
        "after": "Led multi-channel campaigns, increasing engagement by 22% within 8 weeks.",
        "dimension": None,
    }
    fallback["html"] = render_example_html(fallback["before"], fallback["after"])
    return fallback


async def build_card_from_intent(intent: str, cv_text: str, avoid: list[dict] | None = None) -> dict:
    playbook = route_intent(intent)

    tips_data = await generate_tips(playbook, cv_text, intent, avoid=avoid or [])
    example_data = await generate_example(playbook, cv_text, avoid=avoid or [])

    return {
        "id": str(uuid.uuid4())[:8],
        "title": title_from_playbook(playbook),
        "subtitle": f"Focus: {intent}",
        "intent": intent,
        "playbook": playbook,
        "tips": tips_data["tips"],
        "_tips_dimension": tips_data.get("dimension"),
        "example": example_data["html"],
        "_example_raw": {"before": example_data["before"], "after": example_data["after"]},
        "_example_dimension": example_data.get("dimension"),
    }
