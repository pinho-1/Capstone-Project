import os
import io
import re
import json
import glob
import time
from statistics import mean
from datetime import datetime
from typing import Dict, Any, Tuple
from docx import Document
from PyPDF2 import PdfReader

# --- Extract text from uploaded CV file ---
async def extract_text_from_file(content_bytes: bytes, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower().strip()
    text = ""

    print("DEBUG filename:", filename)

    if ext in (".pdf", "pdf"):
        reader = PdfReader(io.BytesIO(content_bytes))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)

    elif ext in (".docx", ".doc"):
        try:
            doc = Document(io.BytesIO(content_bytes))
            text = "\n".join(p.text for p in doc.paragraphs)
        except Exception as e:
            raise ValueError(f"Could not read Word document: {e}")

    elif ext in (".txt", "txt"):
        text = content_bytes.decode("utf-8", errors="ignore")
    else:
        raise ValueError(f"Unsupported file type: '{ext}' — please upload a .pdf, .docx, or .txt file.")

    # --- Basic cleaning ---
    text = re.sub(r"\n\s*\n", "\n\n", text.strip())
    return text

# ========== CARD BUILDING HELPERS ==========

# --- Route intent to playbook ---
def route_intent(intent: str) -> str:
    t = intent.lower()
    if any(k in t for k in ["quantify", "metric", "impact", "results", "numbers", "kpi"]):
        return "impact"
    if any(k in t for k in ["summary", "profile", "objective", "headline", "pitch"]):
        return "summary"
    if any(k in t for k in ["structure", "order", "layout", "sections"]):
        return "structure"
    if any(k in t for k in ["buzzword", "concise", "language", "tone", "clarity"]):
        return "language"
    if any(k in t for k in ["skill", "skills", "stack", "tools", "technologies"]):
        return "skills"
    if any(k in t for k in ["project", "projects", "portfolio"]):
        return "projects"
    if any(k in t for k in ["ats", "keywords", "job description", "matching"]):
        return "ats"
    if any(k in t for k in ["format", "formatting", "dates", "consistency", "typo"]):
        return "formatting"
    if any(k in t for k in ["experience", "bullets", "bullet", "roles"]):
        return "experience"
    return "general"

# --- Title from playbook ---
def title_from_playbook(pb: str) -> str:
    return {
        "impact": "Strengthen Impact",
        "summary": "Sharpen Your Summary",
        "structure": "Refine Structure",
        "language": "Polish Language",
        "skills": "Tighten Skills Section",
        "projects": "Upgrade Project Story",
        "ats": "Improve ATS Match",
        "formatting": "Fix Formatting",
        "experience": "Improve Experience Bullets",
        "general": "Targeted Improvement",
    }.get(pb, "Mentor Insight")

# ========== SIGNAL NORMALIZER ===========
def normalize_signals(raw_signals, default_tone="neutral", limit=4):
    """
    Accepts:
      - list of dicts: {"label": "...", "tone": "positive|neutral|warning"}
      - list of strings: "Business impact"
    Returns: list of dicts with label+tone, deduped by label.
    """
    if not isinstance(raw_signals, list):
        return []

    out = []
    seen = set()
    for item in raw_signals:
        if isinstance(item, dict):
            label = str(item.get("label", "")).strip()
            tone = str(item.get("tone", default_tone)).strip().lower()
        elif isinstance(item, str):
            label = item.strip()
            tone = default_tone
        else:
            continue

        label = " ".join(label.split())
        if not label:
            continue

        if tone not in ("positive", "neutral", "warning"):
            tone = default_tone

        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"label": label, "tone": tone})

        if len(out) >= limit:
            break

    return out