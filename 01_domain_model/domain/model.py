"""Phase 1: Pure domain model. No persistence, no framework — just business rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta


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


@dataclass(frozen=True)
class ISBN:
    """Value Object: an ISBN is just a string, but it has identity-by-value."""

    value: str

    def __post_init__(self) -> None:
        if not self.value or len(self.value) < 10:
            raise ValueError(f"invalid ISBN: {self.value!r}")


@dataclass
class Book:
    """Entity: identified by ISBN. Holds copy availability."""

    isbn: ISBN
    title: str
    total_copies: int
    available_copies: int

    def borrow_one(self) -> None:
        if self.available_copies <= 0:
            raise OutOfStock(f"no copies left for {self.title!r}")
        self.available_copies -= 1

    def return_one(self) -> None:
        if self.available_copies >= self.total_copies:
            raise DomainError("cannot return: all copies already on shelf")
        self.available_copies += 1


@dataclass
class Loan:
    """Entity: a single borrowing event. Has its own lifecycle."""

    member_id: str
    isbn: ISBN
    borrowed_on: date
    due_on: date
    returned_on: date | None = None

    @property
    def is_active(self) -> bool:
        return self.returned_on is None

    @property
    def is_overdue(self) -> bool:
        return self.is_active and date.today() > self.due_on

    def mark_returned(self, on: date) -> None:
        if not self.is_active:
            raise NotBorrowed("loan already closed")
        self.returned_on = on


@dataclass
class Member:
    """Entity: a library member."""

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
        return loan

    def return_book(self, book: Book, today: date) -> Loan:
        for loan in self.active_loans:
            if loan.isbn == book.isbn:
                loan.mark_returned(today)
                book.return_one()
                return loan
        raise NotBorrowed(f"member {self.member_id} has no active loan for {book.isbn.value}")
