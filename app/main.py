# app/main.py
from fastapi import FastAPI
from mangum import Mangum

from app.routes import enrollment, challenge, health, token, verification
from app.db import Base, engine
from app.models import Enrollment, VerificationLog

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

# --- FastAPI app ---
app = FastAPI()

# Routers
app.include_router(enrollment.router, prefix="/api", tags=["Enrollment"])
app.include_router(challenge.router, prefix="/api", tags=["Challenge"])
app.include_router(health.router, prefix="/api", tags=["Health"])
app.include_router(token.router, prefix="/api", tags=["Token"])
app.include_router(verification.router, prefix="/api", tags=["Verification"])

# ✅ Lambda entrypoint
handler = Mangum(app)