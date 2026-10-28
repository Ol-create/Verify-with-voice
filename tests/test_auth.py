# tests/test_auth.py
"""Company credentials, access/refresh tokens and rate-limit keys."""
import datetime
from types import SimpleNamespace

from jose import jwt

from app.auth import create_access_token
from app.models import Company, User
from app.rate_limit import rate_limit_key
from app.utils.security import generate_api_credentials, hash_credential, verify_credential
from fakes import API_KEY, API_SECRET


def get_token(client, headers, user_id="customer-42", **extra):
    return client.post("/v1/token", headers=headers, json={"user_id": user_id, **extra})


# --- Credential helpers ---

def test_generated_credentials_are_unique_and_verifiable():
    key1, secret1 = generate_api_credentials()
    key2, _ = generate_api_credentials()
    assert key1 != key2
    assert verify_credential(secret1, hash_credential(secret1))
    assert not verify_credential("wrong", hash_credential(secret1))


# --- POST /v1/token ---

def test_token_issued_for_valid_credentials(client, company, api_headers, db_session):
    res = get_token(client, api_headers)
    assert res.status_code == 200, res.text
    body = res.json()

    payload = jwt.decode(body["access_token"], "test-access-secret", algorithms=["HS256"])
    assert payload["type"] == "access"
    assert payload["company_id"] == str(company.id)

    user = db_session.query(User).filter_by(external_user_id="customer-42").one()
    assert user.company_id == company.id
    # only the hash of the refresh token is stored
    assert user.refresh_token == hash_credential(body["refresh_token"])


def test_token_rejects_wrong_key(client, company):
    res = get_token(client, {"X-API-KEY": "tv_wrong", "X-API-SECRET": API_SECRET})
    assert res.status_code == 401


def test_token_rejects_wrong_secret(client, company):
    res = get_token(client, {"X-API-KEY": API_KEY, "X-API-SECRET": "wrong"})
    assert res.status_code == 401


def test_token_requires_credentials(client, company):
    assert get_token(client, {}).status_code == 422


def test_token_company_id_must_match_key(client, company, api_headers, db_session):
    other = Company(name="Other", api_key_hash="a" * 64, api_secret_hash="b" * 64)
    db_session.add(other)
    db_session.commit()

    assert get_token(client, api_headers, company_id=str(other.id)).status_code == 403
    assert get_token(client, api_headers, company_id=str(company.id)).status_code == 200


def test_same_external_user_reuses_record(client, company, api_headers, db_session):
    get_token(client, api_headers)
    get_token(client, api_headers)
    assert db_session.query(User).filter_by(external_user_id="customer-42").count() == 1


# --- Access token checks ---

def test_protected_route_requires_token(client):
    assert client.get("/v1/challenge").status_code in (401, 403)


def test_token_without_type_rejected(client, user):
    # tokens issued before this change had no "type" claim
    legacy = jwt.encode(
        {"user_id": str(user.id), "company_id": str(user.company_id),
         "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=5)},
        "test-access-secret", algorithm="HS256",
    )
    res = client.get("/v1/challenge", headers={"Authorization": f"Bearer {legacy}"})
    assert res.status_code == 401


def test_refresh_token_cannot_be_used_as_access_token(client, company, api_headers):
    refresh = get_token(client, api_headers).json()["refresh_token"]
    res = client.get("/v1/challenge", headers={"Authorization": f"Bearer {refresh}"})
    assert res.status_code == 401


# --- Refresh / revoke ---

def test_refresh_issues_new_access_token(client, company, api_headers):
    refresh = get_token(client, api_headers).json()["refresh_token"]
    res = client.post("/v1/token/refresh", json={"refresh_token": refresh})
    assert res.status_code == 200, res.text
    payload = jwt.decode(res.json()["access_token"], "test-access-secret", algorithms=["HS256"])
    assert payload["type"] == "access"


def test_refresh_rejects_access_token(client, company, api_headers):
    access = get_token(client, api_headers).json()["access_token"]
    assert client.post("/v1/token/refresh", json={"refresh_token": access}).status_code == 401


def test_revoked_refresh_token_stops_working(client, company, api_headers):
    refresh = get_token(client, api_headers).json()["refresh_token"]
    assert client.post("/v1/token/revoke", json={"refresh_token": refresh}).status_code == 200
    assert client.post("/v1/token/refresh", json={"refresh_token": refresh}).status_code == 401
    assert client.post("/v1/token/revoke", json={"refresh_token": refresh}).status_code == 404


# --- Rate-limit key ---

def _request(headers):
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host="1.2.3.4"))


def test_rate_limit_key_per_company_for_valid_token(user):
    token = create_access_token({"user_id": str(user.id), "company_id": str(user.company_id)})
    assert rate_limit_key(_request({"authorization": f"Bearer {token}"})) == f"company:{user.company_id}"


def test_rate_limit_key_falls_back_to_ip(user):
    forged = jwt.encode({"type": "access", "company_id": str(user.company_id)}, "wrong", algorithm="HS256")
    assert rate_limit_key(_request({})) == "ip:1.2.3.4"
    assert rate_limit_key(_request({"authorization": f"Bearer {forged}"})) == "ip:1.2.3.4"
