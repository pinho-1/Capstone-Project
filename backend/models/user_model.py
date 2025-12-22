from sqlalchemy import Boolean, Column, Integer, String, Text
from backend.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    career_stage = Column(String)
    interest = Column(String)
    goal = Column(String)
    experience = Column(Integer)
    focus = Column(Text)
    onboarding_complete = Column(Boolean, default=False)