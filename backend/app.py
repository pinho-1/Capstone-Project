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



# ---------------------
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "temporary_secret"))