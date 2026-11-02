# app/services/companies.py
"""Company onboarding and look-ups shared by the admin API and scripts/manage_company.py."""
import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import COMPANY_ACTIVE, ApiCredential, Company, Enrollment, User, VerificationLog
from app.services.credentials import issue_credential


class CompanyExists(Exception):
    pass


def find_by_name(db: Session, name: str) -> Company | None:
    """Case-insensitive, so "Acme" and "acme" can't both be onboarded."""
    return db.query(Company).filter(func.lower(Company.name) == name.strip().lower()).first()


def create_company(
    db: Session, name: str, email: str | None = None, status: str = COMPANY_ACTIVE
) -> tuple[Company, ApiCredential, str, str]:
    """
    Create a company with its first API key. Returns (company, credential, api_key, api_secret);
    the plaintext key and secret are only available here. The caller commits.
    """
    name = name.strip()
    if find_by_name(db, name):
        raise CompanyExists(name)
    company = Company(name=name, email=email.strip().lower() if email else None, status=status)
    db.add(company)
    credential, api_key, api_secret = issue_credential(db, company)
    return company, credential, api_key, api_secret


def month_start(now: datetime.datetime | None = None) -> datetime.datetime:
    now = now or datetime.datetime.utcnow()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def usage_since(db: Session, company_id, since: datetime.datetime) -> dict:
    """
    Voice activity for a company since a date, from verification logs and final enrollments.
    (Replaced by usage records once metering lands in T1.4.)
    """
    verifications, succeeded = (
        db.query(
            func.count(VerificationLog.id),
            func.count(VerificationLog.id).filter(
                VerificationLog.identity_verified.is_(True), VerificationLog.liveness_verified.is_(True)
            ),
        )
        .join(User, User.id == VerificationLog.user_id)
        .filter(User.company_id == company_id, VerificationLog.created_at >= since)
        .one()
    )
    enrollments = (
        db.query(func.count(Enrollment.id))
        .join(User, User.id == Enrollment.user_id)
        .filter(User.company_id == company_id, Enrollment.is_final.is_(True), Enrollment.created_at >= since)
        .scalar()
    )
    return {
        "since": since,
        "verifications": verifications,
        "verifications_succeeded": succeeded,
        "enrollments_completed": enrollments,
    }
