from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from backend.database import Base
from datetime import datetime

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    role = Column(String, nullable=False)  # user | assistant
    content = Column(Text, nullable=False)
    function_call = Column(JSON, nullable=True)
    agent_name = Column(String(32), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="chat_messages")
    
class JobApplication(Base):
    __tablename__ = "job_applications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    company = Column(String, nullable=False)
    role = Column(String, nullable=False)
    job_url = Column(String, nullable=True)

    applied_date = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="applied")

    follow_up_date = Column(DateTime, nullable=True)
    follow_up_completed = Column(Boolean, default=False)

    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", backref="job_applications")
