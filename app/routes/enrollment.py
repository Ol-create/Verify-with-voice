import os
import tempfile
import shutil
import datetime
from fastapi import APIRouter, UploadFile, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Enrollment
from app.utils.audio import compute_embedding
from app.config import verify_token


router = APIRouter()

# 10 MB max upload size (adjust as needed)
MAX_FILE_SIZE = 10 * 1024 * 1024  


@router.post("/enroll-voice")
async def enroll_voice(
    user_id: str = Form(...),
    audio: UploadFile = Form(...),
    token: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    # 1. Prevent duplicate enrollment
    existing = db.query(Enrollment).filter(Enrollment.user_id == user_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="User already enrolled")

    # 2. Use SpooledTemporaryFile with size limit
    with tempfile.SpooledTemporaryFile(max_size=MAX_FILE_SIZE) as tmpfile:
        size = 0
        for chunk in iter(lambda: audio.file.read(1024 * 1024), b""):  # read 1MB chunks
            size += len(chunk)
            if size > MAX_FILE_SIZE:
                raise HTTPException(status_code=413, detail="File too large")
            tmpfile.write(chunk)

        tmpfile.seek(0)

        # Write to a real file inside a temp dir (so compute_embedding can read it)
        tmpdir = tempfile.mkdtemp()
        try:
            audio_path = os.path.join(tmpdir, audio.filename)
            with open(audio_path, "wb") as f:
                tmpfile.seek(0)
                shutil.copyfileobj(tmpfile, f)

            # 3. Extract embedding
            embedding = compute_embedding(audio_path)
            db.add(
                Enrollment(
                    user_id=user_id,
                    embedding=embedding.tobytes(),
                    created_at=datetime.datetime.utcnow(),
                )
            )
            db.commit()
            return {"message": "Enrollment successful"}
        finally:
            shutil.rmtree(tmpdir)
