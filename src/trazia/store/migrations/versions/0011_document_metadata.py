"""Tipo y tag indicados al subir un documento."""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documents", sa.Column("kind", sa.String(), nullable=True))
    op.add_column("documents", sa.Column("equipment_tag", sa.String(), nullable=True))


def downgrade():
    op.drop_column("documents", "equipment_tag")
    op.drop_column("documents", "kind")
