# tests/conftest.py
"""
Test setup that isolates the app from every external service:
- Settings get dummy values (set before app.config loads, so no real .env values are used)
- The ECAPA and AASIST models are stubbed, so nothing is loaded or downloaded
- PostgreSQL is swapped for an in-memory SQLite database
- OpenAI, S3 and the audio pipeline are mocked per test
"""
import os
import sys
import types
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TEST_ENV = {
    "DB_HOST": "localhost",
    "DB_PORT": "5432",
    "DB_NAME": "test",
    "DB_USER": "test",
    "DB_PASS": "test",
    "JWT_SECRET": "test-access-secret",
    "SECRET_KEY": "test-refresh-secret",
    "ADMIN_JWT_SECRET": "test-admin-secret",
    "RATE_LIMIT": "1000/minute",
    "OPENAI_API_KEY": "sk-test",
    "AWS_ACCESS_KEY_ID": "test",
    "AWS_SECRET_ACCESS_KEY": "test",
    "S3_BUCKET_NAME": "test-bucket",
    "AWS_REGION": "us-east-1",
}
os.environ.update(TEST_ENV)

# --- Stub heavy models before the app imports them ---
from speechbrain.inference import EncoderClassifier  # noqa: E402

patch.object(EncoderClassifier, "from_hparams", return_value=MagicMock()).start()

fake_aasist = types.ModuleType("app.anti_spoofing.aasist")
fake_aasist.aasist_score = MagicMock(return_value=0.01)
sys.modules["app.anti_spoofing.aasist"] = fake_aasist

# --- Swap PostgreSQL for in-memory SQLite ---
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.db  # noqa: E402

test_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
app.db.engine = test_engine
app.db.SessionLocal = TestSessionLocal

from fastapi.testclient import TestClient  # noqa: E402

from app.auth import create_access_token  # noqa: E402
from app.db import Base, get_db  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models import ApiCredential, Company, User  # noqa: E402
from app.utils.security import display_prefix, hash_credential  # noqa: E402

from fakes import API_KEY, API_SECRET, CHALLENGE, EMBEDDING  # noqa: E402


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


fastapi_app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    fastapi_app.state.limiter.reset()
    yield


@pytest.fixture
def client():
    return TestClient(fastapi_app)


@pytest.fixture
def db_session():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def company(db_session):
    company = Company(name="Acme Bank", status="active")
    company.credentials.append(ApiCredential(
        name="default",
        key_prefix=display_prefix(API_KEY),
        key_hash=hash_credential(API_KEY),
        secret_hash=hash_credential(API_SECRET),
    ))
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)
    return company


@pytest.fixture
def user(db_session, company):
    user = User(company_id=company.id, external_user_id="customer-42", lang="en")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def api_headers():
    return {"X-API-KEY": API_KEY, "X-API-SECRET": API_SECRET}


@pytest.fixture
def auth_headers(user):
    token = create_access_token(
        {"user_id": str(user.id), "company_id": str(user.company_id), "lang": user.lang}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def wav_file():
    return ("sample.wav", b"RIFF....WAVEfake-audio", "audio/wav")


def _mock_voice_pipeline(module: str):
    """Mock OpenAI, S3, AASIST and audio processing used by a voice route module."""
    return {
        "transcribe": patch(f"{module}.transcribe_audio", new=AsyncMock(return_value=CHALLENGE)),
        "digits": patch(f"{module}.convert_digits_to_words", new=AsyncMock(side_effect=lambda t, lang: t)),
        "wav": patch(f"{module}.convert_to_wav", side_effect=lambda p: p),
        "spoof": patch(f"{module}.aasist_score", return_value=0.01),
        "embed": patch(f"{module}.compute_embedding", return_value=EMBEDDING),
        "upload": patch(f"{module}.upload_audio", return_value="s3://test-bucket/audio/x/sample.wav"),
    }


@pytest.fixture
def mock_enroll_pipeline():
    patches = _mock_voice_pipeline("app.routes.enrollment")
    mocks = {name: p.start() for name, p in patches.items()}
    yield mocks
    for p in patches.values():
        p.stop()


@pytest.fixture
def mock_verify_pipeline():
    patches = _mock_voice_pipeline("app.routes.verification")
    mocks = {name: p.start() for name, p in patches.items()}
    yield mocks
    for p in patches.values():
        p.stop()


@pytest.fixture(autouse=True)
def mock_challenge_generator():
    """Always mocked, so no test can reach the OpenAI API."""
    with patch(
        "app.routes.challenge.generate_challenge_sentence", new=AsyncMock(return_value=CHALLENGE)
    ) as gen:
        yield gen
