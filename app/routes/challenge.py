from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from app.db import get_db
from app.models import User
from app.auth import get_current_user  # JWT decode dependency
from app.utils.openai_client import generate_challenge_sentence  # new util

router = APIRouter()


@router.get("/challenge")
async def get_challenge(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return a random challenge sentence using OpenAI,
    in the language preference of the authenticated user.
    """
    # Fetch fresh user info from DB (to ensure lang is up to date)
    user = db.query(User).filter(User.id == current_user.id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Call OpenAI to generate a sentence
    challenge = await generate_challenge_sentence(user.lang)

    return {"challenge_text": challenge, "lang": user.lang}
