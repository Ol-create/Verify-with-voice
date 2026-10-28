# app/services/credentials.py
"""Issue and revoke company API credentials (used by the CLI now, the admin and portal APIs later)."""
import datetime

from sqlalchemy.orm import Session

from app.models import ApiCredential, Company
from app.utils.security import display_prefix, generate_api_credentials, hash_credential


def issue_credential(db: Session, company: Company, name: str = "default") -> tuple[ApiCredential, str, str]:
    """
    Add a new key + secret to the company and return (credential, api_key, api_secret).
    The plaintext values are only available here; show them once, then they're gone.
    The caller commits.
    """
    api_key, api_secret = generate_api_credentials()
    credential = ApiCredential(
        company=company,
        name=name,
        key_prefix=display_prefix(api_key),
        key_hash=hash_credential(api_key),
        secret_hash=hash_credential(api_secret),
    )
    db.add(credential)
    return credential, api_key, api_secret


def revoke_credential(credential: ApiCredential) -> None:
    """Revoke a key. Already-revoked keys keep their original revoke time. The caller commits."""
    if credential.revoked_at is None:
        credential.revoked_at = datetime.datetime.utcnow()


def active_credentials(company: Company) -> list[ApiCredential]:
    return [c for c in company.credentials if c.is_active]
