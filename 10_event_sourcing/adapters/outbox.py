"""Outbox: events committed in the same transaction as the domain change.

A separate relay worker drains the outbox and publishes to Redis Streams.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, registry


outbox_metadata = MetaData()
outbox_registry = registry(metadata=outbox_metadata)


@dataclass
class OutboxRow:
    message_id: str
    event_type: str
    payload: str
    created_at: datetime
    sent_at: datetime | None = None
    id: int | None = None


outbox_table = Table(
    "outbox",
    outbox_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("message_id", String(64), unique=True, nullable=False),
    Column("event_type", String(100), nullable=False),
    Column("payload", Text, nullable=False),
    Column("created_at", DateTime, nullable=False),
    Column("sent_at", DateTime, nullable=True),
)


_outbox_mapped = False


def map_outbox() -> None:
    global _outbox_mapped
    if _outbox_mapped:
        return
    outbox_registry.map_imperatively(OutboxRow, outbox_table)
    _outbox_mapped = True


def create_outbox_schema(engine: Engine) -> None:
    outbox_metadata.create_all(engine)


def _default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"can't serialize {type(value).__name__}")


def serialize_event(event) -> tuple[str, str]:
    return type(event).__name__, json.dumps(asdict(event), default=_default)


class OutboxRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def append(self, event) -> str:
        event_type, payload = serialize_event(event)
        message_id = uuid.uuid4().hex
        self.session.add(
            OutboxRow(
                message_id=message_id,
                event_type=event_type,
                payload=payload,
                created_at=datetime.utcnow(),
            )
        )
        return message_id

    def fetch_unsent(self, limit: int = 50) -> list[OutboxRow]:
        return (
            self.session.query(OutboxRow)
            .filter(OutboxRow.sent_at.is_(None))
            .order_by(OutboxRow.id.asc())
            .limit(limit)
            .all()
        )

    def mark_sent(self, row: OutboxRow) -> None:
        row.sent_at = datetime.utcnow()
