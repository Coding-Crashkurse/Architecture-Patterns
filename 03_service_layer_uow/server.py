"""Phase 3: HTTP layer is now thin. All logic lives in the service layer + UoW."""

from __future__ import annotations

import os

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine

from adapters.orm import create_schema, map_domain
from domain.model import DomainError
from service_layer import services
from service_layer.unit_of_work import make_uow_factory


PORT = 8003
DB_FILE = os.environ.get("LIBRARY_DB", "library_phase3.db")
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
    except DomainError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/return")
def return_book(payload: BorrowIn) -> dict[str, str]:
    try:
        return services.return_book(payload.member_id, payload.isbn, uow_factory())
    except services.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except DomainError as exc:
        raise HTTPException(409, str(exc)) from exc


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
