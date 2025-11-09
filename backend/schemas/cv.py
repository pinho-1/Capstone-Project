from pydantic import BaseModel
from typing import List, Optional

class Section(BaseModel):
    name: str
    text: str

class DocPayload(BaseModel):
    sections: List[Section]

class MentorAnalysis(BaseModel):
    summary: str
    strengths: List[str]
    improvements: List[str]
    recommended_focus: str

class TailorRequest(BaseModel):
    job_description: str
    job_title: Optional[str] = None
    company: Optional[str] = None
    doc_json: Optional[DocPayload] = None

class TailorSuggestion(BaseModel):
    section: str
    original: Optional[str] = None
    improved: Optional[str] = None
    why: Optional[str] = None
    keywords: Optional[List[str]] = None

class TailorResponse(BaseModel):
    suggestions: List[TailorSuggestion]
    matched_keywords: List[str]
