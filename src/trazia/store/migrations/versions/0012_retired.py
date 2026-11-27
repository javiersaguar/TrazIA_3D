"""Fichas y revisiones borradas o retiradas, para que la siembra no las recupere."""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "retired",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("equipment_id", sa.String(), nullable=True),
        sa.Column("tag_key", sa.String(), nullable=False),
        sa.Column("revision", sa.String(), nullable=True),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=False),
    )
    op.create_index("ix_retired_project_id", "retired", ["project_id"])
    op.create_index("ix_retired_tag_key", "retired", ["tag_key"])


def downgrade():
    op.drop_index("ix_retired_tag_key", "retired")
    op.drop_index("ix_retired_project_id", "retired")
    op.drop_table("retired")
