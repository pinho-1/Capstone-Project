# backend/services/cm_scoring.py

from __future__ import annotations

def clamp_int(x, lo: int, hi: int, default: int) -> int:
    try:
        x = int(x)
    except Exception:
        return default
    return max(lo, min(hi, x))


def label_seniority_fit(job_level: str | None, cv_level: str | None, score: int) -> str:
    # deterministic UI label (NOT AI-written)
    level_order = {"intern": 0, "junior": 1, "mid": 2, "senior": 3}

    jl = level_order.get((job_level or "").lower(), 1)  # default junior
    cl = level_order.get((cv_level or "").lower(), 1)   # default junior

    score = clamp_int(score, 0, 100, 60)

    # If CV level is unknown, don't mention it. Use score bands.
    if (cv_level or "").lower() in ("unknown", "", "none"):
        if score >= 75:
            return "Strong potential"
        if score >= 60:
            return "Good potential"
        return "Early fit"

    diff = cl - jl  # negative = under-level

    if diff >= 1:
        return "Senior for this role"
    if diff == 0:
        return "Strong fit for level"
    if diff == -1:
        return "Slight stretch"
    return "Stretch role"


def label_core_skills(matched: int, total: int) -> str:
    try:
        matched = int(matched)
        total = int(total)
    except Exception:
        return "Core skills: n/a"

    if total <= 0:
        return "Core skills: n/a"

    pct = round(100 * matched / total)
    return f"{matched}/{total} core skills ({pct}%)"


def compute_match_score_from_facts(facts: dict) -> dict:
    """
    Deterministic score so it doesn't jump around.
    Uses:
      - must_have_skills, matched_must_have, missing_must_have
      - job_level, cv_level
      - experience_signals (optional list)
    """
    must = facts.get("must_have_skills") or []
    matched = facts.get("matched_must_have") or []
    missing = facts.get("missing_must_have") or []

    # matched may be list[dict] or list[str]
    matched_n = 0
    for m in matched:
        if isinstance(m, dict) and m.get("skill"):
            matched_n += 1
        elif isinstance(m, str) and m.strip():
            matched_n += 1

    total_n = len([s for s in must if isinstance(s, str) and s.strip()]) or len(must) or max(matched_n + len(missing), 0)

    # base from must-have coverage
    if total_n > 0:
        coverage = matched_n / total_n
    else:
        coverage = 0.5  # neutral if job has no must-haves

    # experience signals bonus (kept small)
    exp_signals = facts.get("experience_signals") or []
    exp_bonus = 0
    if isinstance(exp_signals, list):
        exp_bonus = min(len(exp_signals), 4) * 3  # 0..12

    # seniority penalty if under-level
    job_level = (facts.get("job_level") or "").lower()
    cv_level = (facts.get("cv_level") or "").lower()
    level_order = {"intern": 0, "junior": 1, "mid": 2, "senior": 3}
    jl = level_order.get(job_level, 1)
    cl = level_order.get(cv_level, 1)

    seniority_penalty = 0
    if cv_level not in ("", "unknown", "none") and cl < jl:
        seniority_penalty = (jl - cl) * 8  # 8 points per level gap

    # turn into score (stable)
    score = round(55 + 40 * coverage + exp_bonus - seniority_penalty)
    score = clamp_int(score, 0, 100, 60)

    seniority_fit = label_seniority_fit(facts.get("job_level"), facts.get("cv_level"), score)
    skills_summary = label_core_skills(matched_n, total_n)

    return {
        "match_score": score,
        "seniority_fit": seniority_fit,
        "skills_summary": skills_summary,
        "matched_n": matched_n,
        "total_n": total_n,
    }
