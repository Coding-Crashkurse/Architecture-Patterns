"""Phase 6: same domain plus a Reservation entity. Reservations are queued
when a book is unavailable and fulfilled when it comes back."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from domain.events import (
    BookBorrowed,
    BookReserved,
    BookReturned,
    BookRunningLow,
    Event,
)


MAX_ACTIVE_LOANS_PER_MEMBER = 3
DEFAULT_LOAN_DAYS = 14


class DomainError(Exception):
    pass


class OutOfStock(DomainError):
    pass


class LoanLimitExceeded(DomainError):
    pass


class NotBorrowed(DomainError):
    pass


class ConcurrencyError(DomainError):
    pass


class CannotReserve(DomainError):
    pass


class NotFound(DomainError):
    pass


class AlreadyExists(DomainError):
    pass


@dataclass(frozen=True)
class ISBN:
    value: str

    def __post_init__(self) -> None:
        if not self.value or len(self.value) < 10:
            raise ValueError(f"invalid ISBN: {self.value!r}")


@dataclass
class Book:
    """Aggregate root. Owns its consistency boundary (copies counter) AND its version
    so the ORM/UoW can detect concurrent writes from two transactions."""

    isbn: ISBN
    title: str
    total_copies: int
    available_copies: int
    version: int = 0
    events: list[Event] = field(default_factory=list, compare=False, repr=False)

    def borrow_one(self) -> None:
        if self.available_copies <= 0:
            raise OutOfStock(f"no copies left for {self.title!r}")
        self.available_copies -= 1
        self.version += 1
        if self.available_copies == 0:
            self.events.append(BookRunningLow(isbn=self.isbn.value, title=self.title))

    def return_one(self) -> None:
        if self.available_copies >= self.total_copies:
            raise DomainError("cannot return: all copies already on shelf")
        self.available_copies += 1
        self.version += 1


@dataclass
class Loan:
    member_id: str
    isbn: ISBN
    borrowed_on: date
    due_on: date
    returned_on: date | None = None
    id: int | None = None

    @property
    def is_active(self) -> bool:
        return self.returned_on is None

    def mark_returned(self, on: date) -> None:
        if not self.is_active:
            raise NotBorrowed("loan already closed")
        self.returned_on = on


@dataclass
class Member:
    member_id: str
    name: str
    loans: list[Loan] = field(default_factory=list)

    @property
    def active_loans(self) -> list[Loan]:
        return [loan for loan in self.loans if loan.is_active]

    def borrow(self, book: Book, today: date) -> Loan:
        if len(self.active_loans) >= MAX_ACTIVE_LOANS_PER_MEMBER:
            raise LoanLimitExceeded(
                f"member {self.member_id} already has {MAX_ACTIVE_LOANS_PER_MEMBER} active loans"
            )
        book.borrow_one()
        loan = Loan(
            member_id=self.member_id,
            isbn=book.isbn,
            borrowed_on=today,
            due_on=today + timedelta(days=DEFAULT_LOAN_DAYS),
        )
        self.loans.append(loan)
        book.events.append(
            BookBorrowed(member_id=self.member_id, isbn=book.isbn.value, due_on=loan.due_on)
        )
        return loan

    def return_book(self, book: Book, today: date) -> Loan:
        for loan in self.active_loans:
            if loan.isbn == book.isbn:
                loan.mark_returned(today)
                book.return_one()
                book.events.append(
                    BookReturned(member_id=self.member_id, isbn=book.isbn.value, returned_on=today)
                )
                return loan
        raise NotBorrowed(f"member {self.member_id} has no active loan for {book.isbn.value}")


@dataclass
class Reservation:
    """A member queues for a currently-unavailable book. FIFO; one fulfill turns it into a Loan."""

    member_id: str
    isbn: ISBN
    placed_on: date
    fulfilled_on: date | None = None
    id: int | None = None

    @property
    def is_open(self) -> bool:
        return self.fulfilled_on is None

    def fulfill(self, on: date) -> None:
        if not self.is_open:
            raise CannotReserve("reservation already fulfilled")
        self.fulfilled_on = on


# --------- Phase 9: per-branch stock and inter-branch transfers ---------


class TransferError(DomainError):
    pass


@dataclass
class BranchStock:
    """Per-branch inventory. Independent of the global Book aggregate."""

    isbn: ISBN
    branch: str
    copies: int = 0
    id: int | None = None

    def ship_one(self) -> None:
        if self.copies <= 0:
            raise TransferError(f"branch {self.branch} has no copies of {self.isbn.value} to ship")
        self.copies -= 1

    def receive_one(self) -> None:
        self.copies += 1


@dataclass
class Transfer:
    """Long-running workflow state; the saga moves it through the states."""

    transfer_id: str
    isbn: ISBN
    from_branch: str
    to_branch: str
    state: str = "requested"  # requested -> shipped -> received | failed | compensated
    failure_reason: str | None = None
    simulate_receive_failure: bool = False
    id: int | None = None
