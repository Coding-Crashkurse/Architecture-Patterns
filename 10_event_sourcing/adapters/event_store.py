"""Event store: append-only log of events per stream, plus periodic snapshots."""

from __future__ import annotations

import json
from dataclasses import asdict
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
    UniqueConstraint,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, registry

from domain.loan_es import LoanEvent, LoanState, apply, upcast


es_metadata = MetaData()
es_registry = registry(metadata=es_metadata)


class EventRow:
    def __init__(
        self,
        stream_id: str,
        sequence: int,
        event_type: str,
        payload: str,
        recorded_at: datetime,
        id: int | None = None,
    ) -> None:
        self.stream_id = stream_id
        self.sequence = sequence
        self.event_type = event_type
        self.payload = payload
        self.recorded_at = recorded_at
        self.id = id


class SnapshotRow:
    def __init__(
        self,
        stream_id: str,
        sequence: int,
        state: str,
        recorded_at: datetime,
        id: int | None = None,
    ) -> None:
        self.stream_id = stream_id
        self.sequence = sequence
        self.state = state
        self.recorded_at = recorded_at
        self.id = id


events_table = Table(
    "loan_events",
    es_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("stream_id", String(64), nullable=False),
    Column("sequence", Integer, nullable=False),
    Column("event_type", String(50), nullable=False),
    Column("payload", Text, nullable=False),
    Column("recorded_at", DateTime, nullable=False),
    UniqueConstraint("stream_id", "sequence", name="uix_stream_seq"),
)


snapshots_table = Table(
    "loan_snapshots",
    es_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("stream_id", String(64), nullable=False),
    Column("sequence", Integer, nullable=False),
    Column("state", Text, nullable=False),
    Column("recorded_at", DateTime, nullable=False),
)


_es_mapped = False


def map_event_store() -> None:
    global _es_mapped
    if _es_mapped:
        return
    es_registry.map_imperatively(EventRow, events_table)
    es_registry.map_imperatively(SnapshotRow, snapshots_table)
    _es_mapped = True


def create_event_store_schema(engine: Engine) -> None:
    es_metadata.create_all(engine)


def _default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"can't serialize {type(value).__name__}")


def _serialize_state(state: LoanState) -> str:
    return json.dumps(state.__dict__, default=_default)


def _deserialize_state(blob: str) -> LoanState:
    raw = json.loads(blob)
    for k in ("borrowed_on", "due_on", "returned_on"):
        if raw.get(k):
            raw[k] = date.fromisoformat(raw[k])
    return LoanState(**raw)


SNAPSHOT_EVERY = 5


class EventStore:
    def __init__(self, session: Session) -> None:
        self.session = session

    def load(self, stream_id: str) -> tuple[LoanState, int]:
        """Return (state, current_sequence). Replays from the latest snapshot if any."""
        snap = (
            self.session.query(SnapshotRow)
            .filter_by(stream_id=stream_id)
            .order_by(SnapshotRow.sequence.desc())
            .first()
        )
        state = _deserialize_state(snap.state) if snap is not None else LoanState()
        from_seq = snap.sequence if snap is not None else 0

        rows = (
            self.session.query(EventRow)
            .filter(EventRow.stream_id == stream_id, EventRow.sequence > from_seq)
            .order_by(EventRow.sequence.asc())
            .all()
        )
        seq = from_seq
        for row in rows:
            event = upcast(row.event_type, json.loads(row.payload))
            state = apply(state, event)
            seq = row.sequence
        return state, seq

    def append(self, stream_id: str, expected_version: int, events: list[LoanEvent]) -> int:
        """Append events with optimistic concurrency on stream version."""
        if not events:
            return expected_version
        seq = expected_version
        for ev in events:
            seq += 1
            self.session.add(
                EventRow(
                    stream_id=stream_id,
                    sequence=seq,
                    event_type=type(ev).__name__,
                    payload=json.dumps(asdict(ev), default=_default),
                    recorded_at=datetime.utcnow(),
                )
            )
        return seq

    def snapshot(self, stream_id: str, sequence: int, state: LoanState) -> None:
        if sequence % SNAPSHOT_EVERY == 0:
            self.session.add(
                SnapshotRow(
                    stream_id=stream_id,
                    sequence=sequence,
                    state=_serialize_state(state),
                    recorded_at=datetime.utcnow(),
                )
            )
