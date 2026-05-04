"""Phase 1 server: thin HTTP layer over the pure domain model.

No repository, no service layer, no DB. State lives in module-level dicts
to make the point that the domain model itself doesn't depend on any of that.
"""

from __future__ import annotations

from datetime import date

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from domain.model import (
    ISBN,
    Book,
    DomainError,
    Member,
)


PORT = 8001

app = FastAPI(title="Library — Phase 1: Domain Model")

books: dict[str, Book] = {}
members: dict[str, Member] = {}


class BookIn(BaseModel):
    isbn: str
    title: str
    total_copies: int


class BookOut(BaseModel):
    isbn: str
    title: str
    total_copies: int
    available_copies: int


class MemberIn(BaseModel):
    member_id: str
    name: str


class BorrowIn(BaseModel):
    member_id: str
    isbn: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/books", response_model=BookOut, status_code=201)
def add_book(payload: BookIn) -> BookOut:
    isbn = ISBN(payload.isbn)
    book = Book(
        isbn=isbn,
        title=payload.title,
        total_copies=payload.total_copies,
        available_copies=payload.total_copies,
    )
    books[isbn.value] = book
    return _book_out(book)


@app.get("/books/{isbn}", response_model=BookOut)
def get_book(isbn: str) -> BookOut:
    book = books.get(isbn)
    if book is None:
        raise HTTPException(404, "book not found")
    return _book_out(book)


@app.post("/members", status_code=201)
def add_member(payload: MemberIn) -> dict[str, str]:
    if payload.member_id in members:
        raise HTTPException(409, "member already exists")
    members[payload.member_id] = Member(member_id=payload.member_id, name=payload.name)
    return {"member_id": payload.member_id}


@app.post("/borrow")
def borrow(payload: BorrowIn) -> dict[str, str]:
    book = books.get(payload.isbn)
    member = members.get(payload.member_id)
    if book is None:
        raise HTTPException(404, "book not found")
    if member is None:
        raise HTTPException(404, "member not found")
    try:
        loan = member.borrow(book, today=date.today())
    except DomainError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {
        "member_id": loan.member_id,
        "isbn": loan.isbn.value,
        "due_on": loan.due_on.isoformat(),
    }


@app.post("/return")
def return_book(payload: BorrowIn) -> dict[str, str]:
    book = books.get(payload.isbn)
    member = members.get(payload.member_id)
    if book is None:
        raise HTTPException(404, "book not found")
    if member is None:
        raise HTTPException(404, "member not found")
    try:
        loan = member.return_book(book, today=date.today())
    except DomainError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {
        "member_id": loan.member_id,
        "isbn": loan.isbn.value,
        "returned_on": loan.returned_on.isoformat() if loan.returned_on else "",
    }


def _book_out(book: Book) -> BookOut:
    return BookOut(
        isbn=book.isbn.value,
        title=book.title,
        total_copies=book.total_copies,
        available_copies=book.available_copies,
    )


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
