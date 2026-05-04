"""Event-sourced Loan: state = fold(events). Snapshots and upcasting included.

Events are versioned (V1, V2). The upcaster maps older versions to the latest
when loading an existing stream — additive schema evolution without rewriting history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any


# ---- Events (the source of truth) ----


@dataclass(frozen=True)
class LoanEvent:
    pass


@dataclass(frozen=True)
class LoanCreatedV1(LoanEvent):
    loan_id: str
    member_id: str
    isbn: str
    borrowed_on: date
    due_on: date


@dataclass(frozen=True)
class LoanRenewedV1(LoanEvent):
    loan_id: str
    new_due_on: date


@dataclass(frozen=True)
class LoanReturnedV1(LoanEvent):
    loan_id: str
    returned_on: date


@dataclass(frozen=True)
class LoanReturnedV2(LoanEvent):
    """V2 adds late_fee. V1 events are upcast to V2 with late_fee=0."""

    loan_id: str
    returned_on: date
    late_fee_cents: int = 0


# ---- State (built by folding events) ----


@dataclass
class LoanState:
    loan_id: str = ""
    member_id: str = ""
    isbn: str = ""
    borrowed_on: date | None = None
    due_on: date | None = None
    returned_on: date | None = None
    renewed_count: int = 0
    late_fee_cents: int = 0

    @property
    def is_active(self) -> bool:
        return self.borrowed_on is not None and self.returned_on is None


def apply(state: LoanState, event: LoanEvent) -> LoanState:
    """Pure: derive next state from previous state + one event."""
    if isinstance(event, LoanCreatedV1):
        return LoanState(
            loan_id=event.loan_id,
            member_id=event.member_id,
            isbn=event.isbn,
            borrowed_on=event.borrowed_on,
            due_on=event.due_on,
        )
    if isinstance(event, LoanRenewedV1):
        return LoanState(
            **{**state.__dict__, "due_on": event.new_due_on, "renewed_count": state.renewed_count + 1}
        )
    if isinstance(event, LoanReturnedV2):
        return LoanState(
            **{
                **state.__dict__,
                "returned_on": event.returned_on,
                "late_fee_cents": event.late_fee_cents,
            }
        )
    raise ValueError(f"unknown event type {type(event).__name__}")


# ---- Decision functions (pure: state + command -> events) ----


class LoanError(Exception):
    pass


def borrow(state: LoanState, *, loan_id: str, member_id: str, isbn: str, today: date, days: int = 14) -> list[LoanEvent]:
    if state.loan_id:
        raise LoanError(f"loan {state.loan_id} already exists")
    return [
        LoanCreatedV1(
            loan_id=loan_id,
            member_id=member_id,
            isbn=isbn,
            borrowed_on=today,
            due_on=today + timedelta(days=days),
        )
    ]


def renew(state: LoanState, *, today: date, days: int = 14, max_renewals: int = 2) -> list[LoanEvent]:
    if not state.is_active:
        raise LoanError("cannot renew: loan is not active")
    if state.renewed_count >= max_renewals:
        raise LoanError(f"cannot renew more than {max_renewals} times")
    return [LoanRenewedV1(loan_id=state.loan_id, new_due_on=today + timedelta(days=days))]


def return_loan(state: LoanState, *, today: date) -> list[LoanEvent]:
    if not state.is_active:
        raise LoanError("loan already returned or never created")
    late = max(0, (today - state.due_on).days) if state.due_on else 0
    fee_cents = late * 25  # 25 cents per day late
    return [LoanReturnedV2(loan_id=state.loan_id, returned_on=today, late_fee_cents=fee_cents)]


# ---- Upcaster: handle old event versions when reading the stream ----


def upcast(event_type: str, payload: dict[str, Any]) -> LoanEvent:
    """Map a persisted (event_type, payload) pair to the current event class.

    V1 LoanReturned -> V2 LoanReturned with late_fee_cents=0. New code never has to
    know V1 ever existed.
    """
    if event_type == "LoanCreatedV1":
        return LoanCreatedV1(
            loan_id=payload["loan_id"],
            member_id=payload["member_id"],
            isbn=payload["isbn"],
            borrowed_on=date.fromisoformat(payload["borrowed_on"]),
            due_on=date.fromisoformat(payload["due_on"]),
        )
    if event_type == "LoanRenewedV1":
        return LoanRenewedV1(
            loan_id=payload["loan_id"],
            new_due_on=date.fromisoformat(payload["new_due_on"]),
        )
    if event_type == "LoanReturnedV1":
        # Old shape — fill the new field with a default.
        return LoanReturnedV2(
            loan_id=payload["loan_id"],
            returned_on=date.fromisoformat(payload["returned_on"]),
            late_fee_cents=0,
        )
    if event_type == "LoanReturnedV2":
        return LoanReturnedV2(
            loan_id=payload["loan_id"],
            returned_on=date.fromisoformat(payload["returned_on"]),
            late_fee_cents=payload["late_fee_cents"],
        )
    raise ValueError(f"no upcaster registered for {event_type!r}")
