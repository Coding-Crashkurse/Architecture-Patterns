"""Use cases. They take a UoW + plain values; no FastAPI, no SQLAlchemy types."""

from __future__ import annotations

from datetime import date

from domain.model import (
    ISBN,
    Book,
    DomainError,
    Member,
)
from service_layer.unit_of_work import AbstractUnitOfWork


class NotFound(DomainError):
    pass


class AlreadyExists(DomainError):
    pass


def add_book(isbn: str, title: str, total_copies: int, uow: AbstractUnitOfWork) -> None:
    with uow:
        book = Book(
            isbn=ISBN(isbn),
            title=title,
            total_copies=total_copies,
            available_copies=total_copies,
        )
        uow.books.add(book)
        uow.commit()


def add_member(member_id: str, name: str, uow: AbstractUnitOfWork) -> None:
    with uow:
        if uow.members.get(member_id) is not None:
            raise AlreadyExists(f"member {member_id} already exists")
        uow.members.add(Member(member_id=member_id, name=name))
        uow.commit()


def borrow_book(member_id: str, isbn: str, uow: AbstractUnitOfWork, today: date | None = None) -> dict:
    today = today or date.today()
    with uow:
        member = uow.members.get(member_id)
        book = uow.books.get(ISBN(isbn))
        if member is None:
            raise NotFound(f"member {member_id} not found")
        if book is None:
            raise NotFound(f"book {isbn} not found")
        loan = member.borrow(book, today=today)
        uow.commit()
        return {
            "member_id": loan.member_id,
            "isbn": loan.isbn.value,
            "due_on": loan.due_on.isoformat(),
        }


def return_book(member_id: str, isbn: str, uow: AbstractUnitOfWork, today: date | None = None) -> dict:
    today = today or date.today()
    with uow:
        member = uow.members.get(member_id)
        book = uow.books.get(ISBN(isbn))
        if member is None:
            raise NotFound(f"member {member_id} not found")
        if book is None:
            raise NotFound(f"book {isbn} not found")
        loan = member.return_book(book, today=today)
        uow.commit()
        return {
            "member_id": loan.member_id,
            "isbn": loan.isbn.value,
            "returned_on": loan.returned_on.isoformat() if loan.returned_on else "",
        }


def get_book(isbn: str, uow: AbstractUnitOfWork) -> dict:
    with uow:
        book = uow.books.get(ISBN(isbn))
        if book is None:
            raise NotFound(f"book {isbn} not found")
        return {
            "isbn": book.isbn.value,
            "title": book.title,
            "total_copies": book.total_copies,
            "available_copies": book.available_copies,
            "version": book.version,
        }
