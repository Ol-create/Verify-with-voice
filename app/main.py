# app/main.py
from fastapi import FastAPI
from mangum import Mangum

from slowapi import Limiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.routes import enrollment, challenge, language, health, token, verification, company
from app.db import Base, engine
# from app.models import Enrollment, VerificationLog

# from app.anti_spoofing import load_models

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

# --- FastAPI app ---
app = FastAPI()

# @app.on_event("startup")
# async def startup_event():
#     load_models(
#         aasist_ckpt="app/models/anti_spoof/aasist.ckpt",
#         lcnn_ckpt="app/models/anti_spoof/lcnn.ckpt",
#         cqcc_gmm_ckpt="app/models/anti_spoof/cqcc_gmm.joblib",


#     )

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["3/minute"],  # 3 requests per minute per IP
)

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
# app.include_router(company.router, prefix="/v1", tags=["Company"])

# ✅ Lambda entrypoint
handler = Mangum(app)