"""Commands: imperative requests for state change. Exactly one handler. May fail."""

from __future__ import annotations

from dataclasses import dataclass


class Command:
    pass


@dataclass(frozen=True)
class AddBook(Command):
    isbn: str
    title: str
    total_copies: int


@dataclass(frozen=True)
class AddMember(Command):
    member_id: str
    name: str


@dataclass(frozen=True)
class BorrowBook(Command):
    member_id: str
    isbn: str


@dataclass(frozen=True)
class ReturnBook(Command):
    member_id: str
    isbn: str


@dataclass(frozen=True)
class ReserveBook(Command):
    member_id: str
    isbn: str


@dataclass(frozen=True)
class FulfillReservation(Command):
    member_id: str
    isbn: str


@dataclass(frozen=True)
class RequestTransfer(Command):
    transfer_id: str
    isbn: str
    from_branch: str
    to_branch: str
    simulate_receive_failure: bool = False


@dataclass(frozen=True)
class ShipBook(Command):
    transfer_id: str
    isbn: str
    from_branch: str
    to_branch: str


@dataclass(frozen=True)
class ReceiveBook(Command):
    transfer_id: str
    isbn: str
    to_branch: str


@dataclass(frozen=True)
class CompensateShipment(Command):
    """Used when receiving fails: put the shipped book back on the source branch."""

    transfer_id: str
    isbn: str
    from_branch: str
