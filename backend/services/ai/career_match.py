import json
from .gemini_client import generate_json
from backend.utils.sanitize import sanitize_json

SYSTEM_CAREER_MATCH = (
    "You are an expert career coach. "
    "Compare a candidate's CV with a specific job description and explain how well they match. "
    "You MUST return ONLY valid JSON (no markdown, no comments) with this exact structure:\n"
    "{\n"
    '  "match_score": int,                // 0–100 overall match\n'
    '  "seniority_fit": "string",         // e.g. "Good fit for mid-level role"\n'
    '  "skills_summary": "string",        // short one-line summary of skills alignment\n'
    '  "strengths": [ "string", ... ],    // 3–5 bullets where the candidate is strong\n'
    '  "gaps": [ "string", ... ],         // 3–5 bullets describing missing or weaker areas\n'
    '  "next_steps": [ "string", ... ],   // 3 concrete next steps the candidate can take\n'
    '  "skills_you_have": [ "string", ... ],   // key skills from the job the CV already shows\n'
    '  "skills_missing": [ "string", ... ],    // key skills from the job that are missing/weak\n'
    '  "reason": "string"                 // 1–2 sentence explanation of the match score\n'
    "}\n"
    "Rules:\n"
    "- Be honest but supportive in tone.\n"
    "- Make the bullets short and specific, not generic fluff.\n"
    "- Always fill all fields; if unsure, make your best guess based on the text.\n"
)

async def analyze_career_match(cv_text: str, job_text: str) -> dict:
    payload = {
        "cv_text": cv_text,
        "job_description": job_text,
    }

    try:
        raw = await generate_json(SYSTEM_CAREER_MATCH, payload)
        data = sanitize_json(raw)
    except Exception as e:
        print("Career match AI error:", e)
        data = {}

    if not isinstance(data, dict):
        data = {}

    # --- Safe defaults so the UI never explodes ---
    if not isinstance(data.get("match_score"), int):
        data["match_score"] = 65  # neutral-ish default

    data.setdefault("seniority_fit", "Fit not determined")
    data.setdefault("skills_summary", "Skill alignment not available")
    data.setdefault(
        "reason",
        "Overall match estimated based on your CV compared to this job description."
    )

    for key in ["strengths", "gaps", "next_steps", "skills_you_have", "skills_missing"]:
        value = data.get(key)
        if not isinstance(value, list):
            data[key] = []

    return data
