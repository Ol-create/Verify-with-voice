from datetime import timedelta
from sqlalchemy.orm import Session
from fastapi import Depends, APIRouter, HTTPException, status, Header

from app.db import get_db
from app.models import User, Company
from app.schemas import TokenRequest, TokenResponse
from app.auth import create_access_token
from app.config import settings

router = APIRouter()

@router.post("/token", response_model=TokenResponse)
async def generate_token(
    payload: TokenRequest,
    db: Session = Depends(get_db),
    x_api_key: str = Header(..., alias="X-API-KEY"),
    x_api_secret: str = Header(..., alias="X-API-SECRET"),
):
    """
    Issue a JWT for a user.
    Requires company API key + secret in headers.
    """

    # ✅ Step 1: Verify company using API key/secret
    company = db.query(Company).filter(Company.api_key == x_api_key).first()
    if not company or company.api_secret != x_api_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API credentials",
        )

    # ✅ Step 2: Validate user payload
    if not payload.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_id is required",
        )

    # ✅ Step 3: Find or create user under this company
    user = (
        db.query(User)
        .filter(
            User.external_user_id == payload.user_id,
            User.company_id == company.id,
        )
        .first()
    )

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
        user.lang = payload.lang
        db.commit()

    # ✅ Step 4: Create short-lived JWT
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
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
