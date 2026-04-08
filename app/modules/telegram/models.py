from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.telegram.enums import TelegramEventStatus, TelegramEventType
from app.shared.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class TelegramLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "telegram_links"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, unique=True, index=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
    telegram_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telegram_first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telegram_last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    unlinked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TelegramLinkSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "telegram_link_sessions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TelegramEventOutbox(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "telegram_event_outbox"
    __table_args__ = (
        UniqueConstraint(
            "event_type",
            "entity_id",
            "recipient_user_id",
            "delivery_channel",
            name="uq_telegram_event_outbox_identity",
        ),
    )

    event_type: Mapped[TelegramEventType] = mapped_column(Enum(TelegramEventType), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    recipient_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    recipient_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    delivery_channel: Mapped[str] = mapped_column(String(32), default="telegram_bot", nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[TelegramEventStatus] = mapped_column(
        Enum(TelegramEventStatus),
        default=TelegramEventStatus.PENDING,
        nullable=False,
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
