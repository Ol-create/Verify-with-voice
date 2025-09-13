from fastapi import APIRouter
from app.utils.sentences import get_random_sentence  # <-- import here

router = APIRouter()

@router.get("/challenge")
async def get_challenge():
    """
    Return a random five-word challenge sentence from the predefined list.
    """
    challenge = get_random_sentence()
    return {"challenge_text": challenge}
