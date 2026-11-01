"""Accounts and ownership: DATABASE_CONTRACT v1.1.0.

users, analysis_sessions, refresh_tokens; nullable owner columns on images/queries.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("email", sa.Text, nullable=False, unique=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("role", sa.Text, nullable=False, server_default="user"),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
    )
    op.create_table(
        "analysis_sessions",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("user_id", sa.Text, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
    )
    op.create_index("ix_analysis_sessions_user_id", "analysis_sessions", ["user_id"])
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("user_id", sa.Text, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.Text, nullable=False, unique=True),
        sa.Column("expires_at", sa.Text, nullable=False),
        sa.Column("revoked_at", sa.Text),
        sa.Column("created_at", sa.Text, nullable=False),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    with op.batch_alter_table("images") as b:
        b.add_column(sa.Column("user_id", sa.Text))
        b.add_column(sa.Column("filename", sa.Text))
        b.add_column(sa.Column("size_bytes", sa.Integer))
        b.create_index("ix_images_user_id", ["user_id"])
    with op.batch_alter_table("queries") as b:
        b.add_column(sa.Column("user_id", sa.Text))
        b.add_column(sa.Column("session_id", sa.Text))
        b.create_index("ix_queries_user_id", ["user_id"])
        b.create_index("ix_queries_session_id", ["session_id"])


def downgrade() -> None:
    with op.batch_alter_table("queries") as b:
        b.drop_index("ix_queries_session_id")
        b.drop_index("ix_queries_user_id")
        b.drop_column("session_id")
        b.drop_column("user_id")
    with op.batch_alter_table("images") as b:
        b.drop_index("ix_images_user_id")
        b.drop_column("size_bytes")
        b.drop_column("filename")
        b.drop_column("user_id")
    op.drop_table("refresh_tokens")
    op.drop_table("analysis_sessions")
    op.drop_table("users")
