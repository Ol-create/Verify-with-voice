from datetime import timedelta
from sqlalchemy.orm import Session
from fastapi import Depends, APIRouter, HTTPException, status
from uuid import UUID

from app.database import get_db
from app.models import User, Company
from app.schemas import TokenRequest, TokenResponse
from app.auth import create_access_token
from app.config import settings

router = APIRouter()

@router.post("/token", response_model=TokenResponse)
async def generate_token(payload: TokenRequest, db: Session = Depends(get_db)):
    """
    Generate JWT for a user under a specific company.
    """
    if not payload.user_id or not payload.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_id and company_id are required",
        )

    # Validate company
    company = db.query(Company).filter(Company.id == payload.company_id).first()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found",
        )

    # Find or create user under this company
    user = db.query(User).filter(
        User.external_user_id == payload.user_id,
        User.company_id == company.id
    ).first()

    if not user:
        user = User(
            company_id=company.id,
            external_user_id=payload.user_id,
            lang=payload.lang,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # update language preference
        user.lang = payload.lang
        db.commit()

    # Create token with UUIDs as strings
    access_token_expires = timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    access_token = create_access_token(
        data={
            "user_id": str(user.id),
            "company_id": str(company.id),
            "lang": user.lang,
        },
        expires_delta=access_token_expires,
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "lang": user.lang,
    }
