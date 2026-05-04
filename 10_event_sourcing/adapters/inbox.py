"""Inbox: dedup table keyed by message_id. Idempotent consumer pattern."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    MetaData,
    String,
    Table,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, registry


inbox_metadata = MetaData()
inbox_registry = registry(metadata=inbox_metadata)


class InboxRow:
    def __init__(self, message_id: str, processed_at: datetime) -> None:
        self.message_id = message_id
        self.processed_at = processed_at


inbox_table = Table(
    "inbox",
    inbox_metadata,
    Column("message_id", String(64), primary_key=True),
    Column("processed_at", DateTime, nullable=False),
)


_inbox_mapped = False


def map_inbox() -> None:
    global _inbox_mapped
    if _inbox_mapped:
        return
    inbox_registry.map_imperatively(InboxRow, inbox_table)
    _inbox_mapped = True


def create_inbox_schema(engine: Engine) -> None:
    inbox_metadata.create_all(engine)


class InboxRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def is_processed(self, message_id: str) -> bool:
        return (
            self.session.query(InboxRow).filter_by(message_id=message_id).first() is not None
        )

    def mark_processed(self, message_id: str) -> None:
        self.session.add(InboxRow(message_id=message_id, processed_at=datetime.utcnow()))
