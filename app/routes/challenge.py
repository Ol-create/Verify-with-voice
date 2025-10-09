from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User, Challenge
from app.auth import verify_token
from app.utils.openai_client import generate_challenge_sentence
import datetime
import uuid

# ✅ Create the router BEFORE using it
router = APIRouter()

@router.get("/challenge")
async def get_challenge(
    token_data: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    user_id = token_data.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    # Fetch user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Generate sentence
    challenge_text = await generate_challenge_sentence(user.lang)

    # Insert challenge into DB
    challenge = Challenge(
        user_id=uuid.UUID(user_id),
        text=challenge_text,
        created_at=datetime.datetime.utcnow()
    )
    db.add(challenge)
    db.commit()

    return {"challenge_text": challenge_text, "lang": user.lang}
