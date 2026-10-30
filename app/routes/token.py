import uuid
from datetime import timedelta, datetime
from sqlalchemy.orm import Session
from fastapi import Depends, APIRouter, HTTPException, Header
from app.db import get_db
from app.models import ApiCredential, User
from app.schemas import TokenRequest, TokenResponse, RefreshRequest
from app.auth import create_access_token, require_active_company
from app.config import settings
from app.utils.security import hash_credential, verify_credential
from jose import jwt, JWTError

router = APIRouter()


def _create_refresh_token(user: User, credential_id: str | None) -> str:
    """Create a refresh token and store only its hash on the user."""
    expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    refresh_token = jwt.encode(
        {
            "user_id": str(user.id),
            "company_id": str(user.company_id),
            "credential_id": credential_id,
            "type": "refresh",
            "exp": datetime.utcnow() + expires,
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    user.refresh_token = hash_credential(refresh_token)
    user.refresh_token_expiry = datetime.utcnow() + expires
    return refresh_token


@router.post("/token", response_model=TokenResponse)
async def generate_token(
    payload: TokenRequest,
    db: Session = Depends(get_db),
    x_api_key: str = Header(..., alias="X-API-KEY"),
    x_api_secret: str = Header(..., alias="X-API-SECRET"),
):
    """
    Issue access + refresh tokens for one of the company's end users.
    The company authenticates with one of its API keys and its secret; only their hashes are stored.
    """
    credential = (
        db.query(ApiCredential)
        .filter(ApiCredential.key_hash == hash_credential(x_api_key), ApiCredential.revoked_at.is_(None))
        .first()
    )
    if not credential or not verify_credential(x_api_secret, credential.secret_hash):
        raise HTTPException(status_code=401, detail="Invalid API key or secret")

    company = credential.company
    require_active_company(company)
    credential.last_used_at = datetime.utcnow()

    # company_id in the body is optional; the API key already identifies the company
    if payload.company_id and payload.company_id != company.id:
        raise HTTPException(status_code=403, detail="company_id does not match the API key")

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
    credential_id = str(credential.id)
    access_token = create_access_token(
        data={
            "user_id": str(user.id),
            "company_id": str(company.id),
            "credential_id": credential_id,
            "lang": user.lang,
        },
    )
    refresh_token = _create_refresh_token(user, credential_id)
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
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    if data.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    try:
        user_id = uuid.UUID(data.get("user_id"))
        company_id = uuid.UUID(data.get("company_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or revoked refresh token")

    user = (
        db.query(User)
        .filter(User.id == user_id, User.company_id == company_id)
        .first()
    )
    if (
        not user
        or not user.refresh_token
        or not verify_credential(payload.refresh_token, user.refresh_token)
    ):
        raise HTTPException(status_code=401, detail="Invalid or revoked refresh token")

    if user.refresh_token_expiry and user.refresh_token_expiry < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Refresh token expired")

    require_active_company(user.company)

    # Revoking an API key also ends the sessions it issued
    credential_id = data.get("credential_id")
    if credential_id:
        try:
            credential = db.get(ApiCredential, uuid.UUID(credential_id))
        except ValueError:
            credential = None
        if not credential or not credential.is_active or credential.company_id != user.company_id:
            raise HTTPException(status_code=401, detail="Invalid or revoked refresh token")

    access_token = create_access_token(
        data={
            "user_id": str(user.id),
            "company_id": str(user.company_id),
            "credential_id": credential_id,
            "lang": user.lang,
        },
    )

    return {
        "access_token": access_token,
        "refresh_token": payload.refresh_token,
        "token_type": "bearer",
        "lang": user.lang,
    }


@router.post("/token/revoke")
async def revoke_refresh_token(payload: RefreshRequest, db: Session = Depends(get_db)):
    user = (
        db.query(User)
        .filter(User.refresh_token == hash_credential(payload.refresh_token))
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="Token not found")

    user.refresh_token = None
    user.refresh_token_expiry = None
    db.commit()
    return {"detail": "Refresh token revoked successfully"}
