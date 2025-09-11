import os
import shutil
import tempfile
import numpy as np
from fastapi import APIRouter, UploadFile, Form, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Enrollment
from app.utils.verification import (
    transcribe_audio,
    compute_embedding,
    cosine_similarity,
    fuzzy_match
)

router = APIRouter()

# Centralized threshold constant
SIMILARITY_THRESHOLD = 0.75  

# Max enrollments to compare against (for performance)
MAX_ENROLLMENTS = 5  


@router.post("/secure-verify-voice")
async def secure_verify(
    user_id: str = Form(...),
    challenge_text: str = Form(...),
    audio: UploadFile = Form(...),
    db: Session = Depends(get_db),
):
    tmpdir = tempfile.mkdtemp()
    try:
        # Save upload to temp file
        audio_path = os.path.join(tmpdir, audio.filename)
        with open(audio_path, "wb") as f:
            shutil.copyfileobj(audio.file, f)

        # --- Step 1: Transcribe with Whisper ---
        transcript = transcribe_audio(audio_path)
        matched, ratio = fuzzy_match(transcript, challenge_text)
        if not matched:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Challenge mismatch (similarity {ratio:.2f})"
            )

        # --- Step 2: Speaker embedding + similarity ---
        new_embedding = compute_embedding(audio_path)

        # Limit enrollment records for efficiency (e.g., latest 5)
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

        return {
            "verified": best_sim > SIMILARITY_THRESHOLD,
            "similarity": best_sim,
            "transcript": transcript,
            "challenge_match": ratio
        }

    finally:
        shutil.rmtree(tmpdir)
