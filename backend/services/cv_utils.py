import os
import io
import re
import json
import glob
import time
from statistics import mean
from datetime import datetime
from typing import Dict, Any
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

# ========== CARD BUILDING HELPERS==========

# --- Route intent to playbook ---
def route_intent(intent: str) -> str:
    t = intent.lower()
    if any(k in t for k in ["quantify", "metric", "impact", "results"]):
        return "impact"
    if any(k in t for k in ["summary", "profile", "objective", "punchier"]):
        return "summary"
    if any(k in t for k in ["structure", "order", "layout", "sections"]):
        return "structure"
    if any(k in t for k in ["buzzword", "concise", "language", "tone", "clarity"]):
        return "language"
    return "general"

# --- Title from playbook ---
def title_from_playbook(pb: str) -> str:
    return {
        "impact": "Strengthen Impact",
        "summary": "Sharpen Your Summary",
        "structure": "Refine Structure",
        "language": "Polish Language",
        "general": "Targeted Improvement",
    }.get(pb, "Mentor Insight")
