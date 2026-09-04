import os
import tempfile
import shutil
import datetime
import uuid
import logging
import numpy as np
import asyncio
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, UploadFile, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Enrollment, Challenge, User
from app.utils.audio import compute_embedding, transcribe_audio, convert_to_wav
from app.utils.verification import fuzzy_match
from app.utils.storage import upload_audio
from app.utils.openai_client import convert_digits_to_words
from app.auth import verify_token
from app.anti_spoofing.aasist import aasist_score
from app.utils.normalize_transcription import normalize_numbers_to_words

router = APIRouter()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Add console handler (if not already configured globally)
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%H:%M:%S")
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
CHALLENGE_TTL = 120  # seconds
REQUIRED_SAMPLES = 3
SPOOF_THRESHOLD = 0.30  # Higher = stricter anti-spoof filter
_DETECTOR_POOL = ThreadPoolExecutor(max_workers=2)
MATCH_THRESHOLD = 0.2  # Similarity threshold for challenge verification


async def _run_detector_in_executor(fn, audio_path: str):
    """Run heavy inference (like AASIST) in a thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_DETECTOR_POOL, fn, audio_path)


@router.post("/enroll-voice")
async def enroll_voice(
    audio: UploadFile,
    token_data: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Handles multi-sample voice enrollment (3 recordings per user)."""

    logger.debug("🎤 Starting enroll_voice endpoint")
    logger.debug(f"Received audio: {audio}")
    logger.debug(f"Audio filename: {getattr(audio, 'filename', None)}")
    logger.debug(f"Audio content_type: {getattr(audio, 'content_type', None)}")
    logger.debug(f"Token data: {token_data}")

    user_id = token_data.get("user_id")
    if not user_id:
        logger.error("❌ Missing user_id in token_data")
        raise HTTPException(status_code=401, detail="Invalid token payload")

    try:
        user_uuid = uuid.UUID(user_id)
        logger.debug(f"✅ Parsed user_uuid: {user_uuid}")
    except ValueError:
        logger.exception("❌ Invalid user_id format (not UUID)")
        raise HTTPException(status_code=400, detail="Invalid user_id format")

    if not audio:
        logger.error("❌ No file uploaded")
        raise HTTPException(status_code=400, detail="No file uploaded.")
    if not audio.content_type or not audio.content_type.startswith("audio/"):
        logger.error(f"❌ Invalid file type: {audio.content_type}")
        raise HTTPException(status_code=400, detail="Invalid file type. Must be an audio file.")

    logger.debug("🔎 Checking existing enrollment records...")
    existing = db.query(Enrollment).filter(Enrollment.user_id == user_uuid, Enrollment.is_final == True).first()
    if existing:
        logger.warning("⚠️ User already fully enrolled")
        raise HTTPException(status_code=400, detail="User already fully enrolled")

    logger.debug("🧩 Fetching latest challenge...")
    challenge = (
        db.query(Challenge)
        .filter(Challenge.user_id == user_uuid)
        .order_by(Challenge.created_at.desc())
        .first()
    )
    if not challenge:
        logger.error("❌ No active challenge found")
        raise HTTPException(status_code=400, detail="No active challenge found")

    challenge_age = (datetime.datetime.utcnow() - challenge.created_at).total_seconds()
    logger.debug(f"⏱ Challenge age: {challenge_age:.2f}s")
    if challenge_age > CHALLENGE_TTL:
        logger.warning("⚠️ Challenge expired")
        db.delete(challenge)
        db.commit()
        raise HTTPException(status_code=400, detail="Challenge expired")

    logger.debug("💾 Writing temporary audio file...")
    with tempfile.SpooledTemporaryFile(max_size=MAX_FILE_SIZE) as tmpfile:
        size = 0
        for chunk in iter(lambda: audio.file.read(1024 * 1024), b""):
            size += len(chunk)
            logger.debug(f"Writing chunk ({size} bytes total)")
            if size > MAX_FILE_SIZE:
                logger.error("❌ Audio file too large (>10MB)")
                raise HTTPException(status_code=413, detail="Audio file is too large (max 10MB)")
            tmpfile.write(chunk)

        tmpfile.seek(0)
        tmpdir = tempfile.mkdtemp()
        logger.debug(f"Temporary directory created: {tmpdir}")

        try:
            audio_path = os.path.join(tmpdir, audio.filename)
            logger.debug(f"Saving file to: {audio_path}")
            with open(audio_path, "wb") as f:
                tmpfile.seek(0)
                shutil.copyfileobj(tmpfile, f)
            logger.debug("✅ File saved successfully")

            user = db.query(User).filter(User.id == user_uuid).first()
            if not user:
                logger.error("❌ User not found in database")
                raise HTTPException(status_code=404, detail="User not found")

            logger.debug(f"User language: {user.lang or 'auto'}")

            # Step 1: Convert and transcribe
            wav_path = convert_to_wav(audio_path)
            logger.debug(f"WAV path: {wav_path}")
            transcript = await transcribe_audio(wav_path, language=user.lang or "auto")
            logger.debug(f"Transcription result: {transcript.strip()}")

            # ✅ Normalize digits to words
            # transcript = await convert_digits_to_words(transcript, user.lang or "English")
            # logger.debug(f"Normalized transcript: {transcript}")


            if not transcript.strip():
                logger.error("❌ Empty transcription")
                db.delete(challenge)
                db.commit()
                raise HTTPException(status_code=400, detail="Could not transcribe audio")

            # transcript = normalize_numbers_to_words(transcript)
            transcript = await convert_digits_to_words(transcript, user.lang)
            
            # Step 2: Challenge verification
            match, ratio = fuzzy_match(transcript, challenge.text, threshold=MATCH_THRESHOLD)
            logger.debug(f"Challenge spoken: {transcript}")
            logger.debug(f"Expected challenge: {challenge.text}")
            logger.debug(f"Match: {match}, Similarity ratio: {ratio:.2f}")

            if not match:
                logger.warning("❌ Phrase mismatch detected")
                db.delete(challenge)
                db.commit()
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Phrase mismatch! Say the phrase exactly"}
                )

            # Step 3: Anti-Spoofing
            logger.debug("🚨 Running AASIST anti-spoofing detector...")
            aasist_raw = await _run_detector_in_executor(aasist_score, wav_path)
            spoof_prob = float(np.clip(aasist_raw, 0.0, 1.0))
            logger.debug(f"AASIST raw output: {aasist_raw}")
            logger.info(f"AASIST spoof probability: {spoof_prob:.6f}")

            if spoof_prob > SPOOF_THRESHOLD:
                logger.warning(f"⚠️ Spoof detected (prob={spoof_prob:.4f})")
                db.delete(challenge)
                db.commit()
                return JSONResponse(
                    status_code=400,
                    content={"detail": "We detected an artificial voice! Try again using your real voice."}
                )

            # Step 4: Upload and embedding
            logger.debug("⬆️ Uploading audio to S3...")
            s3_uri = upload_audio(audio_path, str(user_uuid), audio.filename)
            logger.debug(f"✅ Uploaded to S3: {s3_uri}")

            logger.debug("🧠 Computing voice embedding...")
            embedding = compute_embedding(audio_path)
            logger.debug("✅ Embedding computed successfully")

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
            logger.debug("🗃 Enrollment sample saved to DB")

            # Step 6: Check how many samples exist
            user_enrolls = db.query(Enrollment).filter(
                Enrollment.user_id == user_uuid, Enrollment.is_final == False
            ).all()
            logger.debug(f"Current enrollment samples: {len(user_enrolls)}")

            if len(user_enrolls) < REQUIRED_SAMPLES:
                remaining = REQUIRED_SAMPLES - len(user_enrolls)
                logger.debug(f"Still need {remaining} more samples")
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
            logger.debug("🧮 Averaging embeddings for final voiceprint...")
            embeddings = [np.frombuffer(e.embedding, dtype=np.float32) for e in user_enrolls]
            avg_embedding = np.mean(np.stack(embeddings), axis=0)

            for e in user_enrolls:
                db.delete(e)
            db.commit()
            logger.debug("🧹 Temporary enrollments deleted")

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
            logger.info("🎯 Final enrollment complete")

            return {
                "message": "✅ Enrollment complete. Final voiceprint created.",
                "user_id": str(user_uuid),
                "transcript": transcript.strip(),
                "average_samples": REQUIRED_SAMPLES,
                "audio_url": s3_uri,
                "spoof_prob": spoof_prob,
            }

        except Exception as e:
            logger.exception("❌ Enrollment failed due to exception:")
            db.rollback()
            raise HTTPException(status_code=500, detail=str(e))

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
            logger.debug(f"🧹 Cleaned up temporary directory: {tmpdir}")
