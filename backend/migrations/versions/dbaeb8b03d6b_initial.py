"""initial"""

import sqlalchemy as sa
from alembic import op

revision = "dbaeb8b03d6b"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "login_attempts",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("until", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("rules", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "guest_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("digest"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("username", sa.String(length=120), nullable=True),
        sa.Column("local_code_digest", sa.String(length=64), nullable=True),
        sa.Column("issuer", sa.String(), nullable=True),
        sa.Column("subject", sa.String(), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issuer", "subject"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_users_local_code_digest", "users", ["local_code_digest"], unique=True)
    op.create_table(
        "sessions",
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("csrf", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("code_id", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        sa.Column("oauth", sa.JSON(), nullable=False),
        sa.Column("local_code_digest", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["code_id"], ["guest_codes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("digest"),
    )
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_sessions_expires_at"), ["expires_at"], unique=False)


def downgrade():
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sessions_expires_at"))

    op.drop_table("sessions")
    op.drop_index("ix_users_local_code_digest", table_name="users")
    op.drop_table("users")
    op.drop_table("guest_codes")
    op.drop_table("profiles")
    op.drop_table("login_attempts")
