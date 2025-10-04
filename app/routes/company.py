import uuid
import secrets
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Company

router = APIRouter()

@router.post("/companies/signup")
async def register_company(name: str, db: Session = Depends(get_db)):
    """
    Register a new company and return API credentials.
    """

    # check if company already exists
    existing = db.query(Company).filter(Company.name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Company already exists")

    # generate API key + secret
    api_key = f"comp_{uuid.uuid4().hex[:16]}"
    api_secret = secrets.token_urlsafe(32)  # secure random secret

    company = Company(
        name=name,
        api_key=api_key,
        api_secret=api_secret,
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    # Return credentials once (do not expose secret in any GET route)
    return {
        "company_id": str(company.id),
        "api_key": company.api_key,
        "api_secret": company.api_secret,
    }
