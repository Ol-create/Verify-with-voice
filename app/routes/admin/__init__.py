# app/routes/admin/__init__.py
"""Admin API, mounted at /admin. Every route except login requires get_current_admin."""
from fastapi import APIRouter

from app.routes.admin import auth, companies, credentials

router = APIRouter()
router.include_router(auth.router, prefix="/auth")
router.include_router(companies.router, prefix="/companies")
router.include_router(credentials.router, prefix="/credentials")
