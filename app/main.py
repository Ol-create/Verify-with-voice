# app/main.py
from fastapi import FastAPI
from mangum import Mangum

from app.routes import enrollment, challenge, language, health, token, verification
from app.db import Base, engine
# from app.models import Enrollment, VerificationLog

from app.anti_spoofing import load_models

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

# --- FastAPI app ---
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    load_models(
        aasist_ckpt="app/models/anti_spoof/aasist.ckpt",
        lcnn_ckpt="app/models/anti_spoof/lcnn.ckpt",
        cqcc_gmm_ckpt="app/models/anti_spoof/cqcc_gmm.joblib",
    )

# Routers
app.include_router(enrollment.router, prefix="/api", tags=["Enrollment"])
app.include_router(challenge.router, prefix="/api", tags=["Challenge"])
app.include_router(health.router, prefix="/api", tags=["Health"])
app.include_router(token.router, prefix="/api", tags=["Token"])
app.include_router(verification.router, prefix="/api", tags=["Verification"])
app.include_router(language.router, prefix="/api", tags=["Language"])

# ✅ Lambda entrypoint
handler = Mangum(app)