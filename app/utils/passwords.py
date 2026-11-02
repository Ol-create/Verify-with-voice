# app/utils/passwords.py
"""
Password hashing for human accounts (admins now, company members later).

bcrypt, unlike the plain SHA-256 used for API credentials: people choose weak,
reused passwords, so the hash has to be slow and salted.
"""
import bcrypt

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_BYTES = 72  # bcrypt ignores anything longer, so it's rejected instead

# Compared against when an email doesn't exist, so a login takes the same time either way
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt()).decode()


def password_problem(password: str) -> str | None:
    """Why a new password is unacceptable, or None if it's fine."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return f"Password must be at most {MAX_PASSWORD_BYTES} bytes"
    return None


def hash_password(password: str) -> str:
    problem = password_problem(password)
    if problem:
        raise ValueError(problem)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-time check; pass None for an unknown account to keep timing uniform."""
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        encoded = b""  # never matches, but still spends the bcrypt time
    matched = bcrypt.checkpw(encoded, (password_hash or _DUMMY_HASH).encode())
    return matched and password_hash is not None
