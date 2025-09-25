"""Add anti-spoof scores to verification_logs and fix enrollments.id to UUID"""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "9e714f6623cf"
down_revision = None  # or the previous revision id before this one
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ✅ Fix enrollments.id (int → uuid)
    op.add_column(
        "enrollments",
        sa.Column(
            "id_new",
            sa.dialects.postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )

    op.drop_constraint("enrollments_pkey", "enrollments", type_="primary")
    op.drop_column("enrollments", "id")
    op.alter_column("enrollments", "id_new", new_column_name="id")
    op.create_primary_key("enrollments_pkey", "enrollments", ["id"])

    # ✅ Add anti-spoof columns to verification_logs
    op.add_column("verification_logs", sa.Column("aasist_score", sa.Float(), nullable=True))
    op.add_column("verification_logs", sa.Column("lcnn_score", sa.Float(), nullable=True))
    op.add_column("verification_logs", sa.Column("cqcc_gmm_score", sa.Float(), nullable=True))
    op.add_column("verification_logs", sa.Column("spoof_prob", sa.Float(), nullable=True))


def downgrade() -> None:
    # Rollback for verification_logs
    op.drop_column("verification_logs", "spoof_prob")
    op.drop_column("verification_logs", "cqcc_gmm_score")
    op.drop_column("verification_logs", "lcnn_score")
    op.drop_column("verification_logs", "aasist_score")

    # Rollback for enrollments.id (back to int autoincrement)
    op.add_column(
        "enrollments",
        sa.Column("id_old", sa.Integer, autoincrement=True, nullable=False),
    )
    op.drop_constraint("enrollments_pkey", "enrollments", type_="primary")
    op.drop_column("enrollments", "id")
    op.alter_column("enrollments", "id_old", new_column_name="id")
    op.create_primary_key("enrollments_pkey", "enrollments", ["id"])
