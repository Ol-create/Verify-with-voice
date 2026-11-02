"""hash company API credentials

Replaces the Fernet-encrypted companies.api_key / api_secret columns with SHA-256
hashes, so the API never needs a decryption key and companies can be looked up by
key hash instead of decrypting every row.

Existing rows are converted in place. Earlier versions of the app stored credentials
in four ways, told apart by the format of the API key:

- Fernet tokens: decrypted with FERNET_KEY (set in the environment while this
  migration runs, not needed afterwards), then hashed
- "test_tv_" signup keys and downgrade() placeholders: plaintext, hashed as they are
- 32-character hex keys (secrets.token_hex(16)): plaintext, hashed as they are
- 64-character hex keys: already SHA-256 hashes (the old hash_secret()), kept as they are

If a value can't be decrypted the migration stops before changing anything.

Revision ID: b7c1d2e3f4a5
Revises: 042fdfb7c07a
Create Date: 2026-10-14
"""
import hashlib
import os
import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7c1d2e3f4a5"
down_revision: Union[str, Sequence[str], None] = "042fdfb7c07a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Values stored without encryption: old signup keys, and placeholders left by downgrade()
PLAINTEXT_PREFIXES = ("test_tv_", "revoked")
HEX_32 = re.compile(r"[0-9a-f]{32}")  # secrets.token_hex(16) keys, stored unencrypted
SHA256_HEX = re.compile(r"[0-9a-f]{64}")  # values already hashed by the old hash_secret()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _plaintext(value: str, fernet) -> str:
    if value.startswith(PLAINTEXT_PREFIXES):
        return value
    if fernet is None:
        raise RuntimeError(
            "companies table holds encrypted API credentials. Set FERNET_KEY to the key "
            "they were encrypted with, then run `alembic upgrade head` again."
        )
    from cryptography.fernet import InvalidToken

    try:
        return fernet.decrypt(value.encode()).decode()
    except InvalidToken:
        raise RuntimeError(
            "Could not decrypt a company's API credentials with the FERNET_KEY provided. "
            "No changes were made."
        )


def _convert(api_key: str, api_secret: str, fernet) -> tuple[str, str | None, str]:
    """Return (key_hash, key_prefix, secret_hash) for one company row."""
    # The key's format identifies how the row was stored; the secret was always stored the same way
    if SHA256_HEX.fullmatch(api_key) and SHA256_HEX.fullmatch(api_secret):
        return api_key, None, api_secret
    if HEX_32.fullmatch(api_key):
        return _sha256(api_key), api_key[:12], _sha256(api_secret)
    key = _plaintext(api_key, fernet)
    secret = _plaintext(api_secret, fernet)
    return _sha256(key), key[:12], _sha256(secret)


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, api_key, api_secret FROM companies")).fetchall()

    fernet = None
    if os.getenv("FERNET_KEY"):
        from cryptography.fernet import Fernet

        fernet = Fernet(os.environ["FERNET_KEY"].encode())

    # Decrypt everything first, so a bad key fails before any schema change
    converted = []
    for company_id, api_key, api_secret in rows:
        converted.append((company_id, *_convert(api_key, api_secret, fernet)))

    with op.batch_alter_table("companies") as batch:
        batch.add_column(sa.Column("api_key_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("api_key_prefix", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("api_secret_hash", sa.String(length=64), nullable=True))

    update = sa.text(
        "UPDATE companies SET api_key_hash = :key_hash, api_key_prefix = :prefix, "
        "api_secret_hash = :secret_hash WHERE id = :id"
    )
    for company_id, key_hash, prefix, secret_hash in converted:
        conn.execute(
            update,
            {"id": company_id, "key_hash": key_hash, "prefix": prefix, "secret_hash": secret_hash},
        )

    with op.batch_alter_table("companies") as batch:
        batch.alter_column("api_key_hash", existing_type=sa.String(length=64), nullable=False)
        batch.alter_column("api_secret_hash", existing_type=sa.String(length=64), nullable=False)
        batch.create_index("ix_companies_api_key_hash", ["api_key_hash"], unique=True)
        batch.drop_index("ix_companies_api_key")
        batch.drop_column("api_key")
        batch.drop_column("api_secret")


def downgrade() -> None:
    # Hashes can't be turned back into keys, so downgrading restores the old columns
    # with placeholder values. Every company must be issued new credentials afterwards.
    with op.batch_alter_table("companies") as batch:
        batch.add_column(sa.Column("api_key", sa.String(), nullable=True))
        batch.add_column(sa.Column("api_secret", sa.String(), nullable=True))

    op.execute("UPDATE companies SET api_key = 'revoked-' || api_key_hash, api_secret = 'revoked'")

    with op.batch_alter_table("companies") as batch:
        batch.alter_column("api_secret", existing_type=sa.String(), nullable=False)
        batch.create_index("ix_companies_api_key", ["api_key"], unique=True)
        batch.drop_index("ix_companies_api_key_hash")
        batch.drop_column("api_key_hash")
        batch.drop_column("api_key_prefix")
        batch.drop_column("api_secret_hash")
