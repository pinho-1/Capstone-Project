import os
import json
import time

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from langfuse import observe, get_client

from backend.database import get_db
from backend.models.cv_model import CV
from backend.routers.auth import get_current_user
from backend.services.ai.career_match import analyze_career_match

router = APIRouter(prefix="/cm", tags=["career_match"])

FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "../frontend/pages",
)
templates = Jinja2Templates(directory=FRONTEND_DIR)


# -----------------------------
# Langfuse helper
# -----------------------------

def safe_langfuse_client():
    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        return get_client()
    return None


def cm_trace_session_id(user_id: int, cv_id: str, job_id: str) -> str:
    return f"talentum_cm_{user_id}_{cv_id}_{job_id}"


# -----------------------------
# Mock jobs loader
# -----------------------------

def load_mock_jobs():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "mock_jobs.json")
    path = os.path.abspath(path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# -----------------------------
# Cache (bounded, per process)
# -----------------------------
# key: (user_id, cv_id, cv_updated_at, job_id)
_CM_CACHE: dict[tuple[str, str, str, str], dict] = {}
_CM_CACHE_ORDER: list[tuple[str, str, str, str]] = []
_CM_CACHE_MAX = 250


def _cache_get(key):
    return _CM_CACHE.get(key)


def _cache_set(key, value):
    if key in _CM_CACHE:
        _CM_CACHE[key] = value
        return

    _CM_CACHE[key] = value
    _CM_CACHE_ORDER.append(key)

    if len(_CM_CACHE_ORDER) > _CM_CACHE_MAX:
        old = _CM_CACHE_ORDER.pop(0)
        _CM_CACHE.pop(old, None)


# -----------------------------
# Search jobs
# -----------------------------

@router.post("/search", response_class=HTMLResponse)
@observe()
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


# -----------------------------
# Analyze match
# -----------------------------

@router.post("/analyze", response_class=HTMLResponse)
@observe()
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

    cache_key = (str(user.id), str(cv.id), str(cv.updated_at), str(job_id))

    cached = _cache_get(cache_key)
    if cached:
        payload = dict(cached)
        payload["request"] = request
        return templates.TemplateResponse("partials/cm_match_panel.html", payload)

    langfuse = safe_langfuse_client()
    if langfuse:
        langfuse.update_current_trace(
            session_id=cm_trace_session_id(user.id, str(cv.id), str(job_id)),
            tags=["career_match", "analyze"],
            metadata={
                "endpoint": "/cm/analyze",
                "user_id": user.id,
                "cv_id": str(cv.id),
                "job_id": str(job_id),
                "job_title": job.get("title"),
                "job_company": job.get("company"),
            },
        )

    t0 = time.time()
    try:
        analysis = await analyze_career_match(cv_text, job_text)
    except Exception as e:
        print("Career match error:", e)
        analysis = {}
    dt_ms = int((time.time() - t0) * 1000)

    if langfuse:
        langfuse.update_current_trace(
            session_id=cm_trace_session_id(user.id, str(cv.id), str(job_id)),
            metadata={"latency_ms": dt_ms},
        )

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

    cache_payload = dict(context)
    cache_payload.pop("request", None)
    _cache_set(cache_key, cache_payload)

    return templates.TemplateResponse("partials/cm_match_panel.html", context)