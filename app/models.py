import datetime
import uuid
from sqlalchemy import Column, String, DateTime, LargeBinary, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db import Base

class Company(Base):
    __tablename__ = "companies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, index=True)
    api_key = Column(String, unique=True, index=True)
    api_secret = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"))
    external_user_id = Column(String, index=True)   # company’s own user ID
    lang = Column(String, default="en")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    company = relationship("Company", backref="users")
    enrollments = relationship("Enrollment", back_populates="user")
    logs = relationship("VerificationLog", back_populates="user")


class Enrollment(Base):
    __tablename__ = "enrollments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    embedding = Column(LargeBinary, nullable=False)
    audio_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="enrollments")


class VerificationLog(Base):
    __tablename__ = "verification_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    phrase = Column(String)
    similarity = Column(Float)
    liveness_verified = Column(String)   # or Boolean if you prefer
    identity_verified = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="logs")
