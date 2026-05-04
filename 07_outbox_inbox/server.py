"""Phase 7: Outbox + Inbox + Redis Streams.

Outbox:    domain change and event-publish are one DB transaction (no dual-write).
Relay:     a background thread drains the outbox and XADDs to a Redis stream.
Inbox:     consumer dedupes by message_id before applying side-effects.

The "external" notifications log is filled by the consumer thread to make the
asynchronous, at-least-once-delivery path observable.
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


PORT = 8007
DB_FILE = os.environ.get("LIBRARY_DB", "library_phase7.db")
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


app = FastAPI(title="Library -- Phase 7: Outbox + Inbox", lifespan=lifespan)


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


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
