from pydantic import BaseModel
from datetime import datetime


class EnrollmentResponse(BaseModel):
    message: str


class VerificationResponse(BaseModel):
    liveness_verified: bool
    identity_verified: bool
    similarity: float


class RiskScoreResponse(BaseModel):
    user_id: str
    risk_score: float
    liveness_verified: bool
    identity_verified: bool
    timestamp: datetime
    
    class Config:
        orm_mode = True