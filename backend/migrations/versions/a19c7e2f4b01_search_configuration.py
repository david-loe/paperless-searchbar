"""Admin-selected custom fields for the search form."""

import sqlalchemy as sa
from alembic import op

revision = "a19c7e2f4b01"
down_revision = "dbaeb8b03d6b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "search_configuration",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("custom_field_ids", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("search_configuration")
