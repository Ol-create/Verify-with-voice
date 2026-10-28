# tests/test_voice.py
"""Challenge, enrollment and verification routes (OpenAI, S3 and models mocked)."""
import datetime

import numpy as np

from app.config import settings
from app.models import Challenge, Enrollment, VerificationLog
from fakes import CHALLENGE, EMBEDDING


def add_challenge(db, user, age_seconds=0):
    db.add(Challenge(
        user_id=user.id,
        text=CHALLENGE,
        created_at=datetime.datetime.utcnow() - datetime.timedelta(seconds=age_seconds),
    ))
    db.commit()


def add_final_enrollment(db, user, embedding=EMBEDDING):
    db.add(Enrollment(user_id=user.id, embedding=embedding.tobytes(), is_final=True))
    db.commit()


def enroll(client, headers, audio):
    return client.post("/v1/enroll-voice", headers=headers, files={"audio": audio})


def verify(client, headers, audio):
    return client.post("/v1/secure-verify-voice", headers=headers, files={"audio": audio})


# --- Challenge ---

def test_challenge_created_for_user(client, auth_headers, user, mock_challenge_generator, db_session):
    res = client.get("/v1/challenge", headers=auth_headers)
    assert res.status_code == 200, res.text
    assert res.json()["challenge_text"] == CHALLENGE
    assert db_session.query(Challenge).filter_by(user_id=user.id).count() == 1


# --- Enrollment ---

def test_enrollment_needs_three_samples(client, auth_headers, user, wav_file, mock_enroll_pipeline, db_session):
    for sample in (1, 2):
        add_challenge(db_session, user)
        res = enroll(client, auth_headers, wav_file)
        assert res.status_code == 200, res.text
        assert f"{sample}/3" in res.json()["message"]

    add_challenge(db_session, user)
    res = enroll(client, auth_headers, wav_file)
    assert res.status_code == 200, res.text
    assert "complete" in res.json()["message"].lower()

    db_session.expire_all()
    enrollments = db_session.query(Enrollment).filter_by(user_id=user.id).all()
    assert len(enrollments) == 1 and enrollments[0].is_final
    assert np.allclose(np.frombuffer(enrollments[0].embedding, dtype=np.float32), EMBEDDING)

    prefix = mock_enroll_pipeline["upload"].call_args.args[1]
    assert prefix == f"audio/{user.id}"


def test_enrollment_rejected_when_already_enrolled(client, auth_headers, user, wav_file, mock_enroll_pipeline, db_session):
    add_final_enrollment(db_session, user)
    assert enroll(client, auth_headers, wav_file).status_code == 400


def test_enrollment_without_challenge(client, auth_headers, user, wav_file, mock_enroll_pipeline):
    assert enroll(client, auth_headers, wav_file).status_code == 400


def test_enrollment_with_expired_challenge(client, auth_headers, user, wav_file, mock_enroll_pipeline, db_session):
    add_challenge(db_session, user, age_seconds=600)
    res = enroll(client, auth_headers, wav_file)
    assert res.status_code == 400
    assert res.json()["detail"] == "Challenge expired"


def test_enrollment_rejects_non_audio(client, auth_headers, user, mock_enroll_pipeline):
    res = enroll(client, auth_headers, ("notes.txt", b"hello", "text/plain"))
    assert res.status_code == 400


def test_enrollment_empty_transcript_is_400_not_500(client, auth_headers, user, wav_file, mock_enroll_pipeline, db_session):
    add_challenge(db_session, user)
    mock_enroll_pipeline["transcribe"].return_value = "   "
    res = enroll(client, auth_headers, wav_file)
    assert res.status_code == 400
    assert res.json()["detail"] == "Could not transcribe audio"


def test_enrollment_phrase_mismatch(client, auth_headers, user, wav_file, mock_enroll_pipeline, db_session):
    add_challenge(db_session, user)
    mock_enroll_pipeline["transcribe"].return_value = "zzzz"
    res = enroll(client, auth_headers, wav_file)
    assert res.status_code == 400
    mock_enroll_pipeline["upload"].assert_not_called()


def test_enrollment_spoof_detected(client, auth_headers, user, wav_file, mock_enroll_pipeline, db_session):
    add_challenge(db_session, user)
    mock_enroll_pipeline["spoof"].return_value = 0.95
    res = enroll(client, auth_headers, wav_file)
    assert res.status_code == 400
    assert "artificial" in res.json()["detail"]
    mock_enroll_pipeline["upload"].assert_not_called()


# --- Verification ---

def test_verify_success(client, auth_headers, user, wav_file, mock_verify_pipeline, db_session):
    add_final_enrollment(db_session, user)
    add_challenge(db_session, user)
    res = verify(client, auth_headers, wav_file)

    assert res.status_code == 200, res.text
    assert res.json()["verified"] is True
    log = db_session.query(VerificationLog).one()
    assert log.identity_verified and log.liveness_verified

    prefix = mock_verify_pipeline["upload"].call_args.args[1]
    assert prefix == f"audio/{user.id}/verifications"


def test_verify_different_voice(client, auth_headers, user, wav_file, mock_verify_pipeline, db_session):
    add_final_enrollment(db_session, user)
    add_challenge(db_session, user)
    mock_verify_pipeline["embed"].return_value = -EMBEDDING
    res = verify(client, auth_headers, wav_file)

    assert res.status_code == 401
    log = db_session.query(VerificationLog).one()
    assert log.liveness_verified and not log.identity_verified


def test_verify_phrase_mismatch(client, auth_headers, user, wav_file, mock_verify_pipeline, db_session):
    add_final_enrollment(db_session, user)
    add_challenge(db_session, user)
    mock_verify_pipeline["transcribe"].return_value = "zzzz"
    res = verify(client, auth_headers, wav_file)

    assert res.status_code == 401
    mock_verify_pipeline["embed"].assert_not_called()
    assert not db_session.query(VerificationLog).one().liveness_verified


def test_verify_unrelated_speech_rejected(client, auth_headers, user, wav_file, mock_verify_pipeline, db_session):
    add_final_enrollment(db_session, user)
    add_challenge(db_session, user)
    mock_verify_pipeline["transcribe"].return_value = "hello how are you"
    assert verify(client, auth_headers, wav_file).status_code == 401


def test_verify_accepts_punctuated_transcript(client, auth_headers, user, wav_file, mock_verify_pipeline, db_session):
    add_final_enrollment(db_session, user)
    add_challenge(db_session, user)
    mock_verify_pipeline["transcribe"].return_value = "Three, eight, one, five, six."
    assert verify(client, auth_headers, wav_file).status_code == 200


def test_verify_spoof_detected_and_logged(client, auth_headers, user, wav_file, mock_verify_pipeline, db_session):
    add_final_enrollment(db_session, user)
    add_challenge(db_session, user)
    mock_verify_pipeline["spoof"].return_value = 0.95
    assert verify(client, auth_headers, wav_file).status_code == 403

    log = db_session.query(VerificationLog).one()
    assert not log.liveness_verified and not log.identity_verified
    assert log.spoof_prob == 0.95
    mock_verify_pipeline["embed"].assert_not_called()


def test_spoof_threshold_comes_from_settings(client, auth_headers, user, wav_file, mock_verify_pipeline, db_session, monkeypatch):
    monkeypatch.setattr(settings, "SPOOF_THRESHOLD", 0.99)
    add_final_enrollment(db_session, user)
    add_challenge(db_session, user)
    mock_verify_pipeline["spoof"].return_value = 0.95
    assert verify(client, auth_headers, wav_file).status_code == 200


def test_verify_not_enrolled(client, auth_headers, user, wav_file, mock_verify_pipeline, db_session):
    add_challenge(db_session, user)
    assert verify(client, auth_headers, wav_file).status_code == 404


def test_challenge_is_single_use(client, auth_headers, user, wav_file, mock_verify_pipeline, db_session):
    add_final_enrollment(db_session, user)
    add_challenge(db_session, user)
    assert verify(client, auth_headers, wav_file).status_code == 200
    # replaying the same request without a new challenge fails
    assert verify(client, auth_headers, wav_file).status_code == 400
