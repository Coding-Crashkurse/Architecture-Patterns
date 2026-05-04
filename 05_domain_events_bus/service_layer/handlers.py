"""Event handlers. Side effects only — no domain logic in here."""

from __future__ import annotations

from collections.abc import Iterable

from domain.events import BookBorrowed, BookReturned, BookRunningLow


# In-memory log of side-effects so the client can verify them.
notifications: list[dict] = []


def notify_borrow(event: BookBorrowed) -> None:
    notifications.append(
        {
            "type": "BookBorrowed",
            "member_id": event.member_id,
            "isbn": event.isbn,
            "due_on": event.due_on.isoformat(),
        }
    )


def notify_return(event: BookReturned) -> None:
    notifications.append(
        {
            "type": "BookReturned",
            "member_id": event.member_id,
            "isbn": event.isbn,
            "returned_on": event.returned_on.isoformat(),
        }
    )


def alert_running_low(event: BookRunningLow) -> None:
    notifications.append({"type": "BookRunningLow", "isbn": event.isbn, "title": event.title})


def register_all(register_fn) -> None:
    register_fn(BookBorrowed, notify_borrow)
    register_fn(BookReturned, notify_return)
    register_fn(BookRunningLow, alert_running_low)


def get_notifications() -> Iterable[dict]:
    return list(notifications)
