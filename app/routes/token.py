from datetime import timedelta, datetime
from sqlalchemy.orm import Session
from fastapi import Depends, APIRouter, HTTPException, Header
from app.db import get_db
from app.models import User, Company
from app.schemas import TokenRequest, TokenResponse, RefreshRequest
from app.auth import create_access_token
from app.config import settings
from app.utils.security import encrypt_secret, decrypt_secret  # ✅ encryption utils
from jose import jwt, JWTError

router = APIRouter()
REFRESH_TOKEN_EXPIRE_DAYS = 30


@router.post("/token", response_model=TokenResponse)
async def generate_token(
    payload: TokenRequest,
    db: Session = Depends(get_db),
    x_api_key: str = Header(..., alias="X-API-KEY"),
    x_api_secret: str = Header(..., alias="X-API-SECRET"),
):
    """
    Authenticate using encrypted API credentials.
    Accepts raw X-API-KEY and X-API-SECRET, decrypts stored values, 
    and compares them directly.
    """

    # ✅ Retrieve the company using encrypted key (cannot query by raw)
    companies = db.query(Company).all()

    company = None
    for c in companies:
        try:
            decrypted_key = decrypt_secret(c.api_key)
            if decrypted_key == x_api_key:
                company = c
                break
        except Exception:
            continue

    if not company:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # ✅ Verify secret
    try:
        decrypted_secret = decrypt_secret(company.api_secret)
        if decrypted_secret != x_api_secret:
            raise HTTPException(status_code=401, detail="Invalid API secret")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid API secret")

    if not payload.user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    # --- Find or create user ---
    user = (
        db.query(User)
        .filter(User.external_user_id == payload.user_id, User.company_id == company.id)
        .first()
    )

    if not user:
        user = User(
            company_id=company.id,
            external_user_id=payload.user_id,
            lang=payload.lang or "en",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    elif not user.lang and payload.lang:
        user.lang = payload.lang
        db.commit()

    # --- Token Generation ---
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    access_token = create_access_token(
        data={"user_id": str(user.id), "company_id": str(company.id), "lang": user.lang},
        expires_delta=access_token_expires,
    )

    refresh_token_payload = {
        "user_id": str(user.id),
        "company_id": str(company.id),
        "type": "refresh",
        "exp": datetime.utcnow() + refresh_token_expires,
    }

    refresh_token = jwt.encode(
        refresh_token_payload,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    # --- Save refresh token in DB ---
    user.refresh_token = refresh_token
    user.refresh_token_expiry = datetime.utcnow() + refresh_token_expires
    db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "lang": user.lang,
    }


@router.post("/token/refresh", response_model=TokenResponse)
async def refresh_access_token(payload: RefreshRequest, db: Session = Depends(get_db)):
    try:
        data = jwt.decode(
            payload.refresh_token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        if data.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user_id = data.get("user_id")
    company_id = data.get("company_id")

    user = (
        db.query(User)
        .filter(User.id == user_id, User.company_id == company_id)
        .first()
    )
    if not user or user.refresh_token != payload.refresh_token:
        raise HTTPException(status_code=401, detail="Invalid or revoked refresh token")

    if user.refresh_token_expiry and user.refresh_token_expiry < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Refresh token expired")

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"user_id": str(user.id), "company_id": str(company_id), "lang": user.lang},
        expires_delta=access_token_expires,
    )

    return {
        "access_token": access_token,
        "refresh_token": payload.refresh_token,
        "token_type": "bearer",
        "lang": user.lang,
    }


@router.post("/token/revoke")
async def revoke_refresh_token(payload: RefreshRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.refresh_token == payload.refresh_token).first()
    if not user:
        raise HTTPException(status_code=404, detail="Token not found")

    user.refresh_token = None
    user.refresh_token_expiry = None
    db.commit()
    return {"detail": "Refresh token revoked successfully"}
