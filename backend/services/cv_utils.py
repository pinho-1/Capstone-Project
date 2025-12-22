import io
import os
import re

from docx import Document
from PyPDF2 import PdfReader
from markupsafe import escape


def extract_text_from_file(content_bytes: bytes, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower().strip()

    if ext == ".pdf":
        reader = PdfReader(io.BytesIO(content_bytes))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)

    elif ext == ".docx":
        doc = Document(io.BytesIO(content_bytes))
        text = "\n".join(p.text for p in doc.paragraphs)

    elif ext == ".txt":
        text = content_bytes.decode("utf-8", errors="ignore")

    elif ext == ".doc":
        raise ValueError("Unsupported file type '.doc'. Please upload .docx instead.")

    else:
        raise ValueError(f"Unsupported file type: '{ext}' — upload .pdf, .docx, or .txt.")

    text = re.sub(r"\n\s*\n", "\n\n", text.strip())
    return text


def route_intent(intent: str) -> str:
    t = (intent or "").lower()

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


def render_example_html(before: str, after: str) -> str:
    before = escape(before or "")
    after = escape(after or "")

    return f"""
<div class="example-spotlight">
  <div class="after-spot">
    <div class="ba-label">After</div>
    <div class="ba-text">{after}</div>
  </div>

  <details class="before-drop">
    <summary>See original</summary>
    <div class="before-box">
      <div class="ba-label">Before</div>
      <div class="ba-text">{before}</div>
    </div>
  </details>
</div>
""".strip()


def normalize_signals(raw_signals, default_tone="neutral", limit=4):
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