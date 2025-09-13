from fastapi import APIRouter, HTTPException, status
from datetime import timedelta

from app.config import settings
from app.auth import create_access_token
from app.schemas import TokenRequest, TokenResponse

router = APIRouter()


@router.post("/token", response_model=TokenResponse)
async def generate_token(payload: TokenRequest):
    """
    Generate a JWT token using user_id from JSON body.
    Example request:
    {
      "user_id": "12345"
    }
    """
    if not payload.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_id is required",
        )

    access_token_expires = timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    access_token = create_access_token(
        data={"user_id": payload.user_id},
        expires_delta=access_token_expires,
    )
    return {"access_token": access_token, "token_type": "bearer"}
