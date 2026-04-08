"""add telegram event outbox

Revision ID: 7b2d46a1c9f3
Revises: 4d5c9b8f6a71
Create Date: 2026-04-07 08:45:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7b2d46a1c9f3"
down_revision: Union[str, Sequence[str], None] = "4d5c9b8f6a71"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "telegram_event_outbox",
        sa.Column(
            "event_type",
            sa.Enum("PROPOSAL_CREATED", "USER_REGISTERED", name="telegrameventtype"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.String(length=36), nullable=True),
        sa.Column("recipient_user_id", sa.String(length=36), nullable=False),
        sa.Column("recipient_role", sa.String(length=32), nullable=True),
        sa.Column("delivery_channel", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "DISPATCHED", "FAILED", name="telegrameventstatus"),
            nullable=False,
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_type",
            "entity_id",
            "recipient_user_id",
            "delivery_channel",
            name="uq_telegram_event_outbox_identity",
        ),
    )
    op.create_index(op.f("ix_telegram_event_outbox_entity_id"), "telegram_event_outbox", ["entity_id"], unique=False)
    op.create_index(op.f("ix_telegram_event_outbox_entity_type"), "telegram_event_outbox", ["entity_type"], unique=False)
    op.create_index(op.f("ix_telegram_event_outbox_event_type"), "telegram_event_outbox", ["event_type"], unique=False)
    op.create_index(
        op.f("ix_telegram_event_outbox_recipient_user_id"),
        "telegram_event_outbox",
        ["recipient_user_id"],
        unique=False,
    )
    op.create_index(op.f("ix_telegram_event_outbox_status"), "telegram_event_outbox", ["status"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_telegram_event_outbox_status"), table_name="telegram_event_outbox")
    op.drop_index(op.f("ix_telegram_event_outbox_recipient_user_id"), table_name="telegram_event_outbox")
    op.drop_index(op.f("ix_telegram_event_outbox_event_type"), table_name="telegram_event_outbox")
    op.drop_index(op.f("ix_telegram_event_outbox_entity_type"), table_name="telegram_event_outbox")
    op.drop_index(op.f("ix_telegram_event_outbox_entity_id"), table_name="telegram_event_outbox")
    op.drop_table("telegram_event_outbox")
