from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.cv_model import CV
from backend.routers.auth import get_current_user
from backend.services.ai.cm_scoring import compute_match_score_from_facts


from backend.services.ai.career_match import analyze_career_match

import os, json

router = APIRouter(prefix="/cm", tags=["career_match"])

FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "../frontend/pages"
)
templates = Jinja2Templates(directory=FRONTEND_DIR)


def load_mock_jobs():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "mock_jobs.json")
    path = os.path.abspath(path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# --- Simple in-memory cache (per server process) ---
# key: (user_id, cv_id, cv_updated_at, job_id)
_CM_CACHE: dict[tuple[str, str, str, str], dict] = {}


@router.post("/search", response_class=HTMLResponse)
async def cm_search(
    request: Request,
    title: str = Form(""),
    location: str = Form(""),
    mode: str = Form("any"),
):
    jobs = load_mock_jobs()

    title_q = title.lower().strip()
    loc_q = location.lower().strip()
    mode_q = mode.lower().strip()

    filtered = []
    for job in jobs:
        if title_q and title_q not in (job.get("title", "").lower()):
            continue
        if loc_q and loc_q not in (job.get("location", "").lower()):
            continue
        if mode_q != "any":
            job_mode = (job.get("mode", "") or "").lower()
            if mode_q not in job_mode:
                continue
        filtered.append(job)

    return templates.TemplateResponse(
        "partials/cm_job_results.html",
        {"request": request, "jobs": filtered},
    )


@router.post("/analyze", response_class=HTMLResponse)
async def cm_analyze(
    request: Request,
    job_id: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth?error=login_required", status_code=303)

    jobs = load_mock_jobs()
    job = next((j for j in jobs if str(j.get("id")) == str(job_id)), None)

    # Always build a context (avoid UnboundLocalError)
    if not job:
        context = {
            "request": request,
            "job": None,
            "missing_cv": False,
            "cv_uploaded_at": None,
        }
        return templates.TemplateResponse("partials/cm_match_panel.html", context)

    cv = (
        db.query(CV)
        .filter(CV.user_id == user.id, CV.raw_text != None, CV.raw_text != "")
        .order_by(CV.updated_at.desc())
        .first()
    )

    if not cv or not cv.raw_text:
        context = {
            "request": request,
            "job": job,
            "missing_cv": True,
            "cv_uploaded_at": None,
            "match_score": "?",
            "seniority_fit": "",
            "skills_summary": "",
            "strengths": [],
            "gaps": [],
            "next_steps": [],
            "skills_you_have": [],
            "skills_missing": [],
            "reason": "",
        }
        return templates.TemplateResponse("partials/cm_match_panel.html", context)

    cv_text = cv.raw_text
    cv_uploaded_at = cv.updated_at

    job_desc = job.get("description") or job.get("snippet") or ""
    job_text = f"{job.get('title', '')} at {job.get('company', '')}. {job_desc}"

    # Cache key must be STRING-safe (your cv.id is UUID -> don't int() it)
    cache_key = (str(user.id), str(cv.id), str(cv.updated_at), str(job_id))

    if cache_key in _CM_CACHE:
        cached = _CM_CACHE[cache_key]
        cached["request"] = request  # request object must be current
        return templates.TemplateResponse("partials/cm_match_panel.html", cached)

    try:
        analysis = await analyze_career_match(cv_text, job_text)
    except Exception as e:
        print("Career match error:", e)
        analysis = {}

    if not isinstance(analysis, dict):
        analysis = {}

    context = {
        "request": request,
        "job": job,
        "missing_cv": False,
        "cv_uploaded_at": cv_uploaded_at,

        "match_score": analysis.get("match_score", "?"),
        "seniority_fit": analysis.get("seniority_fit", "Fit not determined"),
        "skills_summary": analysis.get("skills_summary", "Skill alignment not available"),

        "strengths": (analysis.get("strengths") or [])[:6],
        "gaps": (analysis.get("gaps") or [])[:6],
        "next_steps": (analysis.get("next_steps") or [])[:6],

        "skills_you_have": (analysis.get("skills_you_have") or [])[:10],
        "skills_missing": (analysis.get("skills_missing") or [])[:10],

        "reason": analysis.get("reason", "Overall match computed from CV evidence against this role."),
    }

    # Store a copy without the Request object (we re-inject request on read)
    cache_payload = dict(context)
    cache_payload.pop("request", None)
    _CM_CACHE[cache_key] = cache_payload

    return templates.TemplateResponse("partials/cm_match_panel.html", context)
