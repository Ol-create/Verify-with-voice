from fastapi import APIRouter
from app.languages import POPULAR_LANGUAGES

router = APIRouter()

@router.get("/languages")
async def list_languages():
    """
    List supported languages for challenge generation.
    """
    return POPULAR_LANGUAGES
