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

    # Raw extracted text
    raw_text = Column(Text)

    # Scores (as before)
    clarity_score = Column(Integer)
    impact_score = Column(Integer)
    structure_score = Column(Integer)
    language_score = Column(Integer)
    overall_score = Column(Integer)
    reasons = Column(JSON, nullable=True)

    # Mentor analysis (new)
    mentor_summary = Column(Text, nullable=True)
    mentor_strengths = Column(JSON, nullable=True)
    mentor_improvements = Column(JSON, nullable=True)
    mentor_focus = Column(Text, nullable=True)

    updated_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="cvs")

