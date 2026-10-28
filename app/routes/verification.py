import os
import shutil
import tempfile
import uuid
import datetime
import logging
import numpy as np
import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, UploadFile, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Enrollment, VerificationLog, Challenge, User
from app.utils.openai_client import convert_digits_to_words
from app.utils.audio import transcribe_audio, compute_embedding, convert_to_wav
from app.utils.verification import cosine_similarity, fuzzy_match
from app.utils.storage import upload_audio
from app.auth import verify_token
from app.anti_spoofing.aasist import aasist_score

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

_DETECTOR_POOL = ThreadPoolExecutor(max_workers=2)


async def _run_detector_in_executor(fn, audio_path: str):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_DETECTOR_POOL, fn, audio_path)


@router.post("/secure-verify-voice")
async def secure_verify(
    audio: UploadFile,
    token_data: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    # ✅ Step 0: Validate user ID
    user_id = token_data.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id format")

    if not audio or not audio.content_type or not audio.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Invalid or missing audio file")

    # ✅ Step 1: Fetch user
    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # ✅ Step 2: Get most recent challenge
    challenge = (
        db.query(Challenge)
        .filter(Challenge.user_id == user_uuid)
        .order_by(Challenge.created_at.desc())
        .first()
    )
    if not challenge:
        raise HTTPException(status_code=400, detail="No active challenge found")

    # ✅ Step 3: Expiry check
    age = (datetime.datetime.utcnow() - challenge.created_at).total_seconds()
    if age > settings.CHALLENGE_TTL:
        db.delete(challenge)
        db.commit()
        raise HTTPException(status_code=400, detail="Challenge expired")

    with tempfile.SpooledTemporaryFile(max_size=MAX_FILE_SIZE) as tmpfile:
        size = 0
        for chunk in iter(lambda: audio.file.read(1024 * 1024), b""):
            size += len(chunk)
            if size > MAX_FILE_SIZE:
                raise HTTPException(status_code=413, detail="Audio file is too large (max 10MB)")
            tmpfile.write(chunk)

        tmpfile.seek(0)
        tmpdir = tempfile.mkdtemp()

        try:
            # ✅ Step 4: Save uploaded audio properly
            audio_path = os.path.join(tmpdir, audio.filename)
            with open(audio_path, "wb") as f:
                tmpfile.seek(0)
                shutil.copyfileobj(tmpfile, f)

            # ✅ Step 5: Transcribe (language-aware)
            transcript = await transcribe_audio(audio_path, language=user.lang or "auto")
            transcript = await convert_digits_to_words(transcript, user.lang)

            # ✅ Step 6: Phrase verification
            matched, ratio = fuzzy_match(transcript, challenge.text, threshold=settings.MATCH_THRESHOLD)
            logger.debug("Verify user=%s phrase match=%s ratio=%.2f", user_uuid, matched, ratio)

            if not matched:
                logger.info("Verify user=%s rejected: phrase mismatch (ratio=%.2f)", user_uuid, ratio)
                db.add(
                    VerificationLog(
                        user_id=user_uuid,
                        phrase=transcript,
                        similarity=0.0,
                        liveness_verified=False,
                        identity_verified=False,
                    )
                )
                db.delete(challenge)
                db.commit()
                raise HTTPException(
                    status_code=401,
                    detail="Phrase mismatch! Say the phrase exactly as displayed",
                )

            # ✅ Step 7: Anti-spoofing
            wav_path = convert_to_wav(audio_path)
            aasist_raw = await _run_detector_in_executor(aasist_score, wav_path)
            spoof_prob = float(np.clip(aasist_raw, 0.0, 1.0))

            if spoof_prob > settings.SPOOF_THRESHOLD:
                logger.info("Verify user=%s rejected: spoof detected (spoof_prob=%.4f)", user_uuid, spoof_prob)
                db.add(
                    VerificationLog(
                        user_id=user_uuid,
                        phrase=transcript,
                        liveness_verified=False,
                        identity_verified=False,
                        aasist_score=spoof_prob,
                        spoof_prob=spoof_prob,
                    )
                )
                db.delete(challenge)
                db.commit()
                raise HTTPException(
                    status_code=403,
                    detail="We detected an artificial voice! Please use your real voice.",
                )

            # ✅ Step 8: Speaker verification
            enrollment = (
                db.query(Enrollment)
                .filter(Enrollment.user_id == user_uuid, Enrollment.is_final == True)
                .first()
            )
            if not enrollment or not enrollment.embedding:
                raise HTTPException(status_code=404, detail="User not fully enrolled")

            enrolled_embedding = np.frombuffer(enrollment.embedding, dtype=np.float32).flatten()
            new_embedding = compute_embedding(audio_path).flatten()
            similarity = cosine_similarity(new_embedding, enrolled_embedding)

            verified = similarity > settings.SIMILARITY_THRESHOLD

            if not verified:
                logger.info("Verify user=%s rejected: voice mismatch (similarity=%.4f)", user_uuid, similarity)
                db.add(
                    VerificationLog(
                        user_id=user_uuid,
                        phrase=transcript,
                        similarity=float(similarity),
                        liveness_verified=True,
                        identity_verified=False,
                        aasist_score=spoof_prob,
                        spoof_prob=spoof_prob,
                    )
                )
                db.delete(challenge)
                db.commit()
                raise HTTPException(
                    status_code=401,
                    detail="Verification failed! Voice doesn’t match the enrolled sample. Please try again.",
                )

            # ✅ Step 9: Upload and success
            s3_uri = upload_audio(audio_path, f"audio/{user_uuid}/verifications", audio.filename)

            log = VerificationLog(
                user_id=user_uuid,
                phrase=transcript,
                similarity=float(similarity),
                liveness_verified=True,
                identity_verified=True,
                aasist_score=spoof_prob,
                spoof_prob=spoof_prob,
            )
            db.add(log)
            db.delete(challenge)
            db.commit()
            logger.info(
                "Verify user=%s succeeded (similarity=%.4f, spoof_prob=%.4f)", user_uuid, similarity, spoof_prob
            )

            return {
                "verified": True,
                "message": "Verification successful!",
                "similarity": similarity,
                "transcript": transcript,
                "challenge_match": ratio,
                "audio_url": s3_uri,
                "spoof_prob": spoof_prob,
                "language_used": user.lang or "auto",
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Verify user=%s failed with an unexpected error", user_uuid)
            db.rollback()
            if challenge in db:
                db.delete(challenge)
                db.commit()
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
