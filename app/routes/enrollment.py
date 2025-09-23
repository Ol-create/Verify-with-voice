# app/routes/enrollment.py

import os
import tempfile
import shutil
import datetime
from fastapi import APIRouter, UploadFile, Form, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Enrollment, Challenge
from app.utils.audio import compute_embedding, transcribe_audio
from app.utils.verification import fuzzy_match
from app.utils.storage import upload_audio
from app.auth import verify_token

router = APIRouter()

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
CHALLENGE_TTL = 30  # seconds


@router.post("/enroll-voice")
async def enroll_voice(
    audio: UploadFile = Form(...),
    token_data: dict = Depends(verify_token),   # ✅ Extract user_id from token
    db: Session = Depends(get_db),
):
    user_id = token_data.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    # ✅ Validate audio input
    if not audio or not audio.content_type.startswith("audio/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or missing audio file.",
        )

    # ✅ Prevent duplicate enrollment
    existing = db.query(Enrollment).filter(Enrollment.user_id == user_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already enrolled",
        )

    # ✅ Get latest challenge
    challenge = (
        db.query(Challenge)
        .filter(Challenge.user_id == user_id)
        .order_by(Challenge.created_at.desc())
        .first()
    )

    if not challenge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active challenge found",
        )

    # ✅ Check expiration
    if (datetime.datetime.utcnow() - challenge.created_at).total_seconds() > CHALLENGE_TTL:
        db.delete(challenge)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Challenge expired",
        )

    # ✅ Save file temporarily
    with tempfile.SpooledTemporaryFile(max_size=MAX_FILE_SIZE) as tmpfile:
        size = 0
        for chunk in iter(lambda: audio.file.read(1024 * 1024), b""):  # 1MB chunks
            size += len(chunk)
            if size > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Audio file is too large (max 10MB).",
                )
            tmpfile.write(chunk)

        tmpfile.seek(0)

        tmpdir = tempfile.mkdtemp()
        try:
            audio_path = os.path.join(tmpdir, audio.filename)
            with open(audio_path, "wb") as f:
                tmpfile.seek(0)
                shutil.copyfileobj(tmpfile, f)

            # ✅ Step 1: Transcribe with Whisper
            transcript = await transcribe_audio(audio_path)
            if not transcript.strip():
                db.delete(challenge)
                db.commit()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Could not transcribe audio. Try again.",
                )

            # ✅ Step 2: Verify spoken challenge
            match, ratio = fuzzy_match(transcript, challenge.text, threshold=0.8)
            if not match:
                db.delete(challenge)
                db.commit()
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Challenge phrase mismatch (similarity={ratio:.2f}).",
                )

            # ✅ Step 3: Upload raw audio to S3
            s3_uri = upload_audio(audio_path, user_id, audio.filename)

            # ✅ Step 4: Compute embedding + save
            embedding = compute_embedding(audio_path)
            db.add(
                Enrollment(
                    user_id=user_id,
                    embedding=embedding.tobytes(),
                    audio_url=s3_uri,
                    created_at=datetime.datetime.utcnow(),
                )
            )

            # ✅ Invalidate challenge after successful enrollment
            db.delete(challenge)

            db.commit()

            return {
                "message": "Enrollment successful",
                "user_id": user_id,
                "transcript": transcript.strip(),
                "similarity": ratio,
                "audio_url": s3_uri,
            }

        except Exception as e:
            # ✅ Always invalidate challenge if something goes wrong
            db.delete(challenge)
            db.commit()
            raise

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
