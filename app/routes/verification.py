import os
import tempfile
import shutil
from fastapi import APIRouter, UploadFile, Form, Depends, HTTPException
from sqlalchemy.orm import Session
import numpy as np
from app.db import get_db
from app.models import Enrollment, VerificationLog
from app.utils.audio import compute_embedding
from app.utils.verification import best_similarity
from app.utils.challenge import ACTIVE_CHALLENGES
from app.config import verify_token
import datetime


router = APIRouter()


@router.post("/secure-verify-voice")
async def secure_verify_voice(
    user_id: str = Form(...),
    audio: UploadFile = Form(...),
    token: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    # Ensure challenge exists
    challenge_data = ACTIVE_CHALLENGES.get(user_id)
    if not challenge_data:
        raise HTTPException(status_code=400, detail="No active challenge")

    tmpdir = tempfile.mkdtemp()
    try:
        audio_path = os.path.join(tmpdir, audio.filename)
        with open(audio_path, "wb") as f:
            shutil.copyfileobj(audio.file, f)

        # Compute embedding
        new_emb = compute_embedding(audio_path)

        # Load enrollments
        rows = db.query(Enrollment).filter(Enrollment.user_id == user_id).all()
        if not rows:
            raise HTTPException(status_code=404, detail="No enrollment found")

        stored_embeddings = [np.frombuffer(r.embedding, dtype=np.float32) for r in rows]
        sim = best_similarity(new_emb, stored_embeddings)
        identity_verified = sim > 0.75

        # For liveness: normally transcribe `audio_path` and compare to challenge
        phrase = challenge_data["phrase"]
        # Placeholder: mark as true until ASR integration
        liveness_verified = True

        # Log attempt
        log = VerificationLog(
            user_id=user_id,
            phrase=phrase,
            similarity=sim,
            liveness_verified=liveness_verified,
            identity_verified=identity_verified,
            created_at=datetime.datetime.utcnow(),
        )
        db.add(log)
        db.commit()

        # Consume the challenge after use
        del ACTIVE_CHALLENGES[user_id]

        return {
            "liveness_verified": liveness_verified,
            "identity_verified": identity_verified,
            "similarity": sim,
        }
    finally:
        shutil.rmtree(tmpdir)
