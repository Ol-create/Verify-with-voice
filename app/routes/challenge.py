from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User, Challenge
from app.auth import get_current_user
from app.utils.openai_client import generate_challenge_sentence
import datetime

router = APIRouter()

@router.get("/challenge")
async def get_challenge(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Generate sentence
    challenge_text = await generate_challenge_sentence(user.lang)

    # Insert challenge into DB
    challenge = Challenge(
        user_id=user.id,
        text=challenge_text,
        created_at=datetime.datetime.utcnow()
    )
    db.add(challenge)
    db.commit()

    return {"challenge_text": challenge_text, "lang": user.lang}
