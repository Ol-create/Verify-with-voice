# app/routes/verification.py

import os
import shutil
import tempfile
import uuid
import numpy as np
from fastapi import APIRouter, UploadFile, Form, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Enrollment, VerificationLog
from app.utils.audio import transcribe_audio, compute_embedding
from app.utils.verification import cosine_similarity, fuzzy_match
from app.utils.storage import upload_audio   # ✅ NEW
from app.auth import verify_token

router = APIRouter()

# Centralized threshold constant
SIMILARITY_THRESHOLD = 0.75  

# Max enrollments to compare against (for performance)
MAX_ENROLLMENTS = 5  


@router.post("/secure-verify-voice")
async def secure_verify(
    challenge_text: str = Form(...),
    audio: UploadFile = Form(...),
    db: Session = Depends(get_db),
    token_data: dict = Depends(verify_token),
):
    """
    Secure verification endpoint.
    Requires Bearer token in the Authorization header.
    Extracts `user_id` from token instead of request body.
    """
    user_id = token_data.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    tmpdir = tempfile.mkdtemp()
    try:
        # Save upload to temp file
        audio_path = os.path.join(tmpdir, audio.filename)
        with open(audio_path, "wb") as f:
            shutil.copyfileobj(audio.file, f)

        # --- Step 1: Transcribe with Whisper ---
        transcript = await transcribe_audio(audio_path)
        matched, ratio = fuzzy_match(transcript, challenge_text)
        if not matched:
            # ❌ Log failed attempt
            log = VerificationLog(
                user_id=user_id,
                phrase=transcript,
                similarity=0.0,
                liveness_verified=0,
                identity_verified=0,
            )
            db.add(log)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Challenge mismatch (similarity {ratio:.2f})"
            )

        # --- Step 2: Speaker embedding + similarity ---
        new_embedding = compute_embedding(audio_path)

        enrollments = (
            db.query(Enrollment)
            .filter(Enrollment.user_id == user_id)
            .order_by(Enrollment.created_at.desc())
            .limit(MAX_ENROLLMENTS)
            .all()
        )

        if not enrollments:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No enrollment found"
            )

        sims = [
            cosine_similarity(
                new_embedding,
                np.frombuffer(e.embedding, dtype=np.float32)
            )
            for e in enrollments
        ]
        best_sim = max(sims)
        verified = best_sim > SIMILARITY_THRESHOLD

        # --- Step 3: Upload verification audio to S3 ---
        s3_uri = upload_audio(
            audio_path,
            f"verifications/{user_id}/{uuid.uuid4()}-{audio.filename}",
            audio.filename
        )

        # ✅ Save verification attempt
        log = VerificationLog(
            user_id=user_id,
            phrase=transcript,
            similarity=float(best_sim),
            liveness_verified=1 if matched else 0,
            identity_verified=1 if verified else 0,
        )
        db.add(log)
        db.commit()

        return {
            "verified": verified,
            "similarity": best_sim,
            "transcript": transcript,
            "challenge_match": ratio,
            "audio_url": s3_uri,   # ✅ return S3 link for verification attempt
        }

    finally:
        shutil.rmtree(tmpdir)
