"""Phase 2 server: domain model now lives behind a Repository, persisted to SQLite."""

from __future__ import annotations

import os
from datetime import date

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from adapters.orm import create_schema, map_domain
from adapters.repository import (
    SqlAlchemyBookRepository,
    SqlAlchemyMemberRepository,
)
from domain.model import (
    ISBN,
    Book,
    DomainError,
    Member,
)


PORT = 8002
DB_FILE = os.environ.get("LIBRARY_DB", "library_phase2.db")
DB_URL = f"sqlite:///{DB_FILE}"


map_domain()
engine = create_engine(DB_URL, future=True)
create_schema(engine)
SessionFactory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


app = FastAPI(title="Library — Phase 2: Repository")


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


def _book_out(book: Book) -> BookOut:
    return BookOut(
        isbn=book.isbn.value,
        title=book.title,
        total_copies=book.total_copies,
        available_copies=book.available_copies,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/books", response_model=BookOut, status_code=201)
def add_book(payload: BookIn) -> BookOut:
    with SessionFactory() as session:
        repo = SqlAlchemyBookRepository(session)
        book = Book(
            isbn=ISBN(payload.isbn),
            title=payload.title,
            total_copies=payload.total_copies,
            available_copies=payload.total_copies,
        )
        repo.add(book)
        session.commit()
        return _book_out(book)


@app.get("/books/{isbn}", response_model=BookOut)
def get_book(isbn: str) -> BookOut:
    with SessionFactory() as session:
        repo = SqlAlchemyBookRepository(session)
        book = repo.get(ISBN(isbn))
        if book is None:
            raise HTTPException(404, "book not found")
        return _book_out(book)


@app.post("/members", status_code=201)
def add_member(payload: MemberIn) -> dict[str, str]:
    with SessionFactory() as session:
        repo = SqlAlchemyMemberRepository(session)
        if repo.get(payload.member_id) is not None:
            raise HTTPException(409, "member already exists")
        repo.add(Member(member_id=payload.member_id, name=payload.name))
        session.commit()
        return {"member_id": payload.member_id}


@app.post("/borrow")
def borrow(payload: BorrowIn) -> dict[str, str]:
    with SessionFactory() as session:
        return _borrow_or_return(session, payload, action="borrow")


@app.post("/return")
def return_book(payload: BorrowIn) -> dict[str, str]:
    with SessionFactory() as session:
        return _borrow_or_return(session, payload, action="return")


def _borrow_or_return(session: Session, payload: BorrowIn, action: str) -> dict[str, str]:
    book_repo = SqlAlchemyBookRepository(session)
    member_repo = SqlAlchemyMemberRepository(session)
    book = book_repo.get(ISBN(payload.isbn))
    member = member_repo.get(payload.member_id)
    if book is None:
        raise HTTPException(404, "book not found")
    if member is None:
        raise HTTPException(404, "member not found")
    try:
        if action == "borrow":
            loan = member.borrow(book, today=date.today())
            session.commit()
            return {
                "member_id": loan.member_id,
                "isbn": loan.isbn.value,
                "due_on": loan.due_on.isoformat(),
            }
        loan = member.return_book(book, today=date.today())
        session.commit()
        return {
            "member_id": loan.member_id,
            "isbn": loan.isbn.value,
            "returned_on": loan.returned_on.isoformat() if loan.returned_on else "",
        }
    except DomainError as exc:
        raise HTTPException(409, str(exc)) from exc


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
