from fastapi import (
    APIRouter, Request, Depends, UploadFile, File, Form, BackgroundTasks, Query
)
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from backend.database import get_db, SessionLocal
from backend.routers.auth import get_current_user
from backend.models.cv_model import CV
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape
import re
import asyncio
import os
import uuid

# AI + CV helpers
from backend.services.ai.cv_agent import (score_cv_with_ai, build_card_from_intent, generate_example,
                             generate_center_insights, classify_document_is_cv)
from backend.services.cv_utils import extract_text_from_file, route_intent

router = APIRouter()

FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "../frontend/pages"
)
templates = Jinja2Templates(directory=FRONTEND_DIR)

def emphasize(text: str, highlights: list[str]):
    if not text or not highlights:
        return escape(text)

    raw = str(text)

    phrases = sorted(
        {p.strip() for p in highlights if isinstance(p, str) and p.strip()},
        key=len,
        reverse=True
    )

    result = raw
    replacements = 0
    MAX_REPLACEMENTS = 18

    for phrase in phrases:
        if replacements >= MAX_REPLACEMENTS:
            break

        pattern = re.compile(re.escape(phrase), re.IGNORECASE)

        def repl(match):
            nonlocal replacements
            if replacements >= MAX_REPLACEMENTS:
                return match.group(0)
            replacements += 1
            return f"<strong class='kw'>{match.group(0)}</strong>"

        result = pattern.sub(repl, result, count=2)

    result = result.replace("<strong class='kw'>", "%%KW_OPEN%%").replace("</strong>", "%%KW_CLOSE%%")
    result = escape(result)
    result = (str(result)
              .replace("%%KW_OPEN%%", "<strong class='kw'>")
              .replace("%%KW_CLOSE%%", "</strong>"))

    return Markup(result)

templates.env.filters["emphasize"] = emphasize

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

    request.session.pop("topic_cards", None)

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

    def normalize_signals(raw, default_tone="neutral", limit=6):
        if not isinstance(raw, list):
            return []
        out, seen = [], set()
        for item in raw:
            if isinstance(item, dict):
                label = str(item.get("label", "")).strip()
                tone = str(item.get("tone", default_tone)).strip().lower()
            elif isinstance(item, str):
                label, tone = item.strip(), default_tone
            else:
                continue

            label = " ".join(label.split())
            if not label:
                continue

            # lock tones to your CSS classes
            if tone not in ("positive", "neutral", "warning"):
                tone = default_tone

            k = label.lower()
            if k in seen:
                continue
            seen.add(k)
            out.append({"label": label, "tone": tone})
            if len(out) >= limit:
                break
        return out

    def set_not_cv_state(cv: CV):
        cv.is_cv = False
        cv.score_valid = False
        cv.score_note = "This upload is not a CV, so CV scoring is not applicable."

        cv.clarity_score = None
        cv.impact_score = None
        cv.structure_score = None
        cv.language_score = None
        cv.overall_score = None

        cv.reasons = {
            "clarity": "N/A (not a CV). Upload a resume format to score clarity.",
            "impact": "N/A (not a CV). Upload a resume format to score impact.",
            "structure": "N/A (not a CV). Upload a resume format to score structure.",
            "language": "N/A (not a CV). Upload a resume format to score language.",
        }

    try:
        raw_text = extract_text_from_file(content_bytes, filename)

        # 1) Classify: CV or NOT CV (no “maybe”)
        ai_class = asyncio.run(classify_document_is_cv(raw_text))
        is_cv = bool(ai_class.get("is_cv", True))  # default True if model misbehaves
        cv_signals = normalize_signals(ai_class.get("signals", []), default_tone="neutral", limit=4)

        # 2) Run scoring + mentor regardless (optional), but only APPLY scores if is_cv=True
        async def run_ai():
            scores_task = asyncio.create_task(score_cv_with_ai(raw_text))
            mentor_task = asyncio.create_task(generate_center_insights(raw_text))
            return await asyncio.gather(scores_task, mentor_task)

        scores, mentor = asyncio.run(run_ai())

        highlights = mentor.get("highlights", []) if isinstance(mentor, dict) else []
        if not isinstance(highlights, list):
            highlights = []
        highlights = [h.strip() for h in highlights if isinstance(h, str) and h.strip()]
        highlights = highlights[:8]

        strengths = mentor.get("strengths", []) if isinstance(mentor, dict) else []
        improvements = mentor.get("improvements", []) if isinstance(mentor, dict) else []
        strengths = strengths[:5] if isinstance(strengths, list) else []
        improvements = improvements[:5] if isinstance(improvements, list) else []
        summary = mentor.get("summary", "") if isinstance(mentor, dict) else ""
        focus = mentor.get("recommended_focus", "") if isinstance(mentor, dict) else ""
        mentor_signals = normalize_signals(
            mentor.get("signals", []) if isinstance(mentor, dict) else [],
            default_tone="neutral",
            limit=4
        )
        signals = normalize_signals(cv_signals + mentor_signals, default_tone="neutral", limit=6)

        # 3) Persist
        cv = db.query(CV).filter(CV.id == cv_id).first()
        if not cv:
            return

        cv.raw_text = raw_text
        cv.status = "ready"

        # store mentor content always (you want the middle panel to explain)
        cv.mentor_highlights = highlights
        cv.mentor_summary = summary
        cv.mentor_strengths = strengths
        cv.mentor_improvements = improvements
        cv.mentor_focus = focus

        # ensure a strong “Not a CV” signal if needed
        if not is_cv:
            signals = [s for s in signals if s.get("label", "").lower() != "not a cv"]
            signals.insert(0, {"label": "Not a CV", "tone": "warning"})
            signals = signals[:6]
        cv.mentor_signals = signals

        if is_cv:
            cv.is_cv = True
            cv.score_valid = True
            cv.score_note = None

            cv.clarity_score = int(scores.get("clarity", 60))
            cv.impact_score = int(scores.get("impact", 60))
            cv.structure_score = int(scores.get("structure", 60))
            cv.language_score = int(scores.get("language", 60))
            cv.overall_score = int(scores.get("overall", 60))
            cv.reasons = scores.get("reasons")

        else:
            set_not_cv_state(cv)

            # also override mentor copy to match the state (optional but recommended)
            cv.mentor_summary = (
                "This upload does not look like a CV/resume. "
                "Upload a resume format with clear sections like Experience, Education, and Skills."
            )
            cv.mentor_strengths = [
                "Content contains relevant information and technical detail.",
                "Clear effort to communicate work and outcomes."
            ]
            cv.mentor_improvements = [
                "Reformat into a CV structure (Experience, Education, Skills, Projects).",
                "Use bullet points with measurable achievements instead of paragraphs.",
                "Add or clearly surface contact info, links, and date ranges."
            ]
            cv.mentor_focus = "Convert this into a CV format and re-upload to get a real score."

        db.commit()
        print(f"✅ CV {cv_id} processed. is_cv={is_cv}")

    except Exception as e:
        print("Background AI task failed:", repr(e))
        try:
            cv = db.query(CV).filter(CV.id == cv_id).first()
            if cv:
                cv.status = "failed"
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


@router.get("/status/{cv_id}")
def cv_status(cv_id: str, db: Session = Depends(get_db)):
    cv = db.query(CV).filter(CV.id == cv_id).first()
    if not cv:
        return {"status": "not_found"}

    payload = {"status": cv.status}

    if cv.status == "ready":
        payload["scores"] = {
            "clarity": cv.clarity_score,
            "impact": cv.impact_score,
            "structure": cv.structure_score,
            "language": cv.language_score,
            "overall": cv.overall_score,
        }
        payload["signals"] = cv.mentor_signals

    elif cv.status == "failed":
        payload["error"] = "CV processing failed. Please try another file."

    return payload

# ========== 2. DYNAMIC MENTOR CARDS ==========

PROGRESS_KEY = "mentor_progress"
HISTORY_KEY = "mentor_history"

CARDS_STORE: dict[str, dict[str, dict]] = {}  # {sid: {card_id: card_dict}}

def get_sid(request: Request) -> str:
    sid = request.session.get("sid")
    if not sid:
        sid = str(uuid.uuid4())
        request.session["sid"] = sid
    return sid

def get_cards(request: Request) -> dict[str, dict]:
    sid = get_sid(request)
    return CARDS_STORE.setdefault(sid, {})

def get_progress(request: Request) -> dict:
    return request.session.get(PROGRESS_KEY, {"completed": [], "dismissed": [], "suggested": []})

def set_progress(request: Request, progress: dict) -> None:
    request.session[PROGRESS_KEY] = progress

def get_history(request: Request) -> dict:
    return request.session.get(HISTORY_KEY, {})  # {playbook: [history_items...]}

def set_history(request: Request, history: dict) -> None:
    request.session[HISTORY_KEY] = history

def is_done(card: dict) -> bool:
    return "Marked as done" in str(card.get("subtitle", ""))

def active_cards(cards: dict[str, dict]) -> list[dict]:
    return [c for c in cards.values() if c and not is_done(c)]

def active_playbooks(cards: dict[str, dict]) -> set[str]:
    return {c.get("playbook") for c in active_cards(cards) if c.get("playbook")}

def _push_history(request: Request, card: dict) -> None:
    """Save last few generations per playbook, including dimensions."""
    pb = card.get("playbook")
    if not pb:
        return

    history = get_history(request)
    history.setdefault(pb, [])

    ex_raw = card.get("_example_raw") or {}
    history[pb].append({
        "tips": list(card.get("tips", [])),
        "before": ex_raw.get("before", ""),
        "after": ex_raw.get("after", ""),
        "tips_dimension": card.get("_tips_dimension"),
        "example_dimension": card.get("_example_dimension"),
    })

    # keep short memory per playbook
    history[pb] = history[pb][-6:]
    set_history(request, history)


@router.post("/intent", response_class=HTMLResponse)
async def create_card(request: Request, intent: str = Form(...)):
    cv_text = request.session.get("uploaded_cv_text", "")

    playbook = route_intent(intent)
    history = get_history(request)
    avoid = history.get(playbook, [])

    card = await build_card_from_intent(intent, cv_text, avoid=avoid)

    cards = get_cards(request)
    cid = str(card["id"])
    card["id"] = cid
    card["source"] = "intent"
    cards[cid] = card

    return templates.TemplateResponse("partials/topic_card.html", {"request": request, "card": card})


@router.post("/card/variant", response_class=HTMLResponse)
async def card_variant(request: Request, card_id: str = Form(...)):
    cards = get_cards(request)
    cid = str(card_id)
    card = cards.get(cid)
    if not card:
        return HTMLResponse("", status_code=204)

    pb = card.get("playbook") or "general"
    history = get_history(request)
    avoid = history.get(pb, [])

    example_data = await generate_example(
        pb,
        request.session.get("uploaded_cv_text", ""),
        avoid=avoid
    )

    card["example"] = example_data["html"]
    card["_example_raw"] = {"before": example_data["before"], "after": example_data["after"]}
    card["_example_dimension"] = example_data.get("dimension")
    cards[cid] = card

    # You’re swapping only the innerHTML of #example-{{id}}, so return only the example html
    return HTMLResponse(card["example"])


@router.post("/card/accept", response_class=HTMLResponse)
async def card_accept(request: Request, card_id: str = Form(...)):
    cards = get_cards(request)
    progress = get_progress(request)

    cid = str(card_id)
    card = cards.get(cid)
    if not card:
        return HTMLResponse("", status_code=204)

    # Save what was shown so future generations can avoid it
    _push_history(request, card)

    card["subtitle"] = "Marked as done ✓"
    card["tips"] = []
    cards[cid] = card

    pb = card.get("playbook")
    if pb:
        progress["completed"].append(pb)
        # keep it tidy
        progress["completed"] = progress["completed"][-50:]
        set_progress(request, progress)

    return templates.TemplateResponse("partials/topic_card.html", {"request": request, "card": card})


@router.delete("/card", response_class=HTMLResponse)
async def card_delete(request: Request, card_id: str = Query(...)):
    cards = get_cards(request)
    progress = get_progress(request)

    cid = str(card_id)
    card = cards.pop(cid, None)

    # If card doesn't exist, just return ok
    if not card:
        return HTMLResponse("", status_code=200)

    # Save to history even if dismissed (so it still avoids repeats)
    _push_history(request, card)

    pb = card.get("playbook")
    if pb:
        progress["dismissed"].append(pb)
        progress["dismissed"] = progress["dismissed"][-50:]
        set_progress(request, progress)

    return HTMLResponse("", status_code=200)


@router.get("/next-action", response_class=HTMLResponse)
async def next_best_action(request: Request):
    progress = get_progress(request)
    cv_text = request.session.get("uploaded_cv_text", "")

    already_done = set(progress.get("completed", []) + progress.get("dismissed", []))

    cards = get_cards(request)
    already_open = active_playbooks(cards)

    possible = ["impact", "summary", "language", "structure", "skills", "projects", "ats", "formatting", "experience"]

    next_focus = next((p for p in possible if p not in already_done and p not in already_open), None)
    if next_focus is None:
        next_focus = next((p for p in possible if p not in already_done), "general")

    # IMPORTANT: use history avoid for that playbook too
    history = get_history(request)
    avoid = history.get(next_focus, [])

    card = await build_card_from_intent(f"improve {next_focus}", cv_text, avoid=avoid)
    card["source"] = "suggested"

    cid = str(card["id"])
    card["id"] = cid

    cards[cid] = card

    progress["suggested"].append(next_focus)
    progress["suggested"] = progress["suggested"][-50:]
    set_progress(request, progress)

    return templates.TemplateResponse("partials/topic_card.html", {"request": request, "card": card})