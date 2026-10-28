# app/main.py
import logging

from fastapi import FastAPI
from mangum import Mangum

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.rate_limit import limiter
from app.routes import enrollment, challenge, language, health, token, verification

# basicConfig is a no-op on Lambda (it already has a handler), so set the app logger level too
logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("app").setLevel(settings.LOG_LEVEL)

# The schema is managed by Alembic: run `alembic upgrade head` before starting the app.

# --- FastAPI app ---
app = FastAPI()

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Routers
app.include_router(enrollment.router, prefix="/v1", tags=["Enrollment"])
app.include_router(challenge.router, prefix="/v1", tags=["Challenge"])
app.include_router(health.router, prefix="", tags=["Health"])
app.include_router(token.router, prefix="/v1", tags=["Token"])
app.include_router(verification.router, prefix="/v1", tags=["Verification"])
app.include_router(language.router, prefix="/v1", tags=["Language"])

# ✅ Lambda entrypoint
handler = Mangum(app)
