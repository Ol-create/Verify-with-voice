# from datetime import timedelta
# from sqlalchemy.orm import Session
# from fastapi import Depends, APIRouter, HTTPException, status, Header

# from app.db import get_db
# from app.models import User, Company
# from app.schemas import TokenRequest, TokenResponse
# from app.auth import create_access_token
# from app.config import settings

# router = APIRouter()

# @router.post("/token", response_model=TokenResponse)
# async def generate_token(
#     payload: TokenRequest,
#     db: Session = Depends(get_db),
#     x_api_key: str = Header(..., alias="X-API-KEY"),
#     x_api_secret: str = Header(..., alias="X-API-SECRET"),
# ):
#     """
#     Issue a JWT for a user.
#     Requires company API key + secret in headers.
#     """

#     # ✅ Step 1: Verify company using API key/secret
#     company = db.query(Company).filter(Company.api_key == x_api_key).first()
#     if not company or company.api_secret != x_api_secret:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Invalid API credentials",
#         )

#     # ✅ Step 2: Validate user payload
#     if not payload.user_id:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="user_id is required",
#         )

#     # ✅ Step 3: Find or create user under this company
#     user = (
#         db.query(User)
#         .filter(
#             User.external_user_id == payload.user_id,
#             User.company_id == company.id,
#         )
#         .first()
#     )

#     if not user:
#         # 🆕 Save language only on first token creation
#         user = User(
#             company_id=company.id,
#             external_user_id=payload.user_id,
#             lang=payload.lang or "en",  # default to English if not provided
#         )
#         db.add(user)
#         db.commit()
#         db.refresh(user)
#     else:
#         # 🆕 Don't overwrite existing language (preserve original choice)
#         if not user.lang and payload.lang:
#             user.lang = payload.lang
#             db.commit()

#     # ✅ Step 4: Create short-lived JWT
#     access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
#     access_token = create_access_token(
#         data={
#             "user_id": str(user.id),
#             "company_id": str(company.id),
#             "lang": user.lang,
#         },
#         expires_delta=access_token_expires,
#     )

#     return {
#         "access_token": access_token,
#         "token_type": "bearer",
#         "lang": user.lang,
#     }

from datetime import timedelta, datetime
from sqlalchemy.orm import Session
from fastapi import Depends, APIRouter, HTTPException, status, Header
from app.db import get_db
from app.models import User, Company
from app.schemas import TokenRequest, TokenResponse, RefreshRequest
from app.auth import create_access_token
from app.config import settings
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
    company = db.query(Company).filter(Company.api_key == x_api_key).first()
    if not company or company.api_secret != x_api_secret:
        raise HTTPException(status_code=401, detail="Invalid API credentials")

    if not payload.user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

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
async def refresh_access_token(
    payload: RefreshRequest,
    db: Session = Depends(get_db),
):
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

    # Optional: check expiry manually
    if user.refresh_token_expiry and user.refresh_token_expiry < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Refresh token expired")

    # --- Generate new short-lived access token ---
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "user_id": str(user.id),
            "company_id": str(company_id),
            "lang": user.lang,
        },
        expires_delta=access_token_expires,
    )

    return {
        "access_token": access_token,
        "refresh_token": payload.refresh_token,  # reuse same refresh token
        "token_type": "bearer",
        "lang": user.lang,
    }


@router.post("/token/revoke")
async def revoke_refresh_token(
    payload: RefreshRequest,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.refresh_token == payload.refresh_token).first()
    if not user:
        raise HTTPException(status_code=404, detail="Token not found")

    user.refresh_token = None
    user.refresh_token_expiry = None
    db.commit()
    return {"detail": "Refresh token revoked successfully"}
