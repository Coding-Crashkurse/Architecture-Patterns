"""Read side. Direct SQL, returns dicts. Bypasses the domain model entirely.

This is the "Q" half of CQRS in its lightest form: queries don't go through aggregates.
Avoiding the round-trip through Repository/UoW is the whole point — read paths are
shaped for the consumer, not for invariants.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def available_books(engine: Engine) -> list[dict]:
    sql = text(
        """
        SELECT isbn, title, available_copies, total_copies
        FROM books
        WHERE available_copies > 0
        ORDER BY title
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql).mappings().all()
    return [dict(r) for r in rows]


def overdue_loans(engine: Engine, today: str) -> list[dict]:
    sql = text(
        """
        SELECT l.id, l.member_id, m.name AS member_name, l.isbn, b.title, l.due_on
        FROM loans l
        JOIN members m ON m.member_id = l.member_id
        JOIN books   b ON b.isbn       = l.isbn
        WHERE l.returned_on IS NULL AND l.due_on < :today
        ORDER BY l.due_on
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"today": today}).mappings().all()
    return [dict(r) for r in rows]


def member_history(engine: Engine, member_id: str) -> list[dict]:
    sql = text(
        """
        SELECT l.isbn, b.title, l.borrowed_on, l.due_on, l.returned_on
        FROM loans l
        JOIN books b ON b.isbn = l.isbn
        WHERE l.member_id = :mid
        ORDER BY l.borrowed_on DESC
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"mid": member_id}).mappings().all()
    return [dict(r) for r in rows]
