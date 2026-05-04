"""Phase 9: Saga / Process Manager for inter-branch book transfers.

A Transfer is a long-running workflow with state stored in the DB. The saga
handlers move it through requested -> shipped -> received (or compensated on failure).

The bus chain looks like:
    POST /transfer -> RequestTransfer (cmd) -> TransferRequested (evt)
        -> ShipBook (cmd) -> BookShipped (evt)
        -> ReceiveBook (cmd) -> BookReceived + TransferCompleted (evt)

Failure path (simulate_receive_failure=true):
        ReceiveBook (cmd) -> TransferFailed (evt) + CompensateShipment (cmd)
        -> shipped copy returns to source branch
"""

from __future__ import annotations

import os

import fakeredis
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adapters.consumer import Consumer
from adapters.inbox import create_inbox_schema, map_inbox
from adapters.orm import create_schema, map_domain
from adapters.outbox import create_outbox_schema, map_outbox
from adapters.relay import Relay
from domain.commands import (
    AddBook,
    AddMember,
    BorrowBook,
    RequestTransfer,
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
from service_layer import handlers, views
from service_layer.messagebus import Bus
from service_layer.unit_of_work import make_uow_factory


PORT = 8009
DB_FILE = os.environ.get("LIBRARY_DB", "library_phase9.db")
DB_URL = f"sqlite:///{DB_FILE}"


map_domain()
map_outbox()
map_inbox()
engine = create_engine(DB_URL, future=True)
create_schema(engine)
create_outbox_schema(engine)
create_inbox_schema(engine)
SessionFactory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
uow_factory = make_uow_factory(engine)


fake_server = fakeredis.FakeServer()
redis_client = fakeredis.FakeStrictRedis(server=fake_server)


external_notifications: list[dict] = []


def on_external_event(event_type: str, payload: dict) -> None:
    external_notifications.append({"type": event_type, "payload": payload})


relay = Relay(SessionFactory, redis_client)
consumer = Consumer(SessionFactory, redis_client, on_event=on_external_event)


def make_bus() -> Bus:
    cmd_handlers, evt_handlers = handlers.build_handler_maps()
    return Bus(uow_factory=uow_factory, command_handlers=cmd_handlers, event_handlers=evt_handlers)


@asynccontextmanager
async def lifespan(app: FastAPI):
    relay.start()
    consumer.start()
    try:
        yield
    finally:
        relay.stop()
        consumer.stop()


app = FastAPI(title="Library -- Phase 9: Saga / Process Manager", lifespan=lifespan)


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
    return {
        "in_process": list(handlers.get_notifications()),
        "external_via_redis": list(external_notifications),
    }


@app.get("/views/available_books")
def view_available() -> dict:
    return {"books": views.available_books(engine)}


@app.get("/views/overdue_loans")
def view_overdue(today: str) -> dict:
    return {"loans": views.overdue_loans(engine, today=today)}


@app.get("/views/member_history/{member_id}")
def view_history(member_id: str) -> dict:
    def fmt(value) -> str | None:
        if value is None:
            return None
        return value.isoformat() if hasattr(value, "isoformat") else str(value)

    return {
        "history": [
            {
                "isbn": row["isbn"],
                "title": row["title"],
                "borrowed_on": fmt(row["borrowed_on"]),
                "due_on": fmt(row["due_on"]),
                "returned_on": fmt(row["returned_on"]),
            }
            for row in views.member_history(engine, member_id=member_id)
        ]
    }


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


@app.post("/books", status_code=201)
def post_book(payload: BookIn) -> dict[str, str]:
    try:
        make_bus().handle(
            AddBook(isbn=payload.isbn, title=payload.title, total_copies=payload.total_copies)
        )
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


class BranchStockIn(BaseModel):
    isbn: str
    branch: str
    copies: int


@app.post("/admin/seed_branch_stock", status_code=201)
def seed_stock(payload: BranchStockIn) -> dict:
    """Demo helper: directly seed per-branch stock (no domain rules; this is admin)."""
    from domain.model import BranchStock

    with uow_factory() as uow:
        from adapters.repository import BranchStockRepository

        existing = BranchStockRepository(uow.session).get(ISBN(payload.isbn), payload.branch)
        if existing is None:
            uow.session.add(
                BranchStock(isbn=ISBN(payload.isbn), branch=payload.branch, copies=payload.copies)
            )
        else:
            existing.copies = payload.copies
        uow.commit()
    return {"isbn": payload.isbn, "branch": payload.branch, "copies": payload.copies}


@app.get("/branch_stock/{branch}/{isbn}")
def get_branch_stock(branch: str, isbn: str) -> dict:
    from adapters.repository import BranchStockRepository

    with uow_factory() as uow:
        stock = BranchStockRepository(uow.session).get(ISBN(isbn), branch)
        copies = stock.copies if stock is not None else 0
    return {"branch": branch, "isbn": isbn, "copies": copies}


class TransferIn(BaseModel):
    transfer_id: str
    isbn: str
    from_branch: str
    to_branch: str
    simulate_receive_failure: bool = False


@app.post("/transfer")
def post_transfer(payload: TransferIn) -> dict:
    cmd = RequestTransfer(
        transfer_id=payload.transfer_id,
        isbn=payload.isbn,
        from_branch=payload.from_branch,
        to_branch=payload.to_branch,
        simulate_receive_failure=payload.simulate_receive_failure,
    )
    try:
        make_bus().handle(cmd)
    except DomainError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _transfer_state(payload.transfer_id)


@app.get("/transfer/{transfer_id}")
def get_transfer(transfer_id: str) -> dict:
    return _transfer_state(transfer_id)


def _transfer_state(transfer_id: str) -> dict:
    from adapters.repository import TransferRepository

    with uow_factory() as uow:
        t = TransferRepository(uow.session).get(transfer_id)
        if t is None:
            raise HTTPException(404, "transfer not found")
        return {
            "transfer_id": t.transfer_id,
            "isbn": t.isbn.value,
            "from_branch": t.from_branch,
            "to_branch": t.to_branch,
            "state": t.state,
            "failure_reason": t.failure_reason,
        }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
