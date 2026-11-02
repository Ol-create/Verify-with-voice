# app/routes/admin/auth.py
import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.auth import create_admin_token, get_current_admin
from app.config import settings
from app.db import get_db
from app.models import AdminUser
from app.rate_limit import limiter
from app.utils.passwords import verify_password

router = APIRouter()
logger = logging.getLogger(__name__)


class AdminLoginRequest(BaseModel):
    email: str
    password: str


class AdminTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class AdminProfile(BaseModel):
    id: str
    email: str
    last_login_at: datetime.datetime | None


@router.post("/login", response_model=AdminTokenResponse)
@limiter.limit(lambda: settings.ADMIN_LOGIN_RATE_LIMIT, key_func=get_remote_address)
async def admin_login(request: Request, payload: AdminLoginRequest, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    admin = db.query(AdminUser).filter(AdminUser.email == email).first()

    # Same message (and similar timing) whether the email, password or account state is wrong
    password_ok = verify_password(payload.password, admin.password_hash if admin else None)
    if not admin or not password_ok or not admin.is_active:
        logger.warning("Admin login failed for %s from %s", email, get_remote_address(request))
        raise HTTPException(status_code=401, detail="Invalid email or password")

    admin.last_login_at = datetime.datetime.utcnow()
    db.commit()
    logger.info("Admin %s logged in", email)

    token, expires_in = create_admin_token(admin)
    return {"access_token": token, "token_type": "bearer", "expires_in": expires_in}


@router.get("/me", response_model=AdminProfile)
async def admin_me(admin: AdminUser = Depends(get_current_admin)):
    return {"id": str(admin.id), "email": admin.email, "last_login_at": admin.last_login_at}
