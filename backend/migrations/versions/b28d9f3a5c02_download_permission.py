"""Download access is opt-in per user and guest code."""

import sqlalchemy as sa
from alembic import op

revision = "b28d9f3a5c02"
down_revision = "a19c7e2f4b01"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("users", "guest_codes"):
        op.add_column(
            table,
            sa.Column("allow_download", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade():
    for table in ("guest_codes", "users"):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("allow_download")
