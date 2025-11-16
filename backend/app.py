from fastapi import FastAPI, Request, Depends, Form, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from backend.database import Base, engine, get_db
from backend.models.user_model import User, CV 
from typing import Optional, Any
from backend.routers import auth, cv
from backend.routers.auth import get_current_user
from backend.services.ai.career_match import analyze_career_match
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

# Get Path
def get_current_path(request: Request):
    return request.url.path

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
        "updated": updated,
        "current_path": request.url.path
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
    return templates.TemplateResponse("about.html", {"request": request, "user": user, "current_path": request.url.path,})


@app.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth?error=login_required", status_code=303)
    return templates.TemplateResponse("chat.html", {"request": request, "user": user, "current_path": request.url.path,})

@app.get("/onboarding", response_class=HTMLResponse)
def onboarding_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)

    if not user:
        return RedirectResponse("/auth?error=login_required", status_code=303)

    update_mode = request.query_params.get("update") == "true"

    if getattr(user, "onboarding_complete", False) and not update_mode:
        return RedirectResponse(f"/?welcome={user.name}", status_code=303)

    categories = [
        {
            "name": "Technology & Data",
            "interests": [
                "Software Development", "AI & Machine Learning", "Data Science", "Cybersecurity",
                "Cloud Computing", "Blockchain", "IT Support", "DevOps", "Data Engineering"
            ],
        },
        {
            "name": "Design & Creativity",
            "interests": [
                "Graphic Design", "UI/UX", "Product Design", "Animation",
                "Media Production", "Photography", "Illustration",
                "Game Design", "Creative Direction"
            ],
        },
        {
            "name": "Business & Leadership",
            "interests": [
                "Business Strategy", "Entrepreneurship", "Finance",
                "Project Management", "Operations", "Consulting",
                "Business Analytics", "Management"
            ],
        },
        {
            "name": "People & Communication",
            "interests": [
                "Marketing", "Public Relations", "Human Resources",
                "Education", "Sales", "Customer Support",
                "Content Creation", "Community Management"
            ],
        },
        {
            "name": "Health & Life Sciences",
            "interests": [
                "Healthcare", "Nursing", "Pharmacy", "Biotechnology",
                "Mental Health", "Nutrition", "Environmental Science",
                "Public Health", "Sports Science"
            ],
        },
        {
            "name": "Engineering & Manufacturing",
            "interests": [
                "Mechanical Engineering", "Electrical Engineering", "Civil Engineering",
                "Robotics", "Industrial Engineering", "Automotive",
                "Quality Assurance", "Aerospace"
            ],
        },
        {
            "name": "Social Impact & Public Sector",
            "interests": [
                "Nonprofit Work", "Government", "Social Work",
                "Policy & Advocacy", "International Relations",
                "Community Development", "Law"
            ],
        },
        {
            "name": "Arts, Culture & Media",
            "interests": [
                "Writing", "Music", "Film", "Performing Arts",
                "Cultural Studies", "History", "Journalism",
                "Languages", "Literature"
            ],
        },
        {
            "name": "Environment & Sustainability",
            "interests": [
                "Environmental Engineering", "Renewable Energy",
                "Sustainability Consulting", "Climate Science",
                "Wildlife & Conservation", "Urban Planning"
            ],
        },
    ]

    # ---- split predefined vs "other" interests for this user ----
    all_user_interests: list[str] = []
    other_interests: list[str] = []

    if user and user.interest:
        all_user_interests = [s.strip() for s in user.interest.split(",") if s.strip()]
        predefined_set = {i for cat in categories for i in cat["interests"]}
        other_interests = [i for i in all_user_interests if i not in predefined_set]

    return templates.TemplateResponse(
        "onboarding.html",
        {
            "request": request,
            "user": user,
            "update_mode": update_mode,
            "categories": categories,
            "user_interests": all_user_interests,
            "other_interests": other_interests,
        },
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
    other_interest: str = Form(None),
):
    if not user:
        return RedirectResponse("/auth?error=login_required", status_code=303)

    # Combine predefined interests and custom ones
    all_interests = interest.split(",") if interest else []
    
    # Add the custom "other" interest
    if other_interest:
        all_interests.append(other_interest.strip())
    
    # Save the combined interests back to the user
    user.career_stage = career_stage
    user.interest = ",".join(all_interests)
    user.goal = goal
    user.experience = experience
    user.focus = focus
    user.onboarding_complete = True
    db.commit()

    # Redirect after submitting the form
    referrer = str(request.headers.get("referer", ""))
    if "update=true" in referrer:
        return RedirectResponse("/?updated=true", status_code=303)

    return RedirectResponse(f"/?welcome={user.name}", status_code=303)


@app.get("/cv", response_class=HTMLResponse)
def cv_upload_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth?error=login_required", status_code=303)
    return templates.TemplateResponse("cv_upload.html", {"request": request, "user": user, "current_path": request.url.path})



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
    job_id: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth?error=login_required", status_code=303)

    # 1. Find the selected job in mock data
    jobs = load_mock_jobs()
    job = next((j for j in jobs if str(j.get("id")) == str(job_id)), None)

    if not job:
        # Something’s odd with this job id
        return templates.TemplateResponse(
            "cm_match_panel.html",
            {
                "request": request,
                "job": None,
                "missing_cv": False,
            },
        )

    # 2. Grab MOST RECENT valid CV for this user
    cvs = (
        db.query(CV)
        .filter(
            CV.user_id == user.id,
            CV.raw_text != None,
            CV.raw_text != ""
        )
        .order_by(CV.updated_at.desc())
        .all()
    )

    cv = cvs[0] if cvs else None

    if not cv:
        return templates.TemplateResponse(
            "cm_match_panel.html",
            {
                "request": request,
                "job": job,
                "missing_cv": True,
                "match_score": "?",
                "seniority_fit": "",
                "skills_summary": "",
                "strengths": [],
                "gaps": [],
                "next_steps": [],
            },
        )


    cv_text = cv.raw_text

    # 3. Build a single job_text string for the AI
    job_desc = job.get("description") or job.get("snippet") or ""
    job_text = f"{job.get('title', '')} at {job.get('company', '')}. {job_desc}"

    # 4. Call AI safely (no keyword args; just positional)
    try:
        # Adjust this if your analyze_career_match signature is different
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
        "match_score": analysis.get("match_score", "?"),
        "seniority_fit": analysis.get("seniority_fit", "Fit not determined"),
        "skills_summary": analysis.get("skills_summary", "Skill alignment not available"),
        "strengths": analysis.get("strengths", []),
        "gaps": analysis.get("gaps", []),
        "next_steps": analysis.get("next_steps", []),
    }

    return templates.TemplateResponse("cm_match_panel.html", context)
# ---------------------
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "temporary_secret"))