"""Service layer for the event-sourced Loan aggregate.

Each use case follows the same shape:
    1. Load state by replaying events (with snapshot)
    2. Run pure decision function -> new events
    3. Append events with optimistic concurrency on stream version
    4. Persist a snapshot if sequence crosses the threshold
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import sessionmaker

from adapters.event_store import EventStore
from domain import loan_es


class StreamConflict(Exception):
    pass


def _open(session_factory: sessionmaker):
    return session_factory()


def borrow_loan(
    session_factory: sessionmaker,
    *,
    loan_id: str,
    member_id: str,
    isbn: str,
    today: date | None = None,
) -> dict:
    today = today or date.today()
    with _open(session_factory) as session:
        store = EventStore(session)
        state, version = store.load(loan_id)
        events = loan_es.borrow(state, loan_id=loan_id, member_id=member_id, isbn=isbn, today=today)
        new_seq = store.append(loan_id, expected_version=version, events=events)
        for ev in events:
            state = loan_es.apply(state, ev)
        store.snapshot(loan_id, new_seq, state)
        try:
            session.commit()
        except Exception as exc:
            session.rollback()
            raise StreamConflict("conflict appending events") from exc
        return _state_to_dict(state, new_seq)


def renew_loan(session_factory: sessionmaker, *, loan_id: str, today: date | None = None) -> dict:
    today = today or date.today()
    with _open(session_factory) as session:
        store = EventStore(session)
        state, version = store.load(loan_id)
        events = loan_es.renew(state, today=today)
        new_seq = store.append(loan_id, expected_version=version, events=events)
        for ev in events:
            state = loan_es.apply(state, ev)
        store.snapshot(loan_id, new_seq, state)
        session.commit()
        return _state_to_dict(state, new_seq)


def return_loan(session_factory: sessionmaker, *, loan_id: str, today: date | None = None) -> dict:
    today = today or date.today()
    with _open(session_factory) as session:
        store = EventStore(session)
        state, version = store.load(loan_id)
        events = loan_es.return_loan(state, today=today)
        new_seq = store.append(loan_id, expected_version=version, events=events)
        for ev in events:
            state = loan_es.apply(state, ev)
        store.snapshot(loan_id, new_seq, state)
        session.commit()
        return _state_to_dict(state, new_seq)


def get_loan(session_factory: sessionmaker, *, loan_id: str) -> dict:
    with _open(session_factory) as session:
        state, version = EventStore(session).load(loan_id)
    return _state_to_dict(state, version)


def get_history(session_factory: sessionmaker, *, loan_id: str) -> list[dict]:
    from adapters.event_store import EventRow

    with _open(session_factory) as session:
        rows = (
            session.query(EventRow)
            .filter(EventRow.stream_id == loan_id)
            .order_by(EventRow.sequence.asc())
            .all()
        )
        return [
            {
                "sequence": row.sequence,
                "event_type": row.event_type,
                "payload": row.payload,
                "recorded_at": row.recorded_at.isoformat(),
            }
            for row in rows
        ]


def _state_to_dict(state, version: int) -> dict:
    return {
        "loan_id": state.loan_id,
        "member_id": state.member_id,
        "isbn": state.isbn,
        "borrowed_on": state.borrowed_on.isoformat() if state.borrowed_on else None,
        "due_on": state.due_on.isoformat() if state.due_on else None,
        "returned_on": state.returned_on.isoformat() if state.returned_on else None,
        "renewed_count": state.renewed_count,
        "late_fee_cents": state.late_fee_cents,
        "version": version,
    }
