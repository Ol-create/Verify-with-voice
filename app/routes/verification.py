# app/routes/verification.py

import os
import shutil
import tempfile
import uuid
import datetime
import numpy as np
import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, UploadFile, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Enrollment, VerificationLog, Challenge
from app.utils.audio import transcribe_audio, compute_embedding
from app.utils.verification import cosine_similarity, fuzzy_match
from app.utils.storage import upload_audio
from app.auth import verify_token
from app.anti_spoofing import (
    aasist_score,
    lcnn_score,
    cqcc_gmm_score,
    normalize_score,
    fuse_scores,
)

router = APIRouter()

SIMILARITY_THRESHOLD = 0.75
MAX_ENROLLMENTS = 5
CHALLENGE_TTL = 30
SPOOF_THRESHOLD = 0.5

_DETECTOR_POOL = ThreadPoolExecutor(max_workers=3)


async def _run_detector_in_executor(fn, audio_path: str):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_DETECTOR_POOL, fn, audio_path)


@router.post("/secure-verify-voice")
async def secure_verify(
    audio: UploadFile,
    db: Session = Depends(get_db),
    token_data: dict = Depends(verify_token),
):
    user_id = token_data.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    # ✅ Fetch latest challenge
    challenge = (
        db.query(Challenge)
        .filter(Challenge.user_id == user_id)
        .order_by(Challenge.created_at.desc())
        .first()
    )
    if not challenge:
        raise HTTPException(status_code=400, detail="No active challenge found")

    # ✅ Enforce TTL
    if (datetime.datetime.utcnow() - challenge.created_at).total_seconds() > CHALLENGE_TTL:
        db.delete(challenge)
        db.commit()
        raise HTTPException(status_code=400, detail="Challenge expired")

    tmpdir = tempfile.mkdtemp()
    try:
        # Save file locally
        audio_path = os.path.join(tmpdir, audio.filename)
        with open(audio_path, "wb") as f:
            shutil.copyfileobj(audio.file, f)

        # --- Step 1: Transcribe + liveness check ---
        transcript = await transcribe_audio(audio_path)
        matched, ratio = fuzzy_match(transcript, challenge.text, threshold=0.8)

        if not matched:
            # ❌ failed liveness → log with null spoof scores
            log = VerificationLog(
                user_id=user_id,
                phrase=transcript,
                similarity=0.0,
                liveness_verified=False,
                identity_verified=False,
                aasist_score=None,
                lcnn_score=None,
                cqcc_gmm_score=None,
                spoof_prob=None,
            )
            db.add(log)
            db.delete(challenge)
            db.commit()
            raise HTTPException(status_code=401, detail=f"Challenge mismatch (similarity {ratio:.2f})")

        # --- Step 2: Run spoof detectors concurrently ---
        aasist_future = _run_detector_in_executor(aasist_score, audio_path)
        lcnn_future = _run_detector_in_executor(lcnn_score, audio_path)
        cqcc_future = _run_detector_in_executor(cqcc_gmm_score, audio_path)

        aasist_raw, lcnn_raw, cqcc_raw = await asyncio.gather(
            aasist_future, lcnn_future, cqcc_future
        )

        aasist_n = normalize_score(aasist_raw, 0.0, 1.0)
        lcnn_n = normalize_score(lcnn_raw, 0.0, 1.0)
        cqcc_n = normalize_score(cqcc_raw, 0.0, 1.0)

        detector_scores = {
            "aasist": float(aasist_n),
            "lcnn": float(lcnn_n),
            "cqcc_gmm": float(cqcc_n),
        }

        spoof_prob = float(fuse_scores(detector_scores))

        if spoof_prob > SPOOF_THRESHOLD:
            # ❌ spoof detected
            log = VerificationLog(
                user_id=user_id,
                phrase=transcript,
                similarity=0.0,
                liveness_verified=True,
                identity_verified=False,
                aasist_score=aasist_n,
                lcnn_score=lcnn_n,
                cqcc_gmm_score=cqcc_n,
                spoof_prob=spoof_prob,
            )
            db.add(log)
            db.delete(challenge)
            db.commit()
            raise HTTPException(status_code=401, detail=f"Audio flagged as spoof (spoof_prob={spoof_prob:.3f})")

        # --- Step 3: Embedding similarity check ---
        new_embedding = compute_embedding(audio_path)
        enrollments = (
            db.query(Enrollment)
            .filter(Enrollment.user_id == user_id)
            .order_by(Enrollment.created_at.desc())
            .limit(MAX_ENROLLMENTS)
            .all()
        )
        if not enrollments:
            db.delete(challenge)
            db.commit()
            raise HTTPException(status_code=404, detail="No enrollment found")

        sims = [
            cosine_similarity(new_embedding, np.frombuffer(e.embedding, dtype=np.float32))
            for e in enrollments
        ]
        best_sim = float(max(sims))
        verified = best_sim > SIMILARITY_THRESHOLD

        # --- Step 4: Upload to S3 + log ---
        s3_uri = upload_audio(
            audio_path,
            f"verifications/{user_id}/{uuid.uuid4()}-{audio.filename}",
            audio.filename,
        )

        log = VerificationLog(
            user_id=user_id,
            phrase=transcript,
            similarity=best_sim,
            liveness_verified=True,
            identity_verified=verified,
            aasist_score=aasist_n,
            lcnn_score=lcnn_n,
            cqcc_gmm_score=cqcc_n,
            spoof_prob=spoof_prob,
        )
        db.add(log)
        db.delete(challenge)
        db.commit()

        return {
            "verified": verified,
            "similarity": best_sim,
            "transcript": transcript,
            "challenge_match": ratio,
            "audio_url": s3_uri,
            "detector_scores": detector_scores,
            "spoof_prob": spoof_prob,
        }

    except Exception as e:
        try:
            db.delete(challenge)
            db.commit()
        except Exception:
            pass
        raise
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
