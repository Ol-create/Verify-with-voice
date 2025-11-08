# app/utils/security.py

# import hashlib
# import hmac
# import secrets

# def generate_secret_key(length: int = 32) -> str:
#     """Generate a random API secret key."""
#     return secrets.token_urlsafe(length)

# def hash_secret(secret: str) -> str:
#     """Hash an API secret using SHA-256 for safe DB storage."""
#     return hashlib.sha256(secret.encode()).hexdigest()

# def verify_secret(stored_hash: str, provided_secret: str) -> bool:
#     """Securely compare stored hash and provided secret."""
#     provided_hash = hash_secret(provided_secret)
#     return hmac.compare_digest(stored_hash, provided_hash)


# app/utils/security.py
import os
import secrets
from cryptography.fernet import Fernet
from fastapi import HTTPException, status

# =====================================================
# 🔐 SETUP ENCRYPTION KEY (must be same for encrypt/decrypt)
# =====================================================
FERNET_KEY = os.getenv("FERNET_KEY")

if not FERNET_KEY:
    raise RuntimeError(
        "Missing FERNET_KEY. Generate one with:\n"
        ">>> from cryptography.fernet import Fernet\n"
        ">>> print(Fernet.generate_key().decode())\n"
        "Then set it as an environment variable: FERNET_KEY=<your_key>"
    )

fernet = Fernet(FERNET_KEY.encode() if isinstance(FERNET_KEY, str) else FERNET_KEY)

# =====================================================
# 🔑 KEY GENERATION
# =====================================================
def generate_secret_key(length: int = 32) -> str:
    """Generate a random API secret key."""
    return secrets.token_urlsafe(length)

# =====================================================
# 🔒 ENCRYPTION / DECRYPTION
# =====================================================
def encrypt_secret(plaintext: str) -> str:
    """Encrypt a plaintext string and return the base64 ciphertext."""
    if plaintext is None:
        return None
    return fernet.encrypt(plaintext.encode()).decode()

def decrypt_secret(ciphertext: str) -> str:
    """Decrypt an encrypted string and return the plaintext."""
    if ciphertext is None:
        return None
    try:
        return fernet.decrypt(ciphertext.encode()).decode()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to decrypt stored value.",
        )
