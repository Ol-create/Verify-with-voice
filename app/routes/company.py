from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Company
from app.schemas import CompanySignupRequest
import secrets
import uuid

router = APIRouter()

@router.post("/companies/signup")
async def company_signup(payload: CompanySignupRequest, db: Session = Depends(get_db)):
    # Generate API key/secret
    api_key = secrets.token_hex(16)
    api_secret = secrets.token_hex(32)

    company = Company(
        id=uuid.uuid4(),
        name=payload.name,
        api_key=api_key,
        api_secret=api_secret,
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    return {
        "id": str(company.id),
        "name": company.name,
        "api_key": company.api_key,
        "api_secret": company.api_secret,
    }
