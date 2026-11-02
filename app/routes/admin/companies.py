# app/routes/admin/companies.py
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.db import get_db
from app.models import AdminUser, ApiCredential, Company, User
from app.routes.admin.schemas import (
    CompanyCreate,
    CompanyCreated,
    CompanyDetail,
    CompanyPage,
    CompanyStatus,
    CompanyUpdate,
)
from app.services.companies import CompanyExists, create_company, find_by_name, month_start, usage_since

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_company(db: Session, company_id: uuid.UUID) -> Company:
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


def _detail(db: Session, company: Company) -> dict:
    user_count = db.query(func.count(User.id)).filter(User.company_id == company.id).scalar()
    return {
        "id": company.id,
        "name": company.name,
        "email": company.email,
        "status": company.status,
        "created_at": company.created_at,
        "user_count": user_count,
        "credentials": sorted(company.credentials, key=lambda c: c.created_at, reverse=True),
        "usage_this_month": usage_since(db, company.id, month_start()),
    }


@router.post("", response_model=CompanyCreated, status_code=status.HTTP_201_CREATED)
async def onboard_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """Create a company and its first API key. The key and secret are in this response only."""
    try:
        company, _, api_key, api_secret = create_company(db, payload.name, payload.email, payload.status)
    except CompanyExists:
        raise HTTPException(status_code=409, detail="A company with this name already exists")
    db.commit()
    logger.info("Admin %s onboarded company %s (%s)", admin.email, company.name, company.id)
    return {"company": _detail(db, company), "api_key": api_key, "api_secret": api_secret}


@router.get("", response_model=CompanyPage)
async def list_companies(
    status_filter: CompanyStatus | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, max_length=200, description="Search name or email"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    user_counts = (
        db.query(User.company_id, func.count(User.id).label("n"))
        .group_by(User.company_id)
        .subquery()
    )
    key_counts = (
        db.query(ApiCredential.company_id, func.count(ApiCredential.id).label("n"))
        .filter(ApiCredential.revoked_at.is_(None))
        .group_by(ApiCredential.company_id)
        .subquery()
    )

    query = db.query(Company)
    if status_filter:
        query = query.filter(Company.status == status_filter)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        query = query.filter(or_(Company.name.ilike(pattern), Company.email.ilike(pattern)))
    total = query.count()

    rows = (
        query.outerjoin(user_counts, user_counts.c.company_id == Company.id)
        .outerjoin(key_counts, key_counts.c.company_id == Company.id)
        .add_columns(func.coalesce(user_counts.c.n, 0), func.coalesce(key_counts.c.n, 0))
        .order_by(Company.created_at.desc(), Company.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        {
            "id": c.id,
            "name": c.name,
            "email": c.email,
            "status": c.status,
            "created_at": c.created_at,
            "user_count": user_count,
            "active_key_count": key_count,
        }
        for c, user_count, key_count in rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{company_id}", response_model=CompanyDetail)
async def get_company(
    company_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    return _detail(db, _get_company(db, company_id))


@router.patch("/{company_id}", response_model=CompanyDetail)
async def update_company(
    company_id: uuid.UUID,
    payload: CompanyUpdate,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """Edit name or email, or set status to activate / suspend. Suspending takes effect immediately."""
    company = _get_company(db, company_id)
    changes = payload.model_dump(exclude_unset=True)

    new_name = changes.get("name")
    if new_name and new_name.lower() != company.name.lower() and find_by_name(db, new_name):
        raise HTTPException(status_code=409, detail="A company with this name already exists")
    if "email" in changes and changes["email"]:
        changes["email"] = changes["email"].lower()

    for field, value in changes.items():
        setattr(company, field, value)
    db.commit()
    if changes:
        logger.info("Admin %s updated company %s: %s", admin.email, company.id, ", ".join(sorted(changes)))
    return _detail(db, company)
