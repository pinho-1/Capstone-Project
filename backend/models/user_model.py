from sqlalchemy import Boolean, Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from backend.database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"

    # Basic user fields
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    # Onboarding fields
    career_stage = Column(String)  # user's current career stage
    interest = Column(String)      # user's primary area of interest
    goal = Column(String)          # main goal for using the platform
    experience = Column(Integer)   # years of professional experience
    focus = Column(Text)           # open-ended focus area
    onboarding_complete = Column(Boolean, default=False)

class CV(Base):
    __tablename__ = "cvs"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String, default="processing")

    raw_text = Column(Text)

    clarity_score = Column(Integer, nullable=True)
    impact_score = Column(Integer, nullable=True)
    structure_score = Column(Integer, nullable=True)
    language_score = Column(Integer, nullable=True)
    overall_score = Column(Integer, nullable=True)
    reasons = Column(JSON, nullable=True)

    mentor_highlights = Column(JSON, nullable=True)
    mentor_summary = Column(Text, nullable=True)
    mentor_signals = Column(JSON, nullable=True)
    mentor_strengths = Column(JSON, nullable=True)
    mentor_improvements = Column(JSON, nullable=True)
    mentor_focus = Column(Text, nullable=True)

    is_cv = Column(Boolean, default=True)
    score_valid = Column(Boolean, default=True)
    score_note = Column(String, nullable=True)

    updated_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="cvs")
