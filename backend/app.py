import json
import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from backend.routers.interviews_api import router as interviews_api_router
import uuid

from backend.database import Base, engine, get_db
from backend.models.cv_model import CV
from backend.routers import auth, chat, cm, cv
from backend.routers.auth import get_current_user

load_dotenv()
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

app = FastAPI()


@app.on_event("startup")
def startup_db():
    """Create tables on startup. If DB is temporarily unavailable, don't crash."""
    try:
        Base.metadata.create_all(bind=engine)
    except OperationalError:
        logger.exception("Database not reachable on startup; will retry on first request if needed.")


# Static + templates
app.mount("/static", StaticFiles(directory=os.path.join(FRONTEND_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(FRONTEND_DIR, "pages"))

# Routers
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(cv.router, prefix="/cv", tags=["cv"])
app.include_router(interviews_api_router)
app.include_router(cm.router)
app.include_router(chat.router, prefix="/chat", tags=["chat"])


@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user,
            "welcome": request.query_params.get("welcome"),
            "goodbye": request.query_params.get("goodbye"),
            "updated": request.query_params.get("updated"),
            "current_path": request.url.path,
        },
    )


@app.get("/auth", response_class=HTMLResponse)
def auth_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("auth.html", {"request": request, "user": user})


@app.get("/about", response_class=HTMLResponse)
def about_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return templates.TemplateResponse(
        "about.html",
        {"request": request, "user": user, "current_path": request.url.path},
    )


@app.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)  # may be None (guest)
    return templates.TemplateResponse(
        "chat.html",
        {
            "request": request,
            "user": user,
            "is_guest": user is None,
            "current_path": request.url.path,
        },
    )


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
                "Software Development",
                "AI & Machine Learning",
                "Data Science",
                "Cybersecurity",
                "Cloud Computing",
                "Blockchain",
                "IT Support",
                "DevOps",
                "Data Engineering",
            ],
        },
        {
            "name": "Design & Creativity",
            "interests": [
                "Graphic Design",
                "UI/UX",
                "Product Design",
                "Animation",
                "Media Production",
                "Photography",
                "Illustration",
                "Game Design",
                "Creative Direction",
            ],
        },
        {
            "name": "Business & Leadership",
            "interests": [
                "Business Strategy",
                "Entrepreneurship",
                "Finance",
                "Project Management",
                "Operations",
                "Consulting",
                "Business Analytics",
                "Management",
            ],
        },
        {
            "name": "People & Communication",
            "interests": [
                "Marketing",
                "Public Relations",
                "Human Resources",
                "Education",
                "Sales",
                "Customer Support",
                "Content Creation",
                "Community Management",
            ],
        },
        {
            "name": "Health & Life Sciences",
            "interests": [
                "Healthcare",
                "Nursing",
                "Pharmacy",
                "Biotechnology",
                "Mental Health",
                "Nutrition",
                "Environmental Science",
                "Public Health",
                "Sports Science",
            ],
        },
        {
            "name": "Engineering & Manufacturing",
            "interests": [
                "Mechanical Engineering",
                "Electrical Engineering",
                "Civil Engineering",
                "Robotics",
                "Industrial Engineering",
                "Automotive",
                "Quality Assurance",
                "Aerospace",
            ],
        },
        {
            "name": "Social Impact & Public Sector",
            "interests": [
                "Nonprofit Work",
                "Government",
                "Social Work",
                "Policy & Advocacy",
                "International Relations",
                "Community Development",
                "Law",
            ],
        },
        {
            "name": "Arts, Culture & Media",
            "interests": [
                "Writing",
                "Music",
                "Film",
                "Performing Arts",
                "Cultural Studies",
                "History",
                "Journalism",
                "Languages",
                "Literature",
            ],
        },
        {
            "name": "Environment & Sustainability",
            "interests": [
                "Environmental Engineering",
                "Renewable Energy",
                "Sustainability Consulting",
                "Climate Science",
                "Wildlife & Conservation",
                "Urban Planning",
            ],
        },
    ]

    all_user_interests: list[str] = []
    other_interests: list[str] = []

    if user.interest:
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
    """Dependency wrapper for current user."""
    return get_current_user(request, db)


@app.post("/onboarding/submit", include_in_schema=False)
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

    all_interests = interest.split(",") if interest else []
    if other_interest:
        all_interests.append(other_interest.strip())

    user.career_stage = career_stage
    user.interest = ",".join(all_interests)
    user.goal = goal
    user.experience = experience
    user.focus = focus
    user.onboarding_complete = True
    db.commit()

    referrer = str(request.headers.get("referer", ""))
    if "update=true" in referrer:
        return RedirectResponse("/?updated=true", status_code=303)

    return RedirectResponse(f"/?welcome={user.name}", status_code=303)


@app.get("/cv", response_class=HTMLResponse)
def cv_entry_point(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth?error=login_required", status_code=303)

    cv_obj = (
        db.query(CV)
        .filter(CV.user_id == user.id)
        .order_by(CV.updated_at.desc(), CV.id.desc())
        .first()
    )

    if cv_obj:
        return RedirectResponse(f"/cv/view/{cv_obj.id}", status_code=303)

    return templates.TemplateResponse(
        "cv_upload.html",
        {"request": request, "user": user, "current_path": request.url.path},
    )


@app.get("/cm", response_class=HTMLResponse)
def career_match_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth?error=login_required", status_code=303)

    return templates.TemplateResponse(
        "career_match.html",
        {"request": request, "user": user, "current_path": request.url.path},
    )


def load_mock_jobs():
    path = os.path.join(os.path.dirname(__file__), "data", "mock_jobs.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/interviews", response_class=HTMLResponse)
def interviews_setup_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth?error=login_required", status_code=303)

    return templates.TemplateResponse(
        "interviews_setup.html",      # new template name
        {
            "request": request,
            "user": user,
            "current_path": request.url.path,
        },
    )

@app.post("/interviews/session", response_class=HTMLResponse)
async def interviews_session_page(
    request: Request,
    db: Session = Depends(get_db),
    job_role: str = Form(...),
    seniority: str = Form(...),
    language: str = Form(...),
    question_count: int = Form(...),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth?error=login_required", status_code=303)

    # ✅ CREATE SESSION ID HERE
    session_id = str(uuid.uuid4())

    return templates.TemplateResponse(
        "interviews_session.html",
        {
            "request": request,
            "user": user,
            "current_path": request.url.path,
            "role": job_role,
            "seniority": seniority,
            "language": language,
            "question_count": question_count,
            "session_id": session_id,  # ✅ PASS TO TEMPLATE
        },
    )

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "temporary_secret"),
    same_site="lax",
)