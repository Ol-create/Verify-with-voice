# app/utils/security.py
"""
Company API credentials.

Only SHA-256 hashes of the API key and secret are stored. The plaintext values are
shown to the company once, when they are created, and can never be read back.
A plain (unsalted) hash is fine here because the values are long random tokens,
not human-chosen passwords, and it lets us look a company up by key hash directly.
"""
import hashlib
import hmac
import secrets

API_KEY_PREFIX = "tv_"
API_SECRET_PREFIX = "tv_sk_"
DISPLAY_PREFIX_LENGTH = 12  # how much of the key we keep in plaintext for display


def generate_api_credentials() -> tuple[str, str]:
    """Return a new random (api_key, api_secret) pair."""
    api_key = f"{API_KEY_PREFIX}{secrets.token_hex(16)}"
    api_secret = f"{API_SECRET_PREFIX}{secrets.token_urlsafe(32)}"
    return api_key, api_secret


def hash_credential(value: str) -> str:
    """SHA-256 hex digest used for storing and looking up credentials."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def verify_credential(value: str, stored_hash: str) -> bool:
    """Constant-time comparison of a provided credential against its stored hash."""
    return hmac.compare_digest(hash_credential(value), stored_hash)


def display_prefix(api_key: str) -> str:
    """Non-secret start of the key, safe to show in dashboards and logs."""
    return api_key[:DISPLAY_PREFIX_LENGTH]
