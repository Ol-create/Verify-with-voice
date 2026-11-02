# tests/test_admin_companies.py
"""Admin company onboarding and management: /admin/companies."""
import datetime
import uuid

import pytest

from app.auth import create_access_token
from app.models import Company, Enrollment, User, VerificationLog
from app.services.credentials import issue_credential, revoke_credential
from fakes import EMBEDDING

URL = "/admin/companies"


def onboard(client, headers, **body):
    return client.post(URL, headers=headers, json={"name": "Globex", **body})


def get_token(client, key, secret, user_id="u1"):
    return client.post("/v1/token", headers={"X-API-KEY": key, "X-API-SECRET": secret}, json={"user_id": user_id})


# --- Access ---

@pytest.mark.parametrize("method,path", [
    ("get", URL), ("post", URL), ("get", f"{URL}/{uuid.uuid4()}"), ("patch", f"{URL}/{uuid.uuid4()}"),
])
def test_requires_admin(client, method, path):
    assert getattr(client, method)(path).status_code in (401, 403)


def test_end_user_token_rejected(client, auth_headers):
    assert client.get(URL, headers=auth_headers).status_code == 401


# --- Onboarding ---

def test_onboard_returns_working_credentials_once(client, admin_headers):
    res = onboard(client, admin_headers, email="Ops@Globex.example.com")
    assert res.status_code == 201, res.text
    body = res.json()

    company = body["company"]
    assert company["status"] == "active"
    assert company["email"] == "ops@globex.example.com"
    assert [c["key_prefix"] for c in company["credentials"]] == [body["api_key"][:12]]

    assert get_token(client, body["api_key"], body["api_secret"]).status_code == 200

    # the secret can't be read back afterwards
    detail = client.get(f"{URL}/{company['id']}", headers=admin_headers).text
    assert body["api_secret"] not in detail and body["api_key"] not in detail


def test_onboard_as_pending_cannot_get_tokens_yet(client, admin_headers):
    body = onboard(client, admin_headers, status="pending").json()
    assert get_token(client, body["api_key"], body["api_secret"]).status_code == 403


def test_onboard_duplicate_name_case_insensitive(client, admin_headers):
    assert onboard(client, admin_headers).status_code == 201
    res = client.post(URL, headers=admin_headers, json={"name": "  globex "})
    assert res.status_code == 409


@pytest.mark.parametrize("body", [
    {"name": "   "},
    {"name": "Globex", "email": "not-an-email"},
    {"name": "Globex", "status": "deleted"},
    {},
])
def test_onboard_validation(client, admin_headers, body):
    assert client.post(URL, headers=admin_headers, json=body).status_code == 422


# --- List ---

def _seed(db_session):
    a = Company(name="Alpha Bank", email="it@alpha.test", status="active")
    b = Company(name="Beta Pay", email="dev@beta.test", status="suspended")
    c = Company(name="Gamma Loans", status="pending")
    db_session.add_all([a, b, c])
    db_session.flush()
    issue_credential(db_session, a)
    issue_credential(db_session, a, "production")
    revoke_credential(issue_credential(db_session, b)[0])
    db_session.add_all([User(company_id=a.id, external_user_id=f"u{i}") for i in range(3)])
    db_session.commit()
    return a, b, c


def test_list_with_counts(client, admin_headers, db_session):
    _seed(db_session)
    body = client.get(URL, headers=admin_headers).json()
    assert body["total"] == 3
    by_name = {c["name"]: c for c in body["items"]}
    assert (by_name["Alpha Bank"]["user_count"], by_name["Alpha Bank"]["active_key_count"]) == (3, 2)
    assert (by_name["Beta Pay"]["user_count"], by_name["Beta Pay"]["active_key_count"]) == (0, 0)


def test_list_filters_and_search(client, admin_headers, db_session):
    _seed(db_session)

    def names(**params):
        return sorted(c["name"] for c in client.get(URL, headers=admin_headers, params=params).json()["items"])

    assert names(status="suspended") == ["Beta Pay"]
    assert names(q="alpha") == ["Alpha Bank"]
    assert names(q="BETA.test") == ["Beta Pay"]  # matches email, any case
    assert names(q="bank", status="suspended") == []
    assert client.get(URL, headers=admin_headers, params={"status": "deleted"}).status_code == 422


def test_list_pagination(client, admin_headers, db_session):
    _seed(db_session)
    first = client.get(URL, headers=admin_headers, params={"page_size": 2}).json()
    second = client.get(URL, headers=admin_headers, params={"page_size": 2, "page": 2}).json()
    assert first["total"] == second["total"] == 3
    assert len(first["items"]) == 2 and len(second["items"]) == 1
    assert {c["id"] for c in first["items"]}.isdisjoint(c["id"] for c in second["items"])
    assert client.get(URL, headers=admin_headers, params={"page_size": 500}).status_code == 422


# --- Detail ---

def test_detail_includes_keys_users_and_this_months_usage(client, admin_headers, company, user, db_session):
    long_ago = datetime.datetime.utcnow() - datetime.timedelta(days=62)
    db_session.add_all([
        VerificationLog(user_id=user.id, liveness_verified=True, identity_verified=True),
        VerificationLog(user_id=user.id, liveness_verified=True, identity_verified=False),
        VerificationLog(user_id=user.id, liveness_verified=True, identity_verified=True, created_at=long_ago),
        Enrollment(user_id=user.id, embedding=EMBEDDING.tobytes(), is_final=True),
    ])
    db_session.commit()

    body = client.get(f"{URL}/{company.id}", headers=admin_headers).json()
    assert body["user_count"] == 1
    assert body["credentials"][0]["name"] == "default"
    usage = body["usage_this_month"]
    assert (usage["verifications"], usage["verifications_succeeded"], usage["enrollments_completed"]) == (2, 1, 1)


def test_detail_unknown_company(client, admin_headers):
    assert client.get(f"{URL}/{uuid.uuid4()}", headers=admin_headers).status_code == 404
    assert client.get(f"{URL}/not-a-uuid", headers=admin_headers).status_code == 422


# --- Update ---

def test_suspend_blocks_company_immediately_then_activate(client, admin_headers, company, user):
    access = create_access_token({"user_id": str(user.id), "company_id": str(company.id)})
    voice = {"Authorization": f"Bearer {access}"}
    assert client.get("/v1/challenge", headers=voice).status_code == 200

    res = client.patch(f"{URL}/{company.id}", headers=admin_headers, json={"status": "suspended"})
    assert res.status_code == 200 and res.json()["status"] == "suspended"
    assert client.get("/v1/challenge", headers=voice).status_code == 403

    client.patch(f"{URL}/{company.id}", headers=admin_headers, json={"status": "active"})
    assert client.get("/v1/challenge", headers=voice).status_code == 200


def test_edit_name_and_email(client, admin_headers, company):
    res = client.patch(f"{URL}/{company.id}", headers=admin_headers, json={"name": " Acme Bank PLC ", "email": "Help@Acme.example.com"})
    assert res.status_code == 200
    assert (res.json()["name"], res.json()["email"], res.json()["status"]) == ("Acme Bank PLC", "help@acme.example.com", "active")

    res = client.patch(f"{URL}/{company.id}", headers=admin_headers, json={"email": None})
    assert res.json()["email"] is None


def test_rename_conflicts(client, admin_headers, company, db_session):
    db_session.add(Company(name="Globex"))
    db_session.commit()
    assert client.patch(f"{URL}/{company.id}", headers=admin_headers, json={"name": "GLOBEX"}).status_code == 409
    # changing only the case of its own name is fine
    assert client.patch(f"{URL}/{company.id}", headers=admin_headers, json={"name": "ACME BANK"}).status_code == 200


@pytest.mark.parametrize("body", [{"name": None}, {"name": ""}, {"status": None}, {"status": "deleted"}, {"email": "nope"}])
def test_update_validation(client, admin_headers, company, body):
    assert client.patch(f"{URL}/{company.id}", headers=admin_headers, json=body).status_code == 422


def test_update_unknown_company(client, admin_headers):
    assert client.patch(f"{URL}/{uuid.uuid4()}", headers=admin_headers, json={"status": "active"}).status_code == 404
