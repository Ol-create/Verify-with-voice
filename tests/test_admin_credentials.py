# tests/test_admin_credentials.py
"""Admin API key management: /admin/companies/{id}/credentials and /admin/credentials/{id}/revoke."""
import uuid

import pytest

from app.models import ApiCredential

COMPANIES = "/admin/companies"


def onboard(client, headers, name="Globex"):
    res = client.post(COMPANIES, headers=headers, json={"name": name})
    assert res.status_code == 201, res.text
    return res.json()


def issue(client, headers, company_id, **body):
    return client.post(f"{COMPANIES}/{company_id}/credentials", headers=headers, json=body or None)


def list_keys(client, headers, company_id, **params):
    return client.get(f"{COMPANIES}/{company_id}/credentials", headers=headers, params=params)


def revoke(client, headers, credential_id):
    return client.post(f"/admin/credentials/{credential_id}/revoke", headers=headers)


def get_token(client, key, secret, user_id="u1"):
    return client.post("/v1/token", headers={"X-API-KEY": key, "X-API-SECRET": secret}, json={"user_id": user_id})


# --- Access ---

@pytest.mark.parametrize("method,path", [
    ("post", f"{COMPANIES}/{uuid.uuid4()}/credentials"),
    ("get", f"{COMPANIES}/{uuid.uuid4()}/credentials"),
    ("post", f"/admin/credentials/{uuid.uuid4()}/revoke"),
])
def test_requires_admin(client, auth_headers, method, path):
    assert getattr(client, method)(path).status_code in (401, 403)
    assert getattr(client, method)(path, headers=auth_headers).status_code == 401


@pytest.mark.parametrize("method,path,detail", [
    ("post", f"{COMPANIES}/{uuid.uuid4()}/credentials", "Company not found"),
    ("get", f"{COMPANIES}/{uuid.uuid4()}/credentials", "Company not found"),
    ("post", f"/admin/credentials/{uuid.uuid4()}/revoke", "API key not found"),
])
def test_unknown_ids_404(client, admin_headers, method, path, detail):
    res = getattr(client, method)(path, headers=admin_headers)
    assert res.status_code == 404
    assert res.json()["detail"] == detail


# --- Issue ---

def test_issue_returns_working_key_once(client, admin_headers, db_session):
    company = onboard(client, admin_headers)["company"]

    res = issue(client, admin_headers, company["id"], name="production")
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["credential"]["name"] == "production"
    assert body["credential"]["key_prefix"] == body["api_key"][:12]
    assert body["credential"]["revoked_at"] is None

    assert get_token(client, body["api_key"], body["api_secret"]).status_code == 200

    # only hashes are stored, and the list never shows the key or secret
    stored = db_session.get(ApiCredential, uuid.UUID(body["credential"]["id"]))
    assert body["api_key"] not in (stored.key_hash, stored.secret_hash)
    listing = list_keys(client, admin_headers, company["id"]).text
    assert body["api_key"] not in listing and body["api_secret"] not in listing


def test_issue_without_body_uses_default_name(client, admin_headers):
    company = onboard(client, admin_headers)["company"]
    res = issue(client, admin_headers, company["id"])
    assert res.status_code == 201, res.text
    assert res.json()["credential"]["name"] == "default"


@pytest.mark.parametrize("name", ["", "   ", "x" * 65])
def test_issue_rejects_bad_names(client, admin_headers, name):
    company = onboard(client, admin_headers)["company"]
    assert issue(client, admin_headers, company["id"], name=name).status_code == 422


def test_issue_to_suspended_company_does_not_grant_access(client, admin_headers):
    company = onboard(client, admin_headers)["company"]
    client.patch(f"{COMPANIES}/{company['id']}", headers=admin_headers, json={"status": "suspended"})

    body = issue(client, admin_headers, company["id"]).json()
    assert get_token(client, body["api_key"], body["api_secret"]).status_code == 403


# --- List ---

def test_list_newest_first_and_filters_revoked(client, admin_headers):
    company = onboard(client, admin_headers)["company"]
    first_id = company["credentials"][0]["id"]
    second = issue(client, admin_headers, company["id"], name="second").json()["credential"]
    revoke(client, admin_headers, first_id)

    everything = list_keys(client, admin_headers, company["id"]).json()
    assert {c["id"] for c in everything} == {first_id, second["id"]}
    assert everything[0]["id"] == second["id"]

    active = list_keys(client, admin_headers, company["id"], include_revoked="false").json()
    assert [c["id"] for c in active] == [second["id"]]


def test_list_only_shows_that_companys_keys(client, admin_headers):
    globex = onboard(client, admin_headers, "Globex")["company"]
    onboard(client, admin_headers, "Initech")
    assert [c["id"] for c in list_keys(client, admin_headers, globex["id"]).json()] == [
        globex["credentials"][0]["id"]
    ]


def test_list_shows_last_used(client, admin_headers):
    body = onboard(client, admin_headers)
    company = body["company"]
    assert list_keys(client, admin_headers, company["id"]).json()[0]["last_used_at"] is None

    get_token(client, body["api_key"], body["api_secret"])
    assert list_keys(client, admin_headers, company["id"]).json()[0]["last_used_at"] is not None


# --- Revoke ---

def test_revoke_stops_new_tokens_and_existing_ones(client, admin_headers):
    body = onboard(client, admin_headers)
    credential_id = body["company"]["credentials"][0]["id"]
    token = get_token(client, body["api_key"], body["api_secret"]).json()["access_token"]
    user_headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/v1/challenge", headers=user_headers).status_code == 200

    res = revoke(client, admin_headers, credential_id)
    assert res.status_code == 200, res.text
    assert res.json()["revoked_at"] is not None

    assert get_token(client, body["api_key"], body["api_secret"]).status_code == 401
    assert client.get("/v1/challenge", headers=user_headers).status_code == 401


def test_revoke_leaves_other_keys_working(client, admin_headers):
    body = onboard(client, admin_headers)
    other = issue(client, admin_headers, body["company"]["id"]).json()

    revoke(client, admin_headers, body["company"]["credentials"][0]["id"])
    assert get_token(client, other["api_key"], other["api_secret"]).status_code == 200


def test_revoke_twice_keeps_first_time(client, admin_headers):
    credential_id = onboard(client, admin_headers)["company"]["credentials"][0]["id"]
    first = revoke(client, admin_headers, credential_id).json()["revoked_at"]
    second = revoke(client, admin_headers, credential_id)
    assert second.status_code == 200
    assert second.json()["revoked_at"] == first
