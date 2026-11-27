"""Rol activo de una sesión."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("account_sessions", sa.Column("viewing_role", sa.String(), nullable=True))


def downgrade():
    op.drop_column("account_sessions", "viewing_role")
