"""Cuentas, sesiones revocables y catálogo compartido."""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "accounts",
        sa.Column("username", sa.String(), primary_key=True),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String()),
    )
    op.create_table(
        "account_sessions",
        sa.Column("digest", sa.String(), primary_key=True),
        sa.Column("username", sa.String(), sa.ForeignKey("accounts.username"), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
    )
    op.create_index("ix_account_sessions_expires_at", "account_sessions", ["expires_at"])
    op.create_table(
        "catalogue_groups",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
    )
    op.create_table(
        "published_designs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("family", sa.String(), nullable=False),
        sa.Column("project", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("media_type", sa.String(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.Float(), nullable=False),
        sa.Column("published_by", sa.String(), sa.ForeignKey("accounts.username"), nullable=False),
    )


def downgrade():
    op.drop_table("published_designs")
    op.drop_table("catalogue_groups")
    op.drop_index("ix_account_sessions_expires_at", table_name="account_sessions")
    op.drop_table("account_sessions")
    op.drop_table("accounts")
