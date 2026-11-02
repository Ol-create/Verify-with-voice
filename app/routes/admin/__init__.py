# app/routes/admin/__init__.py
"""Admin API, mounted at /admin. Every route except login requires get_current_admin."""
from fastapi import APIRouter

from app.routes.admin import auth

router = APIRouter()
router.include_router(auth.router, prefix="/auth")
