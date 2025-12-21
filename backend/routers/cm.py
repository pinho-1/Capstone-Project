from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.cv_model import CV
from backend.routers.auth import get_current_user
from backend.services.ai.career_match import analyze_career_match
import os, json

router = APIRouter(prefix="/cm", tags=["career_match"])

# -- Templates (igual ao cv.py) --
FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "../frontend/pages"
)
templates = Jinja2Templates(directory=FRONTEND_DIR)

# -- Mock jobs --
def load_mock_jobs():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "mock_jobs.json")
    path = os.path.abspath(path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# ========== /cm/search ==========
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
        if title_q and title_q not in job["title"].lower():
            continue
        if loc_q and loc_q not in job["location"].lower():
            continue
        if mode_q != "any":
            job_mode = job["mode"].lower()
            if mode_q not in job_mode:
                continue
        filtered.append(job)

    return templates.TemplateResponse(
        "partials/cm_job_results.html",   # ou "partials/cm_job_results.html" se já estiveres a usar partials
        {"request": request, "jobs": filtered},
    )

# ========== /cm/analyze ==========
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

    if not job:
        return templates.TemplateResponse(
            "partials/cm_match_panel.html",   # ou "partials/cm_match_panel.html"
            {
                "request": request,
                "job": None,
                "missing_cv": False,
                "cv_uploaded_at": None,
            },
        )

    cvs = (
        db.query(CV)
        .filter(
            CV.user_id == user.id,
            CV.raw_text != None,
            CV.raw_text != "",
        )
        .order_by(CV.updated_at.desc())
        .all()
    )
    cv = cvs[0] if cvs else None

    if not cv or not cv.raw_text:
        return templates.TemplateResponse(
            "partials/cm_match_panel.html",
            {
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
            },
        )

    cv_text = cv.raw_text
    cv_uploaded_at = cv.updated_at

    job_desc = job.get("description") or job.get("snippet") or ""
    job_text = f"{job.get('title', '')} at {job.get('company', '')}. {job_desc}"

    try:
        analysis = await analyze_career_match(cv_text, job_text)
    except Exception as e:
        print("Career match AI error:", e)
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
        "strengths": analysis.get("strengths", []),
        "gaps": analysis.get("gaps", []),
        "next_steps": analysis.get("next_steps", []),
        "skills_you_have": analysis.get("skills_you_have", []),
        "skills_missing": analysis.get("skills_missing", []),
        "reason": analysis.get(
            "reason",
            "Overall match estimated based on your CV compared to this role."
        ),
    }

    return templates.TemplateResponse("partials/cm_match_panel.html", context)
