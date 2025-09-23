from pydantic import BaseModel
from datetime import datetime
from uuid import UUID


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
    user_id: UUID
    risk_score: float
    liveness_verified: bool
    identity_verified: bool
    timestamp: datetime

    class Config:
        orm_mode = True


class TokenData(BaseModel):
    user_id: UUID
    company_id: UUID
    lang: str


# ✅ Request when company wants a token for their user
class TokenRequest(BaseModel):
    user_id: str       # external user_id from company’s system
    company_id: UUID   # the company’s UUID
    lang: str = "en"


# ✅ Response after token generation
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    lang: str
