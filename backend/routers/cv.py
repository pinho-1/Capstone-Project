from fastapi import (
    APIRouter, Request, Depends, UploadFile, File, Form, BackgroundTasks
)
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from backend.database import get_db, SessionLocal
from backend.routers.auth import get_current_user
from backend.schemas.cv import TailorResponse
from backend.models.user_model import CV
from fastapi.templating import Jinja2Templates
import asyncio, uuid, os
import uuid

# AI + CV helpers
from backend.services.ai.cv_agent import (score_cv_with_ai, build_card_from_intent, generate_example,
    tailor_for_job, generate_center_insights)
from backend.services.cv_utils import extract_text_from_file

router = APIRouter()

FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "../frontend/pages"
)
templates = Jinja2Templates(directory=FRONTEND_DIR)

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

# ========== 0. VIEW DASHBOARD ==========
@router.get("/view/{cv_id}", response_class=HTMLResponse)
async def view_cv(request: Request, cv_id: str, db: Session = Depends(get_db)):
    """Displays the CV dashboard once analysis is ready."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth?error=login_required", status_code=303)

    cv = db.query(CV).filter(CV.id == cv_id, CV.user_id == user.id).first()
    if not cv:
        return RedirectResponse("/cv/upload", status_code=303)

    # 🧠 Save mentor context to session
    if cv.mentor_focus:
        request.session["mentor_focus"] = cv.mentor_focus

    return templates.TemplateResponse(
        "cv_dashboard.html",
        {"request": request, "cv": cv, "user": user, "current_path": request.url.path}
    )

# ========== 1. UPLOAD & PROCESS ==========

@router.post("/upload")
async def cv_upload(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth?error=login_required", status_code=303)

    # Read the file immediately (before background task starts)
    content_bytes = await file.read()

    # Create the DB entry
    cv_id = str(uuid.uuid4())
    cv_entry = CV(id=cv_id, user_id=user.id, status="processing")
    db.add(cv_entry)
    db.commit()

    # Pass bytes instead of the file object
    background_tasks.add_task(process_uploaded_cv, cv_id, file.filename, content_bytes)

    return RedirectResponse(f"/cv/view/{cv_id}", status_code=303)

def process_uploaded_cv(cv_id: str, filename: str, content_bytes: bytes):
    """Runs in background after upload."""
    db = SessionLocal()
    try:
        raw_text = asyncio.run(extract_text_from_file(content_bytes, filename))

        async def process():
            scores_task = asyncio.create_task(score_cv_with_ai(raw_text))
            mentor_task = asyncio.create_task(generate_center_insights(raw_text))
            return await asyncio.gather(scores_task, mentor_task)

        scores, mentor = asyncio.run(process())

        cv = db.query(CV).filter(CV.id == cv_id).first()
        if cv:
            cv.raw_text = raw_text
            cv.clarity_score = scores["clarity"]
            cv.impact_score = scores["impact"]
            cv.structure_score = scores["structure"]
            cv.language_score = scores["language"]
            cv.overall_score = scores["overall"]
            cv.reasons = scores.get("reasons")

            cv.mentor_summary = mentor["summary"]
            cv.mentor_strengths = mentor["strengths"]
            cv.mentor_improvements = mentor["improvements"]
            cv.mentor_focus = mentor["recommended_focus"]

            cv.status = "ready"
            db.commit()
            print(f"✅ CV {cv_id} processed successfully.")
    except Exception as e:
        print("Background AI task failed:", e)
    finally:
        db.close()


@router.get("/status/{cv_id}")
def cv_status(cv_id: str, db: Session = Depends(get_db)):
    cv = db.query(CV).filter(CV.id == cv_id).first()
    if not cv:
        return {"status": "not_found"}
    return {
        "status": cv.status,
        "scores": {
            "clarity": cv.clarity_score,
            "impact": cv.impact_score,
            "structure": cv.structure_score,
            "language": cv.language_score,
            "overall": cv.overall_score,
        } if cv.status == "ready" else None
    }


# ========== 2. DYNAMIC MENTOR CARDS ==========

SESSION_KEY = "topic_cards"
PROGRESS_KEY = "mentor_progress"

def get_cards(request: Request):
    return request.session.setdefault(SESSION_KEY, {})

def get_progress(request: Request):
    return request.session.setdefault(PROGRESS_KEY, {
        "completed": [],
        "dismissed": [],
        "suggested": []
    })

@router.post("/intent", response_class=HTMLResponse)
async def create_card(request: Request, intent: str = Form(...)):
    cv_text = request.session.get("uploaded_cv_text", "")
    card = await build_card_from_intent(intent, cv_text)
    cards = get_cards(request)
    cards[card["id"]] = card
    return templates.TemplateResponse(
        "partials/topic_card.html", {"request": request, "card": card}
    )


@router.post("/card/variant", response_class=HTMLResponse)
async def card_variant(request: Request, card_id: str = Form(...)):
    cards = get_cards(request)
    card = cards.get(card_id)
    if not card:
        return HTMLResponse("", status_code=204)
    card["example"] = await generate_example(card["playbook"], request.session.get("uploaded_cv_text", ""))
    return templates.TemplateResponse(
        "partials/topic_card.html", {"request": request, "card": card}
    )


@router.post("/card/accept", response_class=HTMLResponse)
async def card_accept(request: Request, card_id: str = Form(...)):
    cards = get_cards(request)
    progress = get_progress(request)
    card = cards.get(card_id)
    if not card:
        return HTMLResponse("", status_code=204)
    card["subtitle"] = "Marked as done ✓"
    card["tips"] = []
    progress["completed"].append(card["playbook"])
    return templates.TemplateResponse(
        "partials/topic_card.html", {"request": request, "card": card}
    )


@router.delete("/card", response_class=HTMLResponse)
async def card_delete(request: Request, card_id: str = Form(...)):
    cards = get_cards(request)
    progress = get_progress(request)
    card = cards.pop(card_id, None)
    if card:
        progress["dismissed"].append(card["playbook"])
    return HTMLResponse("", status_code=204)


@router.get("/next-action", response_class=HTMLResponse)
async def next_best_action(request: Request):
    progress = get_progress(request)
    cv_focus = request.session.get("mentor_focus")  # optional memory of last CV upload

    # Simple heuristic:
    already_done = set(progress["completed"] + progress["dismissed"])
    possible = ["impact", "summary", "structure", "language"]
    next_focus = next((p for p in possible if p not in already_done), None)

    if not next_focus:
        next_focus = "general"

    card = await build_card_from_intent(f"improve {next_focus}", "")
    return templates.TemplateResponse("partials/topic_card.html", {"request": request, "card": card})

# ========== 3. TAILOR FOR JOB (KEEP) ==========

@router.post("/tailor", response_model=TailorResponse)
async def cv_tailor(
    request: Request,
    db: Session = Depends(get_db),
    job_description: str = Form(...),
    job_title: str = Form(None),
    company: str = Form(None),
    doc_json: str = Form(None),
):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"detail": "login_required"}, status_code=401)
    suggestions = await tailor_for_job(job_description, job_title, company, doc_json)
    return JSONResponse(suggestions)
