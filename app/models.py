import datetime
import uuid
from sqlalchemy import (
    Column,
    String,
    DateTime,
    LargeBinary,
    Float,
    ForeignKey,
    Boolean,
    Integer,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db import Base


class Challenge(Base):
    __tablename__ = "challenges"
    __mapper_args__ = {"confirm_deleted_rows": False}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    text = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # ✅ Many-to-one: Challenge → User
    user = relationship("User", back_populates="challenges")


COMPANY_PENDING = "pending"  # signed up, not yet approved or paid
COMPANY_ACTIVE = "active"
COMPANY_SUSPENDED = "suspended"
COMPANY_STATUSES = (COMPANY_PENDING, COMPANY_ACTIVE, COMPANY_SUSPENDED)


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'active', 'suspended')", name="ck_companies_status"
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, index=True)
    email = Column(String, nullable=True)
    # Only active companies can get tokens
    status = Column(String(16), nullable=False, default=COMPANY_ACTIVE, server_default=COMPANY_ACTIVE)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # ✅ One-to-many: Company → Users
    users = relationship("User", back_populates="company")
    credentials = relationship("ApiCredential", back_populates="company", cascade="all, delete-orphan")


class ApiCredential(Base):
    """
    One API key + secret pair. A company can hold several, so keys can be rotated
    without downtime: create a new one, deploy it, then revoke the old one.
    Only hashes are stored; see app/utils/security.py
    """
    __tablename__ = "api_credentials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name = Column(String(64), nullable=False, default="default")
    key_prefix = Column(String(16), nullable=False)  # non-secret, for display
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    secret_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)

    company = relationship("Company", back_populates="credentials")

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


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
    # refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    refresh_token = Column(String, nullable=True)
    refresh_token_expiry = Column(DateTime, nullable=True)


class Enrollment(Base):
    __tablename__ = "enrollments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    embedding = Column(LargeBinary, nullable=False)
    audio_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # 🆕 Add these fields here (not in User)
    enroll_stage = Column(Integer, default=1)  # 1, 2, or 3
    is_final = Column(Boolean, default=False)  # True only for averaged embedding

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

    # ✅ Anti-spoof fields
    aasist_score = Column(Float, nullable=True)
    lcnn_score = Column(Float, nullable=True)
    cqcc_gmm_score = Column(Float, nullable=True)
    spoof_prob = Column(Float, nullable=True)

    user = relationship("User", back_populates="logs")


class AdminUser(Base):
    """A TrueVoice staff account for the admin dashboard."""
    __tablename__ = "admin_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, nullable=False, unique=True, index=True)  # stored lowercase
    password_hash = Column(String, nullable=False)  # bcrypt; see app/utils/passwords.py
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)
