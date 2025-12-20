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

class JobApplication(Base):
    __tablename__ = "job_applications"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    # Job details
    company = Column(String, nullable=False)
    role = Column(String, nullable=False)
    job_url = Column(String, nullable=True)
    
    # Application tracking
    applied_date = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="applied")  # applied, interview, rejected, offer, accepted
    
    # Follow-up
    follow_up_date = Column(DateTime, nullable=True)
    follow_up_completed = Column(Boolean, default=False)
    
    # Notes
    notes = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    user = relationship("User", backref="job_applications")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    role = Column(String, nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    
    # Store function calls if any
    function_call = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    user = relationship("User", backref="chat_messages")