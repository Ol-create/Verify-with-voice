import datetime
from sqlalchemy import Column, String, Integer, DateTime, LargeBinary, Float
from app.db import Base

class Enrollment(Base):
    __tablename__ = "enrollments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    embedding = Column(LargeBinary, nullable=False)
    audio_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class VerificationLog(Base):
    __tablename__ = "verification_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    phrase = Column(String)
    similarity = Column(Float)
    liveness_verified = Column(Integer)   # could also be Boolean
    identity_verified = Column(Integer)   # could also be Boolean
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
