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
