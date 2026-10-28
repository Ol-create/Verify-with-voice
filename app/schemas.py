from uuid import UUID

from pydantic import BaseModel


# ✅ Request when company wants a token for their user
class TokenRequest(BaseModel):
    user_id: str       # external user_id from company’s system
    company_id: UUID | None = None   # optional: the API key already identifies the company
    lang: str | None = "en"

# ✅ Used for token refresh endpoint
class RefreshRequest(BaseModel):
    refresh_token: str

# ✅ Response after token generation
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    lang: str
