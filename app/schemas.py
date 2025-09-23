from pydantic import BaseModel
from datetime import datetime


class EnrollmentResponse(BaseModel):
    message: str

    class Config:
        orm_mode = True


class VerificationResponse(BaseModel):
    liveness_verified: bool
    identity_verified: bool
    similarity: float

    class Config:
        orm_mode = True


class RiskScoreResponse(BaseModel):
    user_id: str
    risk_score: float
    liveness_verified: bool
    identity_verified: bool
    timestamp: datetime

    class Config:
        orm_mode = True


class TokenData(BaseModel):
    user_id: str


# ✅ Moved here from token.py
class TokenRequest(BaseModel):
    user_id: str
    lang: str = "en" 


class TokenResponse(BaseModel):
    lang: str
    access_token: str
    token_type: str = "bearer"