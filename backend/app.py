from fastapi import FastAPI, Request, Depends, Form, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from backend.database import Base, engine, get_db
from backend.models.user_model import User, CV 
from typing import Optional, Any
from backend.routers import auth, cv
from backend.routers.auth import get_current_user
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
import os
import json

load_dotenv()

Base.metadata.create_all(bind=engine)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

app = FastAPI()

# Static files
app.mount("/static", StaticFiles(directory=os.path.join(FRONTEND_DIR, "static")), name="static")

# Templates
templates = Jinja2Templates(directory=os.path.join(FRONTEND_DIR, "pages"))

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(cv.router, prefix="/cv", tags=["cv"])


# ---------------------
# ROUTES
# ---------------------

@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    welcome = request.query_params.get("welcome")
    goodbye = request.query_params.get("goodbye")
    updated = request.query_params.get("updated")
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user,
        "welcome": welcome,
        "goodbye": goodbye,
        "updated": updated
    })


@app.get("/auth", response_class=HTMLResponse)
def auth_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("auth.html", {"request": request, "user": user})

@app.get("/about", response_class=HTMLResponse)
def about_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return templates.TemplateResponse("about.html", {"request": request, "user": user})


@app.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth?error=login_required", status_code=303)
    return templates.TemplateResponse("chat.html", {"request": request, "user": user})

@app.get("/onboarding", response_class=HTMLResponse)
def onboarding_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)

    if not user:
        return RedirectResponse("/auth?error=login_required", status_code=303)

    update_mode = request.query_params.get("update") == "true"

    # Only skip onboarding if not updating
    if getattr(user, "onboarding_complete", False) and not update_mode:
        return RedirectResponse(f"/?welcome={user.name}", status_code=303)

    return templates.TemplateResponse(
        "onboarding.html",
        {"request": request, "user": user, "update_mode": update_mode}
    )

def current_user_dep(request: Request, db: Session = Depends(get_db)):
    """Wrapper so FastAPI can inject dependencies correctly."""
    return get_current_user(request, db)

@app.post("/onboarding/submit", response_model=None, include_in_schema=False)
def submit_onboarding(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(current_user_dep),
    career_stage: str = Form(None),
    interest: str = Form(None),
    goal: str = Form(None),
    experience: int = Form(None),
    focus: str = Form(None),
):
    if not user:
        return RedirectResponse("/auth?error=login_required", status_code=303)

    user.career_stage = career_stage
    user.interest = interest
    user.goal = goal
    user.experience = experience
    user.focus = focus
    user.onboarding_complete = True
    db.commit()

    # Detect update mode via referrer
    referrer = str(request.headers.get("referer", ""))
    if "update=true" in referrer:
        return RedirectResponse("/?updated=true", status_code=303)

    return RedirectResponse(f"/?welcome={user.name}", status_code=303)

@app.get("/cv", response_class=HTMLResponse)
def cv_upload_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth?error=login_required", status_code=303)
    return templates.TemplateResponse("cv_upload.html", {"request": request, "user": user})



#bruno
@app.get("/cm", response_class=HTMLResponse)
def career_match_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth?error=login_required", status_code=303)

    return templates.TemplateResponse("career_match.html", {
        "request": request,
        "user": user
    })


def load_mock_jobs():
    path = os.path.join(os.path.dirname(__file__), "data", "mock_jobs.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
    
@app.post("/cm/search", response_class=HTMLResponse)
async def cm_search(
    request: Request,
    title: str = Form(""),
    location: str = Form(""),
    mode: str = Form("any"),
):
    jobs = load_mock_jobs()

    title_q = title.lower().strip()
    loc_q = location.lower().strip()
    mode_q = mode.lower().strip()  # "any", "on-site", "hybrid", "remote"

    filtered = []
    for job in jobs:
        # Title filter
        if title_q and title_q not in job["title"].lower():
            continue

        # Location filter
        if loc_q and loc_q not in job["location"].lower():
            continue

        # Mode filter
        if mode_q != "any":
            # job["mode"] is "Hybrid", "Remote", "On-site"
            job_mode = job["mode"].lower()
            if mode_q not in job_mode:
                continue

        filtered.append(job)

    return templates.TemplateResponse(
        "cm_job_results.html",
        {
            "request": request,
            "jobs": filtered,
        },
    )

@app.post("/cm/analyze", response_class=HTMLResponse)
async def cm_analyze(
    request: Request,
    job_id: str = Form(...)
):
    # Load jobs and find the selected one
    jobs = load_mock_jobs()
    job = None
    for j in jobs:
        # ids in JSON are numbers, in form they come as string
        if str(j["id"]) == str(job_id):
            job = j
            break

    if not job:
        # fallback: simple error panel
        return templates.TemplateResponse(
            "cm_match_panel.html",
            {
                "request": request,
                "job": None,
                "match_score": 0,
                "seniority_fit": "Unknown",
                "skills_summary": "We couldn't find this job. Please try again.",
                "strengths": [],
                "gaps": [],
                "next_steps": [],
            },
        )

    # --- MOCK ANALYSIS (for now) ---

    # pretend we know the user's profile a bit
    # later you can pull this from DB / CV
    user_skills = {"sql", "excel", "dashboarding", "power bi", "python"}

    job_tags = {t.lower() for t in job.get("tags", [])}
    overlap = user_skills & job_tags
    overlap_ratio = len(overlap) / max(len(job_tags), 1)

    # simple match score between 55 and 90
    base = 55
    match_score = int(base + overlap_ratio * 35)

    if "junior" in job.get("level", "").lower():
        seniority_fit = "Good for your current level"
    elif "mid" in job.get("level", "").lower():
        seniority_fit = "Good match (mid-level)"
    else:
        seniority_fit = "Stretch role – might be challenging"

    if overlap:
        skills_summary = f"You already match {len(overlap)} of {len(job_tags)} key skills for this role."
    else:
        skills_summary = "Your CV doesn’t clearly show the core skills for this role yet."

    strengths = []
    if "sql" in overlap:
        strengths.append("Strong SQL basis for querying and manipulating data.")
    if "dashboarding" in overlap or "power bi" in overlap:
        strengths.append("Experience building dashboards and visual reports for stakeholders.")
    strengths.append("Good analytical mindset and interest in data-driven work (based on your target).")

    gaps = []
    if "experiments" in job_tags:
        gaps.append("Little explicit experience with A/B tests or experiments – consider adding 1–2 examples.")
    if "product" in job_tags:
        gaps.append("Limited product collaboration experience – emphasize any cross-functional work with PMs.")
    if not gaps:
        gaps.append("Clarify 1–2 concrete achievements with measurable impact in your CV.")

    next_steps = [
        "Add 2–3 bullet points in your CV that quantify impact (e.g. ‘improved X metric by Y%’).",
        "Highlight tools and technologies that match the job tags (SQL, BI tools, analytics platforms).",
        "Prepare 2–3 short stories about how you used data to support a decision or project.",
    ]

    return templates.TemplateResponse(
        "cm_match_panel.html",
        {
            "request": request,
            "job": job,
            "match_score": match_score,
            "seniority_fit": seniority_fit,
            "skills_summary": skills_summary,
            "strengths": strengths,
            "gaps": gaps,
            "next_steps": next_steps,
        },
    )


# ---------------------
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "temporary_secret"))