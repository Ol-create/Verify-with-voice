# app/rate_limit.py
from jose import JWTError, jwt
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.config import settings


def rate_limit_key(request: Request) -> str:
    """
    Rate-limit per company when the request carries a valid access token,
    otherwise per client IP (e.g. /token, /health).

    The token signature is checked so nobody can spend another company's
    allowance by sending a forged company_id.
    """
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            payload = jwt.decode(
                auth[7:], settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
            )
            if payload.get("type") == "access" and payload.get("company_id"):
                return f"company:{payload['company_id']}"
        except JWTError:
            pass
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=rate_limit_key, default_limits=[settings.RATE_LIMIT])
