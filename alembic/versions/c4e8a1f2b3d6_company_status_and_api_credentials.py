"""company status and multiple API credentials

Adds companies.status / companies.email and moves API keys into their own
api_credentials table, so a company can hold several keys and revoke them one by one.

Each company's existing key becomes one credential named "default", so integrations
keep working with the same key and secret. Existing companies are set to "active".

Revision ID: c4e8a1f2b3d6
Revises: b7c1d2e3f4a5
Create Date: 2026-10-28
"""
import datetime
import hashlib
import secrets
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4e8a1f2b3d6"
down_revision: Union[str, Sequence[str], None] = "b7c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("companies") as batch:
        batch.add_column(sa.Column("email", sa.String(), nullable=True))
        batch.add_column(sa.Column("status", sa.String(length=16), nullable=False, server_default="active"))
        batch.create_check_constraint(
            "ck_companies_status", "status IN ('pending', 'active', 'suspended')"
        )

    credentials = op.create_table(
        "api_credentials",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("key_prefix", sa.String(length=16), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("secret_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_credentials_company_id", "api_credentials", ["company_id"])
    op.create_index("ix_api_credentials_key_hash", "api_credentials", ["key_hash"], unique=True)

    conn = op.get_bind()
    companies = sa.table(
        "companies",
        sa.column("id", sa.UUID()),
        sa.column("api_key_hash", sa.String()),
        sa.column("api_key_prefix", sa.String()),
        sa.column("api_secret_hash", sa.String()),
    )
    rows = conn.execute(
        sa.select(companies.c.id, companies.c.api_key_hash, companies.c.api_key_prefix, companies.c.api_secret_hash)
    ).fetchall()
    now = datetime.datetime.utcnow()
    if rows:
        op.bulk_insert(
            credentials,
            [
                {
                    "id": uuid.uuid4(),
                    "company_id": company_id,
                    "name": "default",
                    # rows created before prefixes were stored have none; show the start of the hash instead
                    "key_prefix": prefix or key_hash[:12],
                    "key_hash": key_hash,
                    "secret_hash": secret_hash,
                    "created_at": now,
                }
                for company_id, key_hash, prefix, secret_hash in rows
            ],
        )

    with op.batch_alter_table("companies") as batch:
        batch.drop_index("ix_companies_api_key_hash")
        batch.drop_column("api_key_hash")
        batch.drop_column("api_key_prefix")
        batch.drop_column("api_secret_hash")


def downgrade() -> None:
    # The old schema holds one key per company: keep each company's oldest active key.
    # Companies without one get a random placeholder and need new credentials afterwards.
    with op.batch_alter_table("companies") as batch:
        batch.add_column(sa.Column("api_key_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("api_key_prefix", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("api_secret_hash", sa.String(length=64), nullable=True))

    conn = op.get_bind()
    credentials = sa.table(
        "api_credentials",
        sa.column("company_id", sa.UUID()),
        sa.column("key_prefix", sa.String()),
        sa.column("key_hash", sa.String()),
        sa.column("secret_hash", sa.String()),
        sa.column("created_at", sa.DateTime()),
        sa.column("revoked_at", sa.DateTime()),
    )
    companies = sa.table(
        "companies",
        sa.column("id", sa.UUID()),
        sa.column("api_key_hash", sa.String()),
        sa.column("api_key_prefix", sa.String()),
        sa.column("api_secret_hash", sa.String()),
    )
    company_ids = [row[0] for row in conn.execute(sa.select(companies.c.id)).fetchall()]
    for company_id in company_ids:
        kept = conn.execute(
            sa.select(credentials.c.key_prefix, credentials.c.key_hash, credentials.c.secret_hash)
            .where(credentials.c.company_id == company_id, credentials.c.revoked_at.is_(None))
            .order_by(credentials.c.created_at)
            .limit(1)
        ).first()
        if kept:
            prefix, key_hash, secret_hash = kept
        else:
            placeholder = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
            prefix, key_hash, secret_hash = None, placeholder, placeholder
        conn.execute(
            companies.update()
            .where(companies.c.id == company_id)
            .values(api_key_hash=key_hash, api_key_prefix=prefix, api_secret_hash=secret_hash)
        )

    with op.batch_alter_table("companies") as batch:
        batch.alter_column("api_key_hash", existing_type=sa.String(length=64), nullable=False)
        batch.alter_column("api_secret_hash", existing_type=sa.String(length=64), nullable=False)
        batch.create_index("ix_companies_api_key_hash", ["api_key_hash"], unique=True)
        batch.drop_constraint("ck_companies_status", type_="check")
        batch.drop_column("status")
        batch.drop_column("email")

    op.drop_index("ix_api_credentials_key_hash", table_name="api_credentials")
    op.drop_index("ix_api_credentials_company_id", table_name="api_credentials")
    op.drop_table("api_credentials")
