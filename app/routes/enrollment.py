import os
import tempfile
import shutil
import datetime
import logging
import numpy as np
import asyncio
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, UploadFile, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Enrollment, Challenge, User
from app.utils.audio import compute_embedding, transcribe_audio, convert_to_wav
from app.utils.verification import fuzzy_match
from app.utils.storage import upload_audio
from app.utils.openai_client import convert_digits_to_words
from app.auth import get_current_user
from app.anti_spoofing.aasist import aasist_score

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
REQUIRED_SAMPLES = 3
_DETECTOR_POOL = ThreadPoolExecutor(max_workers=2)


async def _run_detector_in_executor(fn, audio_path: str):
    """Run heavy inference (like AASIST) in a thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_DETECTOR_POOL, fn, audio_path)


@router.post("/enroll-voice")
async def enroll_voice(
    audio: UploadFile,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Handles multi-sample voice enrollment (3 recordings per user)."""
    user_uuid = user.id

    if not audio:
        raise HTTPException(status_code=400, detail="No file uploaded.")
    if not audio.content_type or not audio.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Invalid file type. Must be an audio file.")

    existing = db.query(Enrollment).filter(Enrollment.user_id == user_uuid, Enrollment.is_final == True).first()
    if existing:
        raise HTTPException(status_code=400, detail="User already fully enrolled")

    challenge = (
        db.query(Challenge)
        .filter(Challenge.user_id == user_uuid)
        .order_by(Challenge.created_at.desc())
        .first()
    )
    if not challenge:
        raise HTTPException(status_code=400, detail="No active challenge found")

    challenge_age = (datetime.datetime.utcnow() - challenge.created_at).total_seconds()
    if challenge_age > settings.CHALLENGE_TTL:
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
            audio_path = os.path.join(tmpdir, audio.filename)
            with open(audio_path, "wb") as f:
                tmpfile.seek(0)
                shutil.copyfileobj(tmpfile, f)

            # Step 1: Convert and transcribe
            wav_path = convert_to_wav(audio_path)
            transcript = await transcribe_audio(wav_path, language=user.lang or "auto")

            if not transcript.strip():
                logger.info("Enroll user=%s rejected: empty transcription", user_uuid)
                db.delete(challenge)
                db.commit()
                raise HTTPException(status_code=400, detail="Could not transcribe audio")

            transcript = await convert_digits_to_words(transcript, user.lang)

            # Step 2: Challenge verification
            match, ratio = fuzzy_match(transcript, challenge.text, threshold=settings.MATCH_THRESHOLD)
            logger.debug("Enroll user=%s phrase match=%s ratio=%.2f", user_uuid, match, ratio)

            if not match:
                logger.info("Enroll user=%s rejected: phrase mismatch (ratio=%.2f)", user_uuid, ratio)
                db.delete(challenge)
                db.commit()
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Phrase mismatch! Say the phrase exactly"}
                )

            # Step 3: Anti-Spoofing
            aasist_raw = await _run_detector_in_executor(aasist_score, wav_path)
            spoof_prob = float(np.clip(aasist_raw, 0.0, 1.0))

            if spoof_prob > settings.SPOOF_THRESHOLD:
                logger.info("Enroll user=%s rejected: spoof detected (spoof_prob=%.4f)", user_uuid, spoof_prob)
                db.delete(challenge)
                db.commit()
                return JSONResponse(
                    status_code=400,
                    content={"detail": "We detected an artificial voice! Try again using your real voice."}
                )

            # Step 4: Upload and embedding
            s3_uri = upload_audio(audio_path, f"audio/{user_uuid}", audio.filename)
            embedding = compute_embedding(audio_path)

            # Step 5: Save partial enrollment
            enrollment = Enrollment(
                user_id=user_uuid,
                embedding=embedding.astype(np.float32).tobytes(),
                audio_url=s3_uri,
                created_at=datetime.datetime.utcnow(),
                is_final=False,
            )
            db.add(enrollment)
            db.commit()

            # Step 6: Check how many samples exist
            user_enrolls = db.query(Enrollment).filter(
                Enrollment.user_id == user_uuid, Enrollment.is_final == False
            ).all()

            if len(user_enrolls) < REQUIRED_SAMPLES:
                remaining = REQUIRED_SAMPLES - len(user_enrolls)
                logger.info("Enroll user=%s sample %d/%d saved", user_uuid, len(user_enrolls), REQUIRED_SAMPLES)
                db.delete(challenge)
                db.commit()
                return {
                    "message": f"Enrollment sample {len(user_enrolls)}/{REQUIRED_SAMPLES} saved. {remaining} more needed.",
                    "transcript": transcript.strip(),
                    "similarity": ratio,
                    "audio_url": s3_uri,
                    "spoof_prob": spoof_prob,
                }

            # Step 7: Finalize enrollment
            embeddings = [np.frombuffer(e.embedding, dtype=np.float32) for e in user_enrolls]
            avg_embedding = np.mean(np.stack(embeddings), axis=0)

            for e in user_enrolls:
                db.delete(e)
            db.commit()

            final_enrollment = Enrollment(
                user_id=user_uuid,
                embedding=avg_embedding.astype(np.float32).tobytes(),
                audio_url=s3_uri,
                created_at=datetime.datetime.utcnow(),
                is_final=True,
            )
            db.add(final_enrollment)
            db.delete(challenge)
            db.commit()
            logger.info("Enroll user=%s complete, final voiceprint created", user_uuid)

            return {
                "message": "✅ Enrollment complete. Final voiceprint created.",
                "user_id": str(user_uuid),
                "transcript": transcript.strip(),
                "average_samples": REQUIRED_SAMPLES,
                "audio_url": s3_uri,
                "spoof_prob": spoof_prob,
            }

        except HTTPException:
            # Deliberate 4xx responses (user not found, empty transcript...) pass through
            raise
        except Exception as e:
            logger.exception("Enroll user=%s failed with an unexpected error", user_uuid)
            db.rollback()
            raise HTTPException(status_code=500, detail=str(e))

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
