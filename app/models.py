import datetime
import uuid
from sqlalchemy import Column, String, DateTime, LargeBinary, Float, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db import Base


class Challenge(Base):
    __tablename__ = "challenges"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    text = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # ✅ Many-to-one: Challenge → User
    user = relationship("User", back_populates="challenges")


class Company(Base):
    __tablename__ = "companies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, index=True)
    api_key = Column(String, unique=True, index=True)
    api_secret = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # ✅ Implicit backref: Company.users
    users = relationship("User", back_populates="company")


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    external_user_id = Column(String, index=True)   # company’s own user ID
    lang = Column(String, default="en")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # ✅ Relationships
    company = relationship("Company", back_populates="users")
    enrollments = relationship("Enrollment", back_populates="user")
    logs = relationship("VerificationLog", back_populates="user")
    challenges = relationship("Challenge", back_populates="user")


class Enrollment(Base):
    __tablename__ = "enrollments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    embedding = Column(LargeBinary, nullable=False)
    audio_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="enrollments")


class VerificationLog(Base):
    __tablename__ = "verification_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    phrase = Column(String)
    similarity = Column(Float)
    liveness_verified = Column(Boolean, default=False)
    identity_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    
    # ✅ New anti-spoof fields
    aasist_score = Column(Float, nullable=True)
    lcnn_score = Column(Float, nullable=True)
    cqcc_gmm_score = Column(Float, nullable=True)
    spoof_prob = Column(Float, nullable=True)

    user = relationship("User", back_populates="logs")
