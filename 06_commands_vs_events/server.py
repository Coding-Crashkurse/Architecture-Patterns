"""Phase 6: Commands and Events — different semantics on the same bus.

Commands are imperative ("do this"), have one handler, and fail loudly.
Events are factual ("this happened"), can have many handlers, and never abort the caller.

Reservation chain:
    POST /return -> ReturnBook (cmd) -> BookReturned (evt) -> FulfillReservation (cmd)
                 -> BookBorrowed (evt) + ReservationFulfilled (evt) -> notifications
"""

from __future__ import annotations

import os

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine

from adapters.orm import create_schema, map_domain
from domain.commands import (
    AddBook,
    AddMember,
    BorrowBook,
    ReserveBook,
    ReturnBook,
)
from domain.model import (
    AlreadyExists,
    CannotReserve,
    ConcurrencyError,
    DomainError,
    ISBN,
    NotFound,
)
from service_layer import handlers
from service_layer.messagebus import Bus
from service_layer.unit_of_work import make_uow_factory


PORT = 8006
DB_FILE = os.environ.get("LIBRARY_DB", "library_phase6.db")
DB_URL = f"sqlite:///{DB_FILE}"


map_domain()
engine = create_engine(DB_URL, future=True)
create_schema(engine)
uow_factory = make_uow_factory(engine)


def make_bus() -> Bus:
    cmd_handlers, evt_handlers = handlers.build_handler_maps()
    return Bus(uow_factory=uow_factory, command_handlers=cmd_handlers, event_handlers=evt_handlers)


app = FastAPI(title="Library — Phase 6: Commands vs. Events")


class BookIn(BaseModel):
    isbn: str
    title: str
    total_copies: int


class MemberIn(BaseModel):
    member_id: str
    name: str


class BorrowIn(BaseModel):
    member_id: str
    isbn: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/notifications")
def list_notifications() -> dict:
    return {"notifications": list(handlers.get_notifications())}


@app.get("/books/{isbn}")
def get_book(isbn: str) -> dict:
    with uow_factory() as uow:
        book = uow.books.get(ISBN(isbn))
        if book is None:
            raise HTTPException(404, "book not found")
        return {
            "isbn": book.isbn.value,
            "title": book.title,
            "total_copies": book.total_copies,
            "available_copies": book.available_copies,
            "version": book.version,
        }


@app.get("/loans/{member_id}")
def get_loans(member_id: str) -> dict:
    with uow_factory() as uow:
        member = uow.members.get(member_id)
        if member is None:
            raise HTTPException(404, "member not found")
        return {
            "member_id": member_id,
            "active_loans": [
                {"isbn": loan.isbn.value, "due_on": loan.due_on.isoformat()}
                for loan in member.active_loans
            ],
        }


@app.post("/books", status_code=201)
def post_book(payload: BookIn) -> dict[str, str]:
    try:
        make_bus().handle(AddBook(isbn=payload.isbn, title=payload.title, total_copies=payload.total_copies))
    except DomainError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"isbn": payload.isbn}


@app.post("/members", status_code=201)
def post_member(payload: MemberIn) -> dict[str, str]:
    try:
        make_bus().handle(AddMember(member_id=payload.member_id, name=payload.name))
    except AlreadyExists as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"member_id": payload.member_id}


@app.post("/borrow")
def borrow(payload: BorrowIn) -> dict:
    try:
        return make_bus().handle(BorrowBook(member_id=payload.member_id, isbn=payload.isbn))  # type: ignore[return-value]
    except NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except ConcurrencyError as exc:
        raise HTTPException(409, f"concurrency conflict: {exc}") from exc
    except DomainError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/return")
def return_book(payload: BorrowIn) -> dict:
    try:
        return make_bus().handle(ReturnBook(member_id=payload.member_id, isbn=payload.isbn))  # type: ignore[return-value]
    except NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except DomainError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/reserve")
def reserve(payload: BorrowIn) -> dict:
    try:
        return make_bus().handle(ReserveBook(member_id=payload.member_id, isbn=payload.isbn))  # type: ignore[return-value]
    except NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except CannotReserve as exc:
        raise HTTPException(409, str(exc)) from exc
    except DomainError as exc:
        raise HTTPException(409, str(exc)) from exc


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
