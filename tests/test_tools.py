# tests/test_tools.py
"""S3 key format, phrase matching, OpenAI fallback and the company management script."""
import asyncio
import re
from unittest.mock import AsyncMock, patch

from app.models import Company
from app.utils.openai_client import convert_digits_to_words
from app.utils.storage import upload_audio
from app.utils.verification import fuzzy_match
from fakes import CHALLENGE
from scripts import manage_company


@patch("app.utils.storage.s3")
def test_upload_audio_key_and_content_type(mock_s3):
    uri = upload_audio("/tmp/sample.wav", "audio/user-1/verifications", "sample.wav")

    _, bucket, key = mock_s3.upload_file.call_args.args
    assert bucket == "test-bucket"
    assert re.fullmatch(r"audio/user-1/verifications/[0-9a-f-]{36}-sample\.wav", key)
    assert mock_s3.upload_file.call_args.kwargs["ExtraArgs"]["ContentType"] in ("audio/wav", "audio/x-wav")
    assert uri == f"s3://test-bucket/{key}"


def _printed_credentials(capsys):
    out = capsys.readouterr().out
    key = re.search(r"API key:\s+(\S+)", out).group(1)
    secret = re.search(r"API secret:\s+(\S+)", out).group(1)
    return key, secret


def test_create_company_prints_working_credentials(client, capsys, db_session):
    assert manage_company.main(["create", "Globex"]) == 0
    key, secret = _printed_credentials(capsys)

    company = db_session.query(Company).filter_by(name="Globex").one()
    assert company.api_key_prefix == key[:12]
    assert key not in (company.api_key_hash, company.api_secret_hash)

    res = client.post("/v1/token", headers={"X-API-KEY": key, "X-API-SECRET": secret}, json={"user_id": "u1"})
    assert res.status_code == 200


def test_create_company_twice_fails(capsys):
    assert manage_company.main(["create", "Globex"]) == 0
    assert manage_company.main(["create", "Globex"]) == 1


def test_rotate_replaces_old_credentials(client, capsys):
    manage_company.main(["create", "Globex"])
    old_key, old_secret = _printed_credentials(capsys)
    assert manage_company.main(["rotate", "Globex"]) == 0
    new_key, new_secret = _printed_credentials(capsys)

    def token(k, s):
        return client.post("/v1/token", headers={"X-API-KEY": k, "X-API-SECRET": s}, json={"user_id": "u1"})

    assert token(old_key, old_secret).status_code == 401
    assert token(new_key, new_secret).status_code == 200


def test_rotate_unknown_company(capsys):
    assert manage_company.main(["rotate", "Nobody"]) == 1


def test_fuzzy_match_ignores_case_and_punctuation():
    matched, ratio = fuzzy_match("Three, eight. One five SIX!", CHALLENGE, threshold=0.8)
    assert matched and ratio == 1.0


def test_fuzzy_match_rejects_unrelated_speech():
    assert not fuzzy_match("hello how are you", CHALLENGE, threshold=0.8)[0]
    assert not fuzzy_match("", CHALLENGE, threshold=0.8)[0]


def test_digit_conversion_falls_back_to_transcript_on_error():
    failing = AsyncMock(side_effect=RuntimeError("OpenAI down"))
    with patch("app.utils.openai_client.client.chat.completions.create", new=failing):
        assert asyncio.run(convert_digits_to_words("3 8 1 5 6", "en")) == "3 8 1 5 6"
