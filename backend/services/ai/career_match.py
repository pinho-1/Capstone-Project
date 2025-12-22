import re
from typing import Any, Dict, List

from backend.services.ai.gemini_client import generate_json
from backend.utils.sanitize import sanitize_json


# =========================================
# 1) MODEL PROMPT (STRICT + EVIDENCE-BOUND)
# =========================================

SYSTEM_CAREER_MATCH = """
You are an expert career coach doing a CV vs Job match.

ABSOLUTE PRIORITY: JOB REQUIREMENTS
- Only discuss CV details that directly support or block a requirement/responsibility in the JOB DESCRIPTION.
- Even if something is true in the CV (e.g., hobbies, language level), DO NOT mention it unless the JOB DESCRIPTION explicitly requires it or it is clearly essential for a listed task.

GROUNDING RULES (must follow)
1) Use ONLY information explicitly supported by the CV text and/or the job description.
   - Do NOT invent traits, languages/levels, tools, experience, or outcomes.
2) All skills listed in must_have_skills / nice_to_have_skills MUST come from the JOB DESCRIPTION wording (copy/derive from job text).
3) matched_must_have:
   - Include ONLY must-have skills that the CV supports.
   - evidence MUST be a short quote-like snippet from the CV text (2–12 words). NO paraphrase.
4) missing_must_have MUST be the must-have skills that are NOT supported by CV evidence.
5) strengths / gaps / next_steps MUST be mapped to job requirements:
   - Every strength must correspond to at least ONE must-have skill (or a core responsibility clearly stated in the job).
   - Every gap must correspond to a missing must-have skill or a core responsibility clearly stated in the job.
   - next_steps: EXACTLY 3 actions, each explicitly closing one gap (project / course / portfolio proof / measurable deliverable).
6) NO GENERIC FILLER:
   - Do not write teamwork/communication/discipline/motivation unless the job explicitly asks AND the CV explicitly states evidence.
7) Levels:
   - job_level and cv_level must be one of: intern|junior|mid|senior|unknown
   - If not explicitly stated, use "unknown".

OUTPUT FORMAT
Return ONLY valid JSON (no markdown, no comments) with EXACT keys and types:
{
  "job_level": "intern|junior|mid|senior|unknown",
  "cv_level": "intern|junior|mid|senior|unknown",

  "must_have_skills": ["string", ...],        // 3-8 items, from the job description
  "nice_to_have_skills": ["string", ...],     // 0-6 items, from the job description
  "cv_skills": ["string", ...],               // 6-20 items, from the CV text

  "matched_must_have": [
    { "skill": "string", "evidence": "string" }
  ],
  "missing_must_have": ["string", ...],

  "experience_signals": ["string", ...],      // 0-6, ONLY signals tied to must-have skills/tasks
  "strengths": ["string", ...],               // 3-5, each tied to must-haves
  "gaps": ["string", ...],                    // 3-5, each tied to missing must-haves/tasks
  "next_steps": ["string", ...],              // EXACTLY 3, each tied to a gap
  "one_line_summary": "string"                // ONE sentence, reference must-have coverage + level
}

QUALITY CHECK BEFORE RETURNING
- If a bullet does not map to a must-have skill or job responsibility, remove it.
- If evidence is not a real snippet from the CV, do not claim the match.
"""
SYSTEM_CAREER_MATCH_JUDGE = """
You are a strict scoring judge for CV vs Job match.

You will receive:
- extracted_facts (already grounded): must_have_skills, matched_must_have, missing_must_have, job_level, cv_level, experience_signals
- cv_text and job_description

Rules:
1) You MUST stay consistent with extracted facts. Do not invent missing/matched skills.
2) Your score is an expert judgement of strength of evidence + realism of experience.
3) Output MUST be stable: temperature is 0.0 and you must avoid variability.
4) Provide:
   - ai_score: int 0-100
   - confidence: int 0-100 (how reliable the job text + CV evidence is)
   - rationale: ONE sentence referencing must-have coverage + evidence quality

Return JSON only:
{ "ai_score": int, "confidence": int, "rationale": "string" }
"""


async def judge_match_score(cv_text: str, job_text: str, facts: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "cv_text": cv_text,
        "job_description": job_text,
        "extracted_facts": {
            "job_level": facts.get("job_level"),
            "cv_level": facts.get("cv_level"),
            "must_have_skills": facts.get("must_have_skills") or [],
            "matched_must_have": facts.get("matched_must_have") or [],
            "missing_must_have": facts.get("missing_must_have") or [],
            "experience_signals": facts.get("experience_signals") or [],
        }
    }

    raw = await generate_json(SYSTEM_CAREER_MATCH_JUDGE, payload, temperature=0.0)
    data = sanitize_json(raw)

    if not isinstance(data, dict):
        data = {}

    ai_score = data.get("ai_score")
    conf = data.get("confidence")
    rationale = str(data.get("rationale") or "").strip()

    if not isinstance(ai_score, int):
        ai_score = 60
    if not isinstance(conf, int):
        conf = 60

    ai_score = max(0, min(100, ai_score))
    conf = max(0, min(100, conf))
    if not rationale:
        rationale = "AI score reflects strength of CV evidence against job must-haves."

    return {"ai_score": ai_score, "confidence": conf, "rationale": rationale}



# =========================================
# 2) HELPERS (DEDUPE + SANITIZE)
# =========================================

_BANNED_PATTERNS = [
    r"\bB1\b|\bB2\b|\bC1\b|\bC2\b",
    r"\bdiscipl(in|ine)\b",
    r"\bperseverance\b",
    r"\boptimistic\b",
    r"\bsocially\b",
    r"\bfocused\b",
]


def _norm_skill(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items or []:
        x2 = str(x).strip()
        if not x2:
            continue
        k = _norm_skill(x2)
        if k in seen:
            continue
        seen.add(k)
        out.append(x2)
    return out


def _safe_list(v: Any, limit: int | None = None) -> List[str]:
    if not isinstance(v, list):
        return []
    out = []
    for x in v:
        s = str(x).strip()
        if not s:
            continue
        # hard block obvious hallucination-y stuff (optional but useful)
        if any(re.search(p, s, flags=re.I) for p in _BANNED_PATTERNS):
            continue
        out.append(s)
    out = _dedupe_keep_order(out)
    return out[:limit] if limit else out


def _safe_level(v: Any) -> str:
    v = str(v or "").strip().lower()
    if v in {"intern", "junior", "mid", "senior"}:
        return v
    return "unknown"

# =========================================
# 2.5) POST-VALIDATION + FALLBACK BUILDERS
# =========================================

def _clamp_list(items: List[str], min_len: int, max_len: int) -> List[str]:
    items = _dedupe_keep_order([str(x).strip() for x in (items or []) if str(x).strip()])
    if len(items) > max_len:
        items = items[:max_len]
    return items


def _evidence_in_cv(cv_text: str, evidence: str) -> bool:
    """
    Evidence must be a real snippet from CV.
    We accept case-insensitive substring match.
    """
    cv_low = (cv_text or "").lower()
    ev_low = (evidence or "").strip().lower()
    if not ev_low:
        return False
    if len(ev_low) < 3:
        return False
    return ev_low in cv_low


def _cleanup_matched_with_evidence(cv_text: str, matched: List[dict]) -> List[dict]:
    """
    Keep only matched entries with (skill + evidence) and evidence present in CV.
    """
    out = []
    for item in matched or []:
        if not isinstance(item, dict):
            continue
        skill = str(item.get("skill") or "").strip()
        evidence = str(item.get("evidence") or "").strip()

        if not skill or not evidence:
            continue
        if not _evidence_in_cv(cv_text, evidence):
            continue

        out.append({"skill": skill, "evidence": evidence})

    # de-dupe by normalized skill
    seen = set()
    deduped = []
    for m in out:
        k = _norm_skill(m["skill"])
        if k in seen:
            continue
        seen.add(k)
        deduped.append(m)

    return deduped


def _derive_missing(must_have: List[str], matched: List[dict]) -> List[str]:
    matched_set = {_norm_skill(m.get("skill", "")) for m in (matched or []) if isinstance(m, dict)}
    return [s for s in (must_have or []) if _norm_skill(s) not in matched_set]


def _build_strengths_from_matches(matched: List[dict]) -> List[str]:
    skills = [m.get("skill") for m in (matched or []) if isinstance(m, dict) and m.get("skill")]
    skills = _dedupe_keep_order([str(s).strip() for s in skills if str(s).strip()])
    strengths = [f"Evidence of {s} in your CV." for s in skills[:5]]
    return strengths


def _build_gaps_from_missing(missing: List[str]) -> List[str]:
    missing = _dedupe_keep_order([str(s).strip() for s in (missing or []) if str(s).strip()])
    gaps = [f"No clear CV evidence for: {s}." for s in missing[:5]]
    return gaps


def _build_next_steps_from_missing(missing: List[str]) -> List[str]:
    """
    EXACTLY 3 steps. Make them skill-linked and portfolio-proof oriented.
    """
    missing = _dedupe_keep_order([str(s).strip() for s in (missing or []) if str(s).strip()])
    steps = []

    anchors = (missing[:3] + ["portfolio proof", "project ownership", "role-specific practice"])[:3]

    for s in anchors:
        if s.lower() in {"portfolio proof", "project ownership", "role-specific practice"}:
            if s == "portfolio proof":
                steps.append("Add one portfolio project with measurable business impact (KPIs + dashboard).")
            elif s == "project ownership":
                steps.append("Write 3 CV bullets showing end-to-end ownership (problem → method → result).")
            else:
                steps.append("Prepare 2 STAR stories aligned to the job responsibilities and tools.")
        else:
            steps.append(f"Build a small project proving '{s}' and document results in your portfolio.")

    return steps[:3]


def validate_and_fix_facts(cv_text: str, facts: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enforce hard constraints and rebuild weak sections from must-have coverage.
    """
    must_have = facts.get("must_have_skills") or []
    nice_to_have = facts.get("nice_to_have_skills") or []
    cv_skills = facts.get("cv_skills") or []

    # Clamp MUST/NICE/CV skills to spec
    must_have = _clamp_list(must_have, min_len=3, max_len=8)
    nice_to_have = _clamp_list(nice_to_have, min_len=0, max_len=6)
    cv_skills = _clamp_list(cv_skills, min_len=6, max_len=20)

    # Matched must-have must have real evidence
    matched = facts.get("matched_must_have") if isinstance(facts.get("matched_must_have"), list) else []
    matched = _cleanup_matched_with_evidence(cv_text, matched)

    # Missing must-have derived from must-have - matched
    derived_missing = _derive_missing(must_have, matched)
    missing = derived_missing[:8]

    # Strengths/gaps/steps
    strengths = facts.get("strengths") or []
    gaps = facts.get("gaps") or []
    next_steps = facts.get("next_steps") or []

    strengths = _clamp_list(strengths, min_len=0, max_len=5)
    gaps = _clamp_list(gaps, min_len=0, max_len=5)
    next_steps = _clamp_list(next_steps, min_len=0, max_len=3)

    # Rebuild if weak
    if len(strengths) < 3:
        strengths = _build_strengths_from_matches(matched)
    strengths = _clamp_list(strengths, min_len=3, max_len=5)

    if len(gaps) < 3:
        gaps = _build_gaps_from_missing(missing)
    gaps = _clamp_list(gaps, min_len=3, max_len=5)

    if len(next_steps) != 3:
        next_steps = _build_next_steps_from_missing(missing)
    next_steps = next_steps[:3]

    # Experience signals: clamp hard so score doesn't get inflated by fluff
    exp = facts.get("experience_signals") or []
    exp = _clamp_list(exp, min_len=0, max_len=4)

    facts["must_have_skills"] = must_have
    facts["nice_to_have_skills"] = nice_to_have
    facts["cv_skills"] = cv_skills
    facts["matched_must_have"] = matched
    facts["missing_must_have"] = missing
    facts["experience_signals"] = exp
    facts["strengths"] = strengths
    facts["gaps"] = gaps
    facts["next_steps"] = next_steps

    s = str(facts.get("one_line_summary") or "").strip()
    facts["one_line_summary"] = s or "Summary unavailable from extracted evidence."

    return facts

# =========================================
# 3) AI -> FACTS EXTRACTION (TEMP=0.0)
# =========================================

async def extract_career_match_facts(cv_text: str, job_text: str) -> Dict[str, Any]:
    payload = {"cv_text": cv_text, "job_description": job_text}

    # IMPORTANT: temperature=0.0 => more stable outputs
    raw = await generate_json(SYSTEM_CAREER_MATCH, payload, temperature=0.0)
    data = sanitize_json(raw)

    if not isinstance(data, dict):
        data = {}

    facts: Dict[str, Any] = {
        "job_level": _safe_level(data.get("job_level")),
        "cv_level": _safe_level(data.get("cv_level")),

        "must_have_skills": _safe_list(data.get("must_have_skills"), limit=20),
        "nice_to_have_skills": _safe_list(data.get("nice_to_have_skills"), limit=20),
        "cv_skills": _safe_list(data.get("cv_skills"), limit=40),

        "matched_must_have": data.get("matched_must_have") if isinstance(data.get("matched_must_have"), list) else [],
        "missing_must_have": _safe_list(data.get("missing_must_have"), limit=20),

        "experience_signals": _safe_list(data.get("experience_signals"), limit=10),
        "strengths": _safe_list(data.get("strengths"), limit=6),
        "gaps": _safe_list(data.get("gaps"), limit=6),
        "next_steps": _safe_list(data.get("next_steps"), limit=3),

        "one_line_summary": str(data.get("one_line_summary") or "").strip() or "Match summary unavailable.",
    }

    # Normalize matched_must_have objects
    norm_matched = []
    for item in facts["matched_must_have"]:
        if not isinstance(item, dict):
            continue
        skill = str(item.get("skill") or "").strip()
        evidence = str(item.get("evidence") or "").strip()
        if skill:
            # also filter banned fluff inside skill/evidence
            if any(re.search(p, skill, flags=re.I) for p in _BANNED_PATTERNS):
                continue
            norm_matched.append({"skill": skill, "evidence": evidence})
    facts["matched_must_have"] = norm_matched[:20]

    # If model forgot to fill missing_must_have, derive it from must_have - matched
    if not facts["missing_must_have"] and facts["must_have_skills"]:
        matched_set = {_norm_skill(m["skill"]) for m in facts["matched_must_have"]}
        missing = [s for s in facts["must_have_skills"] if _norm_skill(s) not in matched_set]
        facts["missing_must_have"] = missing[:20]

    # Force next_steps to exactly 3 (fallbacks are generic but safe)
    if len(facts["next_steps"]) < 3:
        fallback_steps = [
            "Tailor your CV bullets to the job’s must-have skills.",
            "Add one portfolio project proving an end-to-end analytics workflow.",
            "Prepare 2–3 STAR stories mapped to the role’s responsibilities.",
        ]
        for x in fallback_steps:
            if len(facts["next_steps"]) >= 3:
                break
            if x not in facts["next_steps"]:
                facts["next_steps"].append(x)
        facts["next_steps"] = facts["next_steps"][:3]

    return facts


# =========================================
# 4) DETERMINISTIC SCORE (YOUR LOGIC)
# =========================================

def compute_match_score(facts: Dict[str, Any]) -> Dict[str, Any]:
    must = facts.get("must_have_skills") or []
    matched = facts.get("matched_must_have") or []
    missing = facts.get("missing_must_have") or []
    job_level = facts.get("job_level", "unknown")
    cv_level = facts.get("cv_level", "unknown")

    must_total = max(1, len(must))
    must_matched = min(len(matched), must_total)

    # Core: must-have coverage (0..70)
    must_ratio = must_matched / must_total
    must_points = round(70 * must_ratio)

    # Penalty for missing must-haves (cap -20)
    miss_pen = min(20, 5 * max(0, len(missing)))
    # scale penalty if must list is large
    miss_pen = round(miss_pen * (1.0 if must_total <= 6 else 0.7))

    # Seniority alignment bonus/penalty (-10..+10)
    level_order = {"intern": 0, "junior": 1, "mid": 2, "senior": 3, "unknown": 1}
    diff = level_order.get(cv_level, 1) - level_order.get(job_level, 1)

    if diff == 0:
        level_points = 10
        seniority_fit = "Good fit"
    elif diff < 0:
        level_points = -10
        seniority_fit = "Slight stretch"
    else:
        level_points = -4
        seniority_fit = "Slight stretch"

    # Experience signals bonus (0..20)
    signals = facts.get("experience_signals") or []
    exp_points = min(20, 4 * len(signals))

    score = must_points - miss_pen + level_points + exp_points
    score = max(0, min(100, int(score)))

    skills_summary = f"{must_matched}/{must_total} must-haves matched"

    return {
        "match_score": score,
        "seniority_fit": seniority_fit,
        "skills_summary": skills_summary,
    }


# =========================================
# 5) FINAL API OUTPUT (FACTS + SCORE)
# =========================================

async def analyze_career_match(cv_text: str, job_text: str) -> Dict[str, Any]:
    facts = await extract_career_match_facts(cv_text, job_text)

    # enforce constraints + rebuild weak outputs (your existing validator)
    facts = validate_and_fix_facts(cv_text, facts)

    computed = compute_match_score(facts)

    # --- AI judgement layer (temp=0, stable) ---
    judge = await judge_match_score(cv_text, job_text, facts)
    ai_score = judge["ai_score"]
    ai_conf = judge["confidence"]
    ai_rationale = judge["rationale"]

    # --- Clamp AI score so it can't contradict must-have coverage too much ---
    must_total = max(1, len(facts.get("must_have_skills") or []))
    must_matched = min(len(facts.get("matched_must_have") or []), must_total)
    must_ratio = must_matched / must_total

    # allowed band based on coverage (prevents insane scores)
    # ex: if 1/3 matched, AI can't claim 90
    min_allowed = int(10 + 70 * must_ratio)   # 10..80
    max_allowed = int(40 + 60 * must_ratio)   # 40..100
    ai_score = max(min_allowed, min(max_allowed, ai_score))

    # --- Weighted blend ---
    # Keep deterministic as the base; let AI adjust mildly.
    weight_ai = 0.30  # 30% AI, 70% deterministic
    final_score = int(round((1 - weight_ai) * computed["match_score"] + weight_ai * ai_score))
    final_score = max(0, min(100, final_score))

    skills_you_have = [
        m["skill"]
        for m in facts.get("matched_must_have", [])
        if isinstance(m, dict) and m.get("skill")
    ]
    skills_missing = facts.get("missing_must_have", []) or []

    # reason stays stable + evidence-based
    reason = f"{facts.get('one_line_summary','').strip()} ({computed['skills_summary']}). {ai_rationale}".strip()

    return {
        **facts,
        "match_score": final_score,
        "seniority_fit": computed["seniority_fit"],
        "skills_summary": computed["skills_summary"],

        # optional: expose these for debugging / future UI
        "ai_score": ai_score,
        "ai_confidence": ai_conf,

        "skills_you_have": skills_you_have[:10],
        "skills_missing": skills_missing[:10],
        "reason": reason or "Overall match computed from CV evidence against this role.",

        "strengths": (facts.get("strengths") or [])[:5],
        "gaps": (facts.get("gaps") or [])[:5],
        "next_steps": (facts.get("next_steps") or [])[:3],
    }
