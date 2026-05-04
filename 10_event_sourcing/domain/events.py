"""Domain events. Pure data — what happened, never how to react to it."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


class Event:
    """Marker base class so the message bus can dispatch by isinstance."""


@dataclass(frozen=True)
class BookBorrowed(Event):
    member_id: str
    isbn: str
    due_on: date


@dataclass(frozen=True)
class BookReturned(Event):
    member_id: str
    isbn: str
    returned_on: date


@dataclass(frozen=True)
class BookRunningLow(Event):
    """Emitted when available_copies drops to 0. A handler could re-order stock."""

    isbn: str
    title: str


@dataclass(frozen=True)
class BookReserved(Event):
    member_id: str
    isbn: str


@dataclass(frozen=True)
class ReservationFulfilled(Event):
    member_id: str
    isbn: str


@dataclass(frozen=True)
class TransferRequested(Event):
    transfer_id: str
    isbn: str
    from_branch: str
    to_branch: str


@dataclass(frozen=True)
class BookShipped(Event):
    transfer_id: str
    isbn: str
    from_branch: str
    to_branch: str


@dataclass(frozen=True)
class BookReceived(Event):
    transfer_id: str
    isbn: str
    to_branch: str


@dataclass(frozen=True)
class TransferCompleted(Event):
    transfer_id: str
    isbn: str
    from_branch: str
    to_branch: str


@dataclass(frozen=True)
class TransferFailed(Event):
    transfer_id: str
    isbn: str
    reason: str
