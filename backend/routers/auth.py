from fastapi import APIRouter, Request, Form, Depends, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from passlib.hash import bcrypt
from itsdangerous import URLSafeSerializer
from backend.database import get_db
from backend.models.user_model import User
from typing import Any
from fastapi.templating import Jinja2Templates
from backend.oauth import oauth
import os

router = APIRouter()

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "../frontend/pages")
templates = Jinja2Templates(directory=FRONTEND_DIR)

SECRET_KEY = "replace_with_env_secret"
serializer = URLSafeSerializer(SECRET_KEY, salt="session")

def create_session(response: Response, user_id: int):
    token = serializer.dumps({"user_id": user_id})
    response.set_cookie(
    key="user_session",  # different name from middleware
    value=token,
    httponly=True,
    max_age=60 * 60 * 24 * 7,
    samesite="none",
    secure=True,
    path="/"
)

def get_current_user(request: Request, db: Session) -> Any:
    token = request.cookies.get("user_session")
    if not token:
        return None
    try:
        data = serializer.loads(token)
        user = db.query(User).filter(User.id == data["user_id"]).first()
        return user
    except Exception:
        return None


@router.post("/signup")
def signup(
    response: Response,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    if db.query(User).filter_by(email=email).first():
        return RedirectResponse("/auth?error=email_exists", status_code=303)

    hashed_pw = bcrypt.hash(password)
    new_user = User(name=name, email=email, hashed_password=hashed_pw)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    redirect = RedirectResponse("/onboarding", status_code=303)
    create_session(redirect, new_user.id)
    return redirect


@router.post("/login")
def login(
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter_by(email=email).first()
    if not user or not bcrypt.verify(password, user.hashed_password):
        return RedirectResponse("/auth?error=invalid_credentials", status_code=303)

    if not user.onboarding_complete:
        redirect = RedirectResponse("/onboarding", status_code=303)
    else:
        redirect = RedirectResponse(f"/?welcome={user.name}", status_code=303)
    create_session(redirect, user.id)
    return redirect


@router.get("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    name = user.name if user else "friend"
    redirect = RedirectResponse(f"/?goodbye={name}", status_code=303)
    redirect.delete_cookie("user_session")
    return redirect

@router.get("/google/login")
async def google_login(request: Request):
    redirect_uri = request.url_for("google_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo")

    if not user_info:
        return RedirectResponse("/auth?error=google_failed", status_code=303)

    email = user_info["email"]
    name = user_info.get("name", email.split("@")[0])

    user = db.query(User).filter_by(email=email).first()
    if not user:
        user = User(name=name, email=email, hashed_password="")
        db.add(user)
        db.commit()
        db.refresh(user)

    if not user.onboarding_complete:
        redirect = RedirectResponse("/onboarding", status_code=303)
    else:
        redirect = RedirectResponse(f"/?welcome={user.name}", status_code=303)
    create_session(redirect, user.id)
    return redirect


@router.get("/github/login")
async def github_login(request: Request):
    redirect_uri = request.url_for("github_callback")
    return await oauth.github.authorize_redirect(request, redirect_uri)


@router.get("/github/callback")
async def github_callback(request: Request, db: Session = Depends(get_db)):
    token = await oauth.github.authorize_access_token(request)
    user_data = await oauth.github.get("user", token=token)
    user = user_data.json()

    email = user.get("email")
    if not email:
        emails_resp = await oauth.github.get("user/emails", token=token)
        emails = emails_resp.json()
        email = next((e["email"] for e in emails if e["primary"]), None)

    if not email:
        return RedirectResponse("/auth?error=github_no_email", status_code=303)

    name = user.get("name") or user.get("login")

    existing = db.query(User).filter_by(email=email).first()
    if not existing:
        existing = User(name=name, email=email, hashed_password="")
        db.add(existing)
        db.commit()
        db.refresh(existing)

    if not existing.onboarding_complete:
        redirect = RedirectResponse("/onboarding", status_code=303)
    else:
        redirect = RedirectResponse(f"/?welcome={existing.name}", status_code=303)
    create_session(redirect, existing.id)
    return redirect
