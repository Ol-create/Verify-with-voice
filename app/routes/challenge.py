from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.auth import verify_token  # ✅ use verify_token instead of get_current_user
from app.utils.openai_client import generate_challenge_sentence  # new util

router = APIRouter()


@router.get("/challenge")
async def get_challenge(
    token_data: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """
    Return a random challenge sentence using OpenAI,
    in the language preference of the authenticated user.
    """
    user_id = token_data.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    # Fetch fresh user info from DB (to ensure lang is up to date)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Call OpenAI to generate a sentence
    challenge = await generate_challenge_sentence(user.lang)

    return {"challenge_text": challenge, "lang": user.lang}
