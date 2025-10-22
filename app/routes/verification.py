# # app/routes/verification.py (UPDATED WITH LANGUAGE SUPPORT)

# import os
# import shutil
# import tempfile
# import uuid
# import datetime
# import numpy as np
# import asyncio
# from concurrent.futures import ThreadPoolExecutor

# from fastapi import APIRouter, UploadFile, Depends, HTTPException
# from sqlalchemy.orm import Session

# from app.db import get_db
# from app.models import Enrollment, VerificationLog, Challenge, User
# from app.utils.audio import transcribe_audio, compute_embedding, convert_to_wav
# from app.utils.verification import cosine_similarity, fuzzy_match
# from app.utils.storage import upload_audio
# from app.auth import verify_token
# from app.anti_spoofing.aasist import aasist_score

# router = APIRouter()

# # === CONFIGURATION CONSTANTS ===
# # SIMILARITY_THRESHOLD = 0.75
# SIMILARITY_THRESHOLD = 0.65
# CHALLENGE_TTL = 120
# SPOOF_THRESHOLD = 0.99999

# _DETECTOR_POOL = ThreadPoolExecutor(max_workers=2)


# async def _run_detector_in_executor(fn, audio_path: str):
#     """Run detector (AASIST) in a thread pool asynchronously."""
#     loop = asyncio.get_event_loop()
#     return await loop.run_in_executor(_DETECTOR_POOL, fn, audio_path)


# @router.post("/secure-verify-voice")
# async def secure_verify(
#     audio: UploadFile,
#     db: Session = Depends(get_db),
#     token_data: dict = Depends(verify_token),
# ):
#     """
#     Secure voice verification route.
#     Includes:
#       - Challenge phrase validation (transcription + fuzzy match)
#       - Spoof detection (AASIST)
#       - Voice similarity check (ECAPA)
#       - Uses user’s preferred language for transcription
#     """
#     print("\n[DEBUG] --- Starting secure_verify ---")

#     # ✅ Step 0: Validate user ID from token
#     user_id = token_data.get("user_id")
#     print(f"[DEBUG] user_id = {user_id}")
#     if not user_id:
#         raise HTTPException(status_code=401, detail="Invalid token payload")

#     try:
#         user_uuid = uuid.UUID(user_id)
#     except ValueError:
#         raise HTTPException(status_code=400, detail="Invalid user_id format (must be UUID).")

#     # ✅ Step 1: Fetch user (for language preference)
#     user = db.query(User).filter(User.id == user_uuid).first()
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")

#     print(f"[DEBUG] User language = {user.lang or 'auto'}")

#     # ✅ Step 2: Fetch the active challenge
#     challenge = (
#         db.query(Challenge)
#         .filter(Challenge.user_id == user_uuid)
#         .order_by(Challenge.created_at.desc())
#         .first()
#     )
#     print(f"[DEBUG] Challenge fetched = {challenge.text if challenge else None}")

#     if not challenge:
#         raise HTTPException(status_code=400, detail="No active challenge found")

#     # ✅ Step 3: Check if challenge expired
#     age = (datetime.datetime.utcnow() - challenge.created_at).total_seconds()
#     print(f"[DEBUG] Challenge age = {age:.2f}s")
#     if age > CHALLENGE_TTL:
#         db.delete(challenge)
#         db.commit()
#         raise HTTPException(status_code=400, detail="Challenge expired")

#     tmpdir = tempfile.mkdtemp()
#     print(f"[DEBUG] Created tmpdir: {tmpdir}")

#     try:
#         # ✅ Step 4: Save uploaded audio
#         audio_path = os.path.join(tmpdir, audio.filename)
#         with open(audio_path, "wb") as f:
#             shutil.copyfileobj(audio.file, f)
#         print(f"[DEBUG] Saved audio to {audio_path}")

#         # ✅ Step 5: Transcribe using user's preferred language
#         transcript = await transcribe_audio(audio_path, language=user.lang or "auto")
#         print(f"[DEBUG] Transcript: {transcript}")

#         # ✅ Step 6: Verify challenge phrase
#         matched, ratio = fuzzy_match(transcript, challenge.text, threshold=0.8)
#         print(f"[DEBUG] Fuzzy match result: matched={matched}, ratio={ratio:.2f}")

#         if not matched:
#             print("[DEBUG] Challenge mismatch → aborting.")
#             db.add(VerificationLog(
#                 user_id=user_uuid,
#                 phrase=transcript,
#                 similarity=0.0,
#                 liveness_verified=False,
#                 identity_verified=False,
#                 language_used=user.lang or "auto",
#             ))
#             db.delete(challenge)
#             db.commit()
#             raise HTTPException(status_code=401, detail="Phrase mismatch! Say the phrase exactly as displayed")

#         # ✅ Step 7: Spoof detection (AASIST)
#         print("[DEBUG] Starting AASIST spoof detection...")
#         wav_path = convert_to_wav(audio_path)
#         aasist_raw = await _run_detector_in_executor(aasist_score, wav_path)
#         spoof_prob = float(np.clip(aasist_raw, 0.0, 1.0))
#         print(f"[DEBUG] AASIST raw: {aasist_raw}, normalized: {spoof_prob}")

#         if spoof_prob > SPOOF_THRESHOLD:
#             print("[DEBUG] Spoof detected → aborting.")
#             db.add(VerificationLog(
#                 user_id=user_uuid,
#                 phrase=transcript,
#                 similarity=0.0,
#                 liveness_verified=True,
#                 identity_verified=False,
#                 aasist_score=spoof_prob,
#                 spoof_prob=spoof_prob,
#                 language_used=user.lang or "auto",
#             ))
#             db.query(Challenge).filter(Challenge.id == challenge.id).delete(synchronize_session=False)
#             db.commit()
#             raise HTTPException(status_code=401, detail=f"Audio flagged as spoof (prob={spoof_prob:.3f})")

#         # ✅ Step 8: Load enrollment embedding
#         print("[DEBUG] Loading enrollment embedding...")
#         enrollment = (
#             db.query(Enrollment)
#             .filter(Enrollment.user_id == user_uuid, Enrollment.is_final == True)
#             .first()
#         )
#         if not enrollment:
#             print("[DEBUG] No enrollment found.")
#             db.query(Challenge).filter(Challenge.id == challenge.id).delete(synchronize_session=False)
#             db.commit()
#             raise HTTPException(status_code=404, detail="User not fully enrolled")

#         enrolled_embedding = np.frombuffer(enrollment.embedding, dtype=np.float32)
#         new_embedding = compute_embedding(audio_path)
#         similarity = cosine_similarity(new_embedding, enrolled_embedding)
#         print(f"[DEBUG] Voice similarity: {similarity:.3f}")

#         verified = similarity > SIMILARITY_THRESHOLD
#         print(f"[DEBUG] Verified = {verified}")

#         # ✅ Step 9: Upload audio to storage
#         s3_uri = upload_audio(
#             audio_path,
#             str(user_uuid),
#             f"verifications/{uuid.uuid4()}-{audio.filename}",
#         )

#         # ✅ Step 10: Log result
#         log = VerificationLog(
#             user_id=user_uuid,
#             phrase=transcript,
#             similarity=float(similarity),
#             liveness_verified=True,
#             identity_verified=verified,
#             aasist_score=spoof_prob,
#             spoof_prob=spoof_prob,
#             # language_used=user.lang or "auto",
#         )
#         db.add(log)
#         db.query(Challenge).filter(Challenge.id == challenge.id).delete(synchronize_session=False)
#         db.commit()

#         print("[DEBUG] Verification complete ✅")
#         return {
#             "verified": verified,
#             "similarity": similarity,
#             "transcript": transcript,
#             "challenge_match": ratio,
#             "audio_url": s3_uri,
#             "detector_scores": {"aasist": spoof_prob},
#             "spoof_prob": spoof_prob,
#             "language_used": user.lang or "auto",
#         }

#     except HTTPException as e:
#         print(f"[DEBUG] HTTPException raised: {e.detail}")
#         raise
#     except Exception as e:
#         print(f"[DEBUG] ERROR: {str(e)}")
#         db.rollback()
#         db.query(Challenge).filter(Challenge.id == challenge.id).delete(synchronize_session=False)
#         db.commit()
#         raise HTTPException(status_code=500, detail=str(e))
#     finally:
#         shutil.rmtree(tmpdir, ignore_errors=True)
#         print("[DEBUG] Cleaned tmpdir")

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
from app.models import Enrollment, VerificationLog, Challenge, User
from app.utils.audio import transcribe_audio, compute_embedding, convert_to_wav
from app.utils.verification import cosine_similarity, fuzzy_match
from app.utils.storage import upload_audio
from app.auth import verify_token
from app.anti_spoofing.aasist import aasist_score

router = APIRouter()

SIMILARITY_THRESHOLD = 0.65
CHALLENGE_TTL = 120
SPOOF_THRESHOLD = 0.1999
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
    print("\n[DEBUG] --- Starting /secure-verify-voice ---")

    # ✅ Step 0: Validate user ID
    user_id = token_data.get("user_id")
    print(f"[DEBUG] Token user_id: {user_id}")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        print("[DEBUG] Invalid user_id format")
        raise HTTPException(status_code=400, detail="Invalid user_id format")

    if not audio or not audio.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Invalid or missing audio file")

    # ✅ Step 1: Fetch user
    user = db.query(User).filter(User.id == user_uuid).first()
    print(f"[DEBUG] Fetched user: {user}")
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # ✅ Step 2: Get most recent challenge
    challenge = (
        db.query(Challenge)
        .filter(Challenge.user_id == user_uuid)
        .order_by(Challenge.created_at.desc())
        .first()
    )
    print(f"[DEBUG] Latest challenge: {challenge}")

    if not challenge:
        raise HTTPException(status_code=400, detail="No active challenge found")

    # ✅ Step 3: Expiry check
    age = (datetime.datetime.utcnow() - challenge.created_at).total_seconds()
    print(f"[DEBUG] Challenge age: {age}s")
    if age > CHALLENGE_TTL:
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
        print(f"[DEBUG] Temp directory created at: {tmpdir}")

        try:
            # ✅ Step 4: Save uploaded audio properly
            audio_path = os.path.join(tmpdir, audio.filename)
            print(f"[DEBUG] Saving uploaded audio to {audio_path}")
            with open(audio_path, "wb") as f:
                tmpfile.seek(0)
                shutil.copyfileobj(tmpfile, f)

            # ✅ Step 5: Transcribe (language-aware)
            print(f"[DEBUG] Transcribing audio using language: {user.lang or 'auto'}")
            transcript = await transcribe_audio(audio_path, language=user.lang or "auto")
            print(f"[DEBUG] Transcript result: {transcript}")

            # ✅ Step 6: Phrase verification
            print(f"[DEBUG] Comparing transcript to challenge text: {challenge.text}")
            matched, ratio = fuzzy_match(transcript, challenge.text, threshold=0.8)
            print(f"[DEBUG] Phrase match result: matched={matched}, ratio={ratio}")

            if not matched:
                print("[DEBUG] Phrase mismatch — logging and aborting.")
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
            print("[DEBUG] Running AASIST anti-spoofing detection...")
            wav_path = convert_to_wav(audio_path)
            aasist_raw = await _run_detector_in_executor(aasist_score, wav_path)
            spoof_prob = float(np.clip(aasist_raw, 0.0, 1.0))
            print(f"[DEBUG] AASIST score={aasist_raw}, spoof_prob={spoof_prob}")

            if spoof_prob > SPOOF_THRESHOLD:
                print("[DEBUG] Spoof detected! Logging and aborting.")
                db.delete(challenge)
                db.commit()
                raise HTTPException(
                    status_code=403,
                    detail="We detected an artificial voice! Please use your real voice.",
                )

            # ✅ Step 8: Speaker verification
            print("[DEBUG] Loading enrollment embedding...")
            enrollment = (
                db.query(Enrollment)
                .filter(Enrollment.user_id == user_uuid, Enrollment.is_final == True)
                .first()
            )
            print(f"[DEBUG] Enrollment found: {enrollment is not None}")
            if not enrollment or not enrollment.embedding:
                raise HTTPException(status_code=404, detail="User not fully enrolled")

            print("[DEBUG] Computing new embedding...")
            enrolled_embedding = np.frombuffer(enrollment.embedding, dtype=np.float32).flatten()
            new_embedding = compute_embedding(audio_path).flatten()
            similarity = cosine_similarity(new_embedding, enrolled_embedding)
            print(f"[DEBUG] Computed similarity={similarity:.4f}")

            verified = similarity > SIMILARITY_THRESHOLD
            print(f"[DEBUG] Verification passed={verified}")

            if not verified:
                print("[DEBUG] Voice mismatch — logging failure.")
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
            print("[DEBUG] Uploading audio to S3...")
            s3_uri = upload_audio(
                audio_path,
                str(user_uuid),
                f"verifications/{uuid.uuid4()}-{audio.filename}",
            )
            print(f"[DEBUG] Uploaded audio URL: {s3_uri}")

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
            print("[DEBUG] Verification complete and committed to DB.")

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

        except HTTPException as e:
            print(f"[DEBUG] HTTPException caught: {e.detail}")
            raise
        except Exception as e:
            print(f"[DEBUG] Unexpected error: {str(e)}")
            db.rollback()
            if challenge in db:
                db.delete(challenge)
                db.commit()
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            print(f"[DEBUG] Cleaning up temp dir: {tmpdir}")
            shutil.rmtree(tmpdir, ignore_errors=True)
