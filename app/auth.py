import datetime
import uuid
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session, joinedload
from typing import Optional

from app.config import settings
from app.db import get_db
from app.models import COMPANY_ACTIVE, ApiCredential, Company, User

# --- Security ---
security = HTTPBearer()

# --- JWT Utilities ---
def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + (
        expires_delta or datetime.timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    encoded = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Validate an end-user access token and return its payload."""
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError:
        raise _unauthorized()

    # Only access tokens for a specific company user are accepted here
    if payload.get("type") != "access" or not payload.get("user_id") or not payload.get("company_id"):
        raise _unauthorized()
    return payload


def require_active_company(company: Company) -> None:
    if company.status != COMPANY_ACTIVE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Company account is {company.status}")


def get_current_user(token_data: dict = Depends(verify_token), db: Session = Depends(get_db)) -> User:
    """
    The end user an access token belongs to, loaded with their company.
    Checked on every request, so suspending a company or revoking the API key that
    issued the token takes effect immediately instead of when the token expires.
    """
    try:
        user_id = uuid.UUID(token_data["user_id"])
        company_id = uuid.UUID(token_data["company_id"])
        credential_id = uuid.UUID(token_data["credential_id"]) if token_data.get("credential_id") else None
    except ValueError:
        raise _unauthorized()

    user = (
        db.query(User)
        .options(joinedload(User.company))
        .filter(User.id == user_id, User.company_id == company_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    require_active_company(user.company)

    if credential_id:
        credential = db.get(ApiCredential, credential_id)
        if not credential or not credential.is_active or credential.company_id != company_id:
            raise _unauthorized()

    return user
