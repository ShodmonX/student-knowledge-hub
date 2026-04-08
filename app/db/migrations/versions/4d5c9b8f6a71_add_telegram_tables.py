"""add telegram tables

Revision ID: 4d5c9b8f6a71
Revises: 160cc8cb219d
Create Date: 2026-04-05 16:40:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4d5c9b8f6a71"
down_revision: Union[str, Sequence[str], None] = "160cc8cb219d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "telegram_links",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_username", sa.String(length=255), nullable=True),
        sa.Column("telegram_first_name", sa.String(length=255), nullable=True),
        sa.Column("telegram_last_name", sa.String(length=255), nullable=True),
        sa.Column("language_code", sa.String(length=16), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("unlinked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_telegram_links_telegram_user_id"), "telegram_links", ["telegram_user_id"], unique=True)
    op.create_index(op.f("ix_telegram_links_user_id"), "telegram_links", ["user_id"], unique=True)

    op.create_table(
        "telegram_link_sessions",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_telegram_link_sessions_code_hash"), "telegram_link_sessions", ["code_hash"], unique=True)
    op.create_index(op.f("ix_telegram_link_sessions_expires_at"), "telegram_link_sessions", ["expires_at"], unique=False)
    op.create_index(op.f("ix_telegram_link_sessions_token_hash"), "telegram_link_sessions", ["token_hash"], unique=True)
    op.create_index(op.f("ix_telegram_link_sessions_user_id"), "telegram_link_sessions", ["user_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_telegram_link_sessions_user_id"), table_name="telegram_link_sessions")
    op.drop_index(op.f("ix_telegram_link_sessions_token_hash"), table_name="telegram_link_sessions")
    op.drop_index(op.f("ix_telegram_link_sessions_expires_at"), table_name="telegram_link_sessions")
    op.drop_index(op.f("ix_telegram_link_sessions_code_hash"), table_name="telegram_link_sessions")
    op.drop_table("telegram_link_sessions")

    op.drop_index(op.f("ix_telegram_links_user_id"), table_name="telegram_links")
    op.drop_index(op.f("ix_telegram_links_telegram_user_id"), table_name="telegram_links")
    op.drop_table("telegram_links")
