# # app/routes/enrollment.py

# import os
# import tempfile
# import shutil
# import datetime
# import uuid
# import logging
# import numpy as np
# from fastapi import APIRouter, UploadFile, Form, Depends, HTTPException, status
# from sqlalchemy.orm import Session

# from app.db import get_db
# from app.models import Enrollment, Challenge, User
# from app.utils.audio import compute_embedding, transcribe_audio, convert_to_wav
# from app.utils.verification import fuzzy_match
# from app.utils.storage import upload_audio
# from app.auth import verify_token

# router = APIRouter()
# logger = logging.getLogger(__name__)

# MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
# CHALLENGE_TTL = 120  # seconds
# REQUIRED_SAMPLES = 3  # 3 enrollments before averaging


# @router.post("/enroll-voice")
# async def enroll_voice(
#     audio: UploadFile = Form(...),
#     token_data: dict = Depends(verify_token),
#     db: Session = Depends(get_db),
# ):
#     """Handles multi-sample voice enrollment (3 recordings per user)."""
#     user_id = token_data.get("user_id")
#     if not user_id:
#         raise HTTPException(status_code=401, detail="Invalid token payload")

#     # ✅ Convert user_id to UUID
#     try:
#         user_uuid = uuid.UUID(user_id)
#     except ValueError:
#         raise HTTPException(status_code=400, detail="Invalid user_id format (must be UUID).")

#     # ✅ Validate audio input
#     if not audio or not audio.content_type.startswith("audio/"):
#         raise HTTPException(status_code=400, detail="Invalid or missing audio file.")

#     # ✅ Check if user already fully enrolled
#     existing_final = (
#         db.query(Enrollment)
#         .filter(Enrollment.user_id == user_uuid, Enrollment.is_final == True)
#         .first()
#     )
#     if existing_final:
#         raise HTTPException(status_code=400, detail="User already fully enrolled.")

#     # ✅ Get latest challenge
#     challenge = (
#         db.query(Challenge)
#         .filter(Challenge.user_id == user_uuid)
#         .order_by(Challenge.created_at.desc())
#         .first()
#     )
#     if not challenge:
#         raise HTTPException(status_code=400, detail="No active challenge found")

#     # ✅ Check expiration
#     age = (datetime.datetime.utcnow() - challenge.created_at).total_seconds()
#     if age > CHALLENGE_TTL:
#         db.delete(challenge)
#         db.commit()
#         raise HTTPException(status_code=400, detail="Challenge expired")

#     # ✅ Save uploaded audio temporarily
#     with tempfile.SpooledTemporaryFile(max_size=MAX_FILE_SIZE) as tmpfile:
#         size = 0
#         for chunk in iter(lambda: audio.file.read(1024 * 1024), b""):  # 1 MB chunks
#             size += len(chunk)
#             if size > MAX_FILE_SIZE:
#                 raise HTTPException(status_code=413, detail="Audio file is too large (max 10MB).")
#             tmpfile.write(chunk)

#         tmpfile.seek(0)
#         tmpdir = tempfile.mkdtemp()

#         try:
#             audio_path = os.path.join(tmpdir, audio.filename)
#             with open(audio_path, "wb") as f:
#                 tmpfile.seek(0)
#                 shutil.copyfileobj(tmpfile, f)

#             # ✅ Step 1: Retrieve user language from DB
#             user = db.query(User).filter(User.id == user_uuid).first()
#             if not user:
#                 raise HTTPException(status_code=404, detail="User not found")

#             # ✅ Step 2: Transcribe audio in user's preferred language
#             wav_path = convert_to_wav(audio_path)
#             transcript = await transcribe_audio(wav_path, language=user.lang or "auto")


#             if not transcript.strip():
#                 db.delete(challenge)
#                 db.commit()
#                 raise HTTPException(status_code=400, detail="Could not transcribe audio. Try again.")

#             # ✅ Step 3: Match spoken challenge (must match current challenge)
#             match, ratio = fuzzy_match(transcript, challenge.text, threshold=0.7)
#             if not match:
#                 db.delete(challenge)
#                 db.commit()
#                 raise HTTPException(status_code=401, detail=f"Challenge mismatch (similarity={ratio:.2f}).")

#             # ✅ Step 4: Upload audio to S3
#             s3_uri = upload_audio(audio_path, str(user_uuid), audio.filename)

#             # ✅ Step 5: Compute embedding
#             embedding = compute_embedding(audio_path)

#             # ✅ Step 6: Save as a temporary enrollment (not final yet)
#             enrollment = Enrollment(
#                 user_id=user_uuid,
#                 embedding=embedding.astype(np.float32).tobytes(),
#                 audio_url=s3_uri,
#                 created_at=datetime.datetime.utcnow(),
#                 is_final=False,
#             )
#             db.add(enrollment)
#             db.commit()

#             # ✅ Step 7: Count how many enrollments exist for user
#             user_enrolls = (
#                 db.query(Enrollment)
#                 .filter(Enrollment.user_id == user_uuid, Enrollment.is_final == False)
#                 .all()
#             )

#             if len(user_enrolls) < REQUIRED_SAMPLES:
#                 remaining = REQUIRED_SAMPLES - len(user_enrolls)
#                 db.delete(challenge)
#                 db.commit()
#                 return {
#                     "message": f"Enrollment sample {len(user_enrolls)}/{REQUIRED_SAMPLES} saved. {remaining} more needed.",
#                     "transcript": transcript.strip(),
#                     "similarity": ratio,
#                     "audio_url": s3_uri,
#                 }

#             # ✅ Step 8: Average embeddings if all 3 samples done
#             embeddings = [np.frombuffer(e.embedding, dtype=np.float32) for e in user_enrolls]
#             avg_embedding = np.mean(np.stack(embeddings), axis=0)
#             avg_bytes = avg_embedding.astype(np.float32).tobytes()

#             # ✅ Step 9: Delete temp enrollments and create final record
#             for e in user_enrolls:
#                 db.delete(e)
#             db.commit()

#             final_enrollment = Enrollment(
#                 user_id=user_uuid,
#                 embedding=avg_bytes,
#                 audio_url=s3_uri,
#                 created_at=datetime.datetime.utcnow(),
#                 is_final=True,
#             )
#             db.add(final_enrollment)

#             # ✅ Step 10: Invalidate challenge after success
#             db.delete(challenge)
#             db.commit()

#             return {
#                 "message": "✅ Enrollment complete. Final voiceprint created.",
#                 "user_id": str(user_uuid),
#                 "transcript": transcript.strip(),
#                 "average_samples": REQUIRED_SAMPLES,
#                 "audio_url": s3_uri,
#             }

#         except Exception as e:
#             logger.exception("Enrollment failed: %s", str(e))
#             db.delete(challenge)
#             db.commit()
#             raise HTTPException(status_code=500, detail="Internal server error during enrollment.")

#         finally:
#             shutil.rmtree(tmpdir, ignore_errors=True)


import os
import tempfile
import shutil
import datetime
import uuid
import logging
import numpy as np
from fastapi import APIRouter, UploadFile, Form, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Enrollment, Challenge, User
from app.utils.audio import compute_embedding, transcribe_audio, convert_to_wav
from app.utils.verification import fuzzy_match
from app.utils.storage import upload_audio
from app.auth import verify_token

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
CHALLENGE_TTL = 120  # seconds
REQUIRED_SAMPLES = 3  # 3 enrollments before averaging


@router.post("/enroll-voice")
async def enroll_voice(
    # FIX: Change 'audio: UploadFile = Form(...)' to 'audio: UploadFile'
    audio: UploadFile,
    token_data: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Handles multi-sample voice enrollment (3 recordings per user)."""
    user_id = token_data.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    # ✅ Convert user_id to UUID
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id format (must be UUID).")

    # ✅ Validate audio input
    if not audio or not audio.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Invalid or missing audio file.")

    # ✅ Check if user already fully enrolled
    existing_final = (
        db.query(Enrollment)
        .filter(Enrollment.user_id == user_uuid, Enrollment.is_final == True)
        .first()
    )
    if existing_final:
        raise HTTPException(status_code=400, detail="User already fully enrolled.")

    # ✅ Get latest challenge
    challenge = (
        db.query(Challenge)
        .filter(Challenge.user_id == user_uuid)
        .order_by(Challenge.created_at.desc())
        .first()
    )
    if not challenge:
        raise HTTPException(status_code=400, detail="No active challenge found")

    # ✅ Check expiration
    age = (datetime.datetime.utcnow() - challenge.created_at).total_seconds()
    if age > CHALLENGE_TTL:
        db.delete(challenge)
        db.commit()
        raise HTTPException(status_code=400, detail="Challenge expired")

    # ✅ Save uploaded audio temporarily
    with tempfile.SpooledTemporaryFile(max_size=MAX_FILE_SIZE) as tmpfile:
        size = 0
        for chunk in iter(lambda: audio.file.read(1024 * 1024), b""):  # 1 MB chunks
            size += len(chunk)
            if size > MAX_FILE_SIZE:
                raise HTTPException(status_code=413, detail="Audio file is too large (max 10MB).")
            tmpfile.write(chunk)

        tmpfile.seek(0)
        tmpdir = tempfile.mkdtemp()

        try:
            audio_path = os.path.join(tmpdir, audio.filename)
            with open(audio_path, "wb") as f:
                tmpfile.seek(0)
                shutil.copyfileobj(tmpfile, f)

            # ✅ Step 1: Retrieve user language from DB
            user = db.query(User).filter(User.id == user_uuid).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            # ✅ Step 2: Transcribe audio in user's preferred language
            wav_path = convert_to_wav(audio_path)
            transcript = await transcribe_audio(wav_path, language=user.lang or "auto")

            if not transcript.strip():
                db.delete(challenge)
                db.commit()
                raise HTTPException(status_code=400, detail="Could not transcribe audio. Try again.")

            # ✅ Step 3: Match spoken challenge (must match current challenge)
            match, ratio = fuzzy_match(transcript, challenge.text, threshold=0.7)
            if not match:
                db.delete(challenge)
                db.commit()
                raise HTTPException(
                    status_code=400,
                    detail=f"Challenge mismatch (similarity={ratio:.2f}). Please read the text exactly as shown."
                )

            # ✅ Step 4: Upload audio to S3
            s3_uri = upload_audio(audio_path, str(user_uuid), audio.filename)

            # ✅ Step 5: Compute embedding
            embedding = compute_embedding(audio_path)

            # ✅ Step 6: Save as a temporary enrollment (not final yet)
            enrollment = Enrollment(
                user_id=user_uuid,
                embedding=embedding.astype(np.float32).tobytes(),
                audio_url=s3_uri,
                created_at=datetime.datetime.utcnow(),
                is_final=False,
            )
            db.add(enrollment)
            db.commit()

            # ✅ Step 7: Count how many enrollments exist for user
            user_enrolls = (
                db.query(Enrollment)
                .filter(Enrollment.user_id == user_uuid, Enrollment.is_final == False)
                .all()
            )

            if len(user_enrolls) < REQUIRED_SAMPLES:
                remaining = REQUIRED_SAMPLES - len(user_enrolls)
                db.delete(challenge)
                db.commit()
                return {
                    "message": f"Enrollment sample {len(user_enrolls)}/{REQUIRED_SAMPLES} saved. {remaining} more needed.",
                    "transcript": transcript.strip(),
                    "similarity": ratio,
                    "audio_url": s3_uri,
                }

            # ✅ Step 8: Average embeddings if all 3 samples done
            embeddings = [np.frombuffer(e.embedding, dtype=np.float32) for e in user_enrolls]
            avg_embedding = np.mean(np.stack(embeddings), axis=0)
            avg_bytes = avg_embedding.astype(np.float32).tobytes()

            # ✅ Step 9: Delete temp enrollments and create final record
            for e in user_enrolls:
                db.delete(e)
            db.commit()

            final_enrollment = Enrollment(
                user_id=user_uuid,
                embedding=avg_bytes,
                audio_url=s3_uri,
                created_at=datetime.datetime.utcnow(),
                is_final=True,
            )
            db.add(final_enrollment)

            # ✅ Step 10: Invalidate challenge after success
            db.delete(challenge)
            db.commit()

            return {
                "message": "✅ Enrollment complete. Final voiceprint created.",
                "user_id": str(user_uuid),
                "transcript": transcript.strip(),
                "average_samples": REQUIRED_SAMPLES,
                "audio_url": s3_uri,
            }

        except Exception as e:
            logger.exception("Enrollment failed: %s", str(e))
            db.delete(challenge)
            db.commit()
            raise HTTPException(status_code=500, detail="Internal server error during enrollment.")

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
