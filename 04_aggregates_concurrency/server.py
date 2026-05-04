"""Phase 4: Book is now an aggregate root with a version field.

When two transactions try to update the same Book concurrently, the UoW raises
ConcurrencyError, which the server maps to 409 with explicit body.
"""

from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine

from datetime import date

from adapters.orm import create_schema, map_domain
from domain.model import ISBN, ConcurrencyError, DomainError
from service_layer import services
from service_layer.unit_of_work import make_uow_factory


PORT = 8004
DB_FILE = os.environ.get("LIBRARY_DB", "library_phase4.db")
DB_URL = f"sqlite:///{DB_FILE}"


map_domain()
engine = create_engine(DB_URL, future=True)
create_schema(engine)
uow_factory = make_uow_factory(engine)


app = FastAPI(title="Library — Phase 3: Service Layer + UoW")


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


@app.post("/books", status_code=201)
def add_book(payload: BookIn) -> dict[str, str]:
    try:
        services.add_book(payload.isbn, payload.title, payload.total_copies, uow_factory())
    except DomainError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"isbn": payload.isbn}


@app.get("/books/{isbn}")
def get_book(isbn: str) -> dict:
    try:
        return services.get_book(isbn, uow_factory())
    except services.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/members", status_code=201)
def add_member(payload: MemberIn) -> dict[str, str]:
    try:
        services.add_member(payload.member_id, payload.name, uow_factory())
    except services.AlreadyExists as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"member_id": payload.member_id}


@app.post("/borrow")
def borrow(payload: BorrowIn) -> dict[str, str]:
    try:
        return services.borrow_book(payload.member_id, payload.isbn, uow_factory())
    except services.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except ConcurrencyError as exc:
        raise HTTPException(409, f"concurrency conflict: {exc}") from exc
    except DomainError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/return")
def return_book(payload: BorrowIn) -> dict[str, str]:
    try:
        return services.return_book(payload.member_id, payload.isbn, uow_factory())
    except services.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except ConcurrencyError as exc:
        raise HTTPException(409, f"concurrency conflict: {exc}") from exc
    except DomainError as exc:
        raise HTTPException(409, str(exc)) from exc


class RaceIn(BaseModel):
    member_a: str
    member_b: str
    isbn: str


@app.post("/admin/race_borrow")
def race_borrow(payload: RaceIn) -> dict:
    """Fire two borrow attempts in parallel, holding a barrier so they race.

    With Book carrying a version, exactly one will commit cleanly; the other
    sees a stale version and gets 409 ConcurrencyError. Useful as a deterministic
    demo of optimistic concurrency.
    """
    barrier = threading.Barrier(2)

    def attempt(member_id: str) -> dict:
        uow = uow_factory()
        with uow:
            member = uow.members.get(member_id)
            book = uow.books.get(ISBN(payload.isbn))
            if member is None or book is None:
                return {"member_id": member_id, "status": "not_found"}
            barrier.wait(timeout=2.0)
            try:
                loan = member.borrow(book, today=date.today())
                if member_id == payload.member_b:
                    time.sleep(0.05)  # stagger so the two commits actually race
                uow.commit()
                return {"member_id": member_id, "status": "ok", "due_on": loan.due_on.isoformat()}
            except ConcurrencyError as exc:
                return {"member_id": member_id, "status": "concurrency_conflict", "detail": str(exc)}
            except DomainError as exc:
                return {"member_id": member_id, "status": "domain_error", "detail": str(exc)}

    with ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(attempt, payload.member_a)
        f2 = ex.submit(attempt, payload.member_b)
        results = [f1.result(), f2.result()]

    return {"results": results}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
