# tests/test_admin.py
"""Admin accounts, login, admin tokens and the create_admin script."""
import datetime
from unittest.mock import patch

import bcrypt
import pytest
from jose import jwt

from app.auth import create_access_token
from app.models import AdminUser
from app.utils.passwords import hash_password, password_problem, verify_password
from scripts import create_admin

ADMIN_EMAIL = "admin@truevoice.test"
ADMIN_PASSWORD = "correct horse battery"

_real_gensalt = bcrypt.gensalt


@pytest.fixture(autouse=True)
def fast_bcrypt():
    """Cheap bcrypt rounds so the suite stays fast (production uses the default 12)."""
    with patch("app.utils.passwords.bcrypt.gensalt", lambda: _real_gensalt(rounds=4)):
        yield


@pytest.fixture
def admin(db_session):
    admin = AdminUser(email=ADMIN_EMAIL, password_hash=hash_password(ADMIN_PASSWORD))
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return admin


def login(client, email=ADMIN_EMAIL, password=ADMIN_PASSWORD):
    return client.post("/admin/auth/login", json={"email": email, "password": password})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


# --- Passwords ---

def test_password_hash_round_trip():
    hashed = hash_password(ADMIN_PASSWORD)
    assert hashed != ADMIN_PASSWORD
    assert verify_password(ADMIN_PASSWORD, hashed)
    assert not verify_password("wrong password!", hashed)
    assert not verify_password(ADMIN_PASSWORD, None)


def test_password_rules():
    assert password_problem("short") is not None
    assert password_problem("x" * 73) is not None  # bcrypt would silently ignore the tail
    assert password_problem(ADMIN_PASSWORD) is None
    with pytest.raises(ValueError):
        hash_password("short")


# --- Login ---

def test_login_returns_working_admin_token(client, admin, db_session):
    res = login(client)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["expires_in"] == 480 * 60

    me = client.get("/admin/auth/me", headers=bearer(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == ADMIN_EMAIL

    db_session.expire_all()
    assert db_session.get(AdminUser, admin.id).last_login_at is not None


def test_login_email_is_case_insensitive(client, admin):
    assert login(client, email="  Admin@TrueVoice.test ").status_code == 200


@pytest.mark.parametrize("email,password", [
    (ADMIN_EMAIL, "wrong password!"),
    ("nobody@truevoice.test", ADMIN_PASSWORD),
])
def test_login_failures_look_the_same(client, admin, email, password):
    res = login(client, email=email, password=password)
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid email or password"


def test_deactivated_admin_cannot_log_in(client, admin, db_session):
    db_session.get(AdminUser, admin.id).is_active = False
    db_session.commit()
    res = login(client)
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid email or password"


def test_login_is_rate_limited(client, admin):
    for _ in range(5):
        login(client, password="wrong password!")
    assert login(client).status_code == 429


# --- Admin token checks ---

def test_admin_routes_require_token(client):
    assert client.get("/admin/auth/me").status_code in (401, 403)


def test_deactivating_admin_blocks_existing_token(client, admin, db_session):
    token = login(client).json()["access_token"]
    db_session.get(AdminUser, admin.id).is_active = False
    db_session.commit()
    assert client.get("/admin/auth/me", headers=bearer(token)).status_code == 401


def test_end_user_token_rejected_on_admin_routes(client, user):
    token = create_access_token({"user_id": str(user.id), "company_id": str(user.company_id)})
    assert client.get("/admin/auth/me", headers=bearer(token)).status_code == 401


def test_admin_token_rejected_on_voice_routes(client, admin):
    token = login(client).json()["access_token"]
    assert client.get("/v1/challenge", headers=bearer(token)).status_code == 401


def test_admin_claims_signed_with_wrong_secret_rejected(client, admin):
    forged = jwt.encode(
        {"sub": str(admin.id), "type": "admin",
         "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=5)},
        "test-access-secret",  # the end-user secret, not ADMIN_JWT_SECRET
        algorithm="HS256",
    )
    assert client.get("/admin/auth/me", headers=bearer(forged)).status_code == 401


# --- scripts/create_admin.py ---

def run_script(argv, *passwords):
    with patch("scripts.create_admin.getpass.getpass", side_effect=list(passwords)):
        return create_admin.main(argv)


def test_script_creates_admin_who_can_log_in(client, capsys):
    assert run_script(["--email", "New@TrueVoice.test"], ADMIN_PASSWORD, ADMIN_PASSWORD) == 0
    assert login(client, email="new@truevoice.test").status_code == 200


def test_script_rejects_duplicate_short_and_mismatched(capsys, admin):
    assert run_script(["--email", ADMIN_EMAIL], ADMIN_PASSWORD, ADMIN_PASSWORD) == 1
    assert run_script(["--email", "b@truevoice.test"], "short") == 1
    assert run_script(["--email", "c@truevoice.test"], ADMIN_PASSWORD, "something else!!") == 1


def test_script_reset_password_and_deactivate(client, capsys, admin):
    new_password = "a brand new passphrase"
    assert run_script(["--email", ADMIN_EMAIL, "--reset-password"], new_password, new_password) == 0
    assert login(client).status_code == 401
    assert login(client, password=new_password).status_code == 200

    assert create_admin.main(["--email", ADMIN_EMAIL, "--deactivate"]) == 0
    assert login(client, password=new_password).status_code == 401
    assert create_admin.main(["--email", "nobody@truevoice.test", "--activate"]) == 1
