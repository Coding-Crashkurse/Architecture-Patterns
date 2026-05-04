"""Shared branch service: each branch (north/south/west) imports and runs this.

Each instance is its own FastAPI process, with its own Postgres DB. Inter-branch
calls are real HTTP. This is the same library domain, deliberately stripped down
to make the inter-service shape obvious.
"""

from __future__ import annotations

import os
import time

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    select,
    text,
)
from sqlalchemy.engine import Engine


metadata = MetaData()

books = Table(
    "books",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("isbn", String(20), nullable=False),
    Column("title", String(200), nullable=False),
    Column("copies", Integer, nullable=False, default=0),
    UniqueConstraint("isbn", name="uix_books_isbn"),
)


def wait_for_db(engine: Engine, attempts: int = 30) -> None:
    for _ in range(attempts):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except Exception:
            time.sleep(1)
    raise RuntimeError("database did not become reachable in time")


def make_app(branch: str, port: int, db_url: str, peers: dict[str, str]) -> FastAPI:
    """`peers` is {branch_name: base_url} of the other branches."""

    engine = create_engine(db_url, future=True)
    wait_for_db(engine)
    metadata.create_all(engine)

    app = FastAPI(title=f"Library Branch -- {branch}")

    class BookIn(BaseModel):
        isbn: str
        title: str
        copies: int = 0

    class StockOp(BaseModel):
        isbn: str

    class TransferOut(BaseModel):
        isbn: str
        to_branch: str  # one of peers.keys()

    class TransferIn(BaseModel):
        isbn: str
        title: str

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "branch": branch}

    @app.post("/books", status_code=201)
    def add_book(payload: BookIn) -> dict:
        with engine.begin() as conn:
            existing = conn.execute(
                select(books).where(books.c.isbn == payload.isbn)
            ).first()
            if existing is None:
                conn.execute(
                    books.insert().values(
                        isbn=payload.isbn, title=payload.title, copies=payload.copies
                    )
                )
            else:
                conn.execute(
                    books.update().where(books.c.isbn == payload.isbn).values(
                        title=payload.title, copies=payload.copies
                    )
                )
        return {"branch": branch, "isbn": payload.isbn, "copies": payload.copies}

    @app.get("/stock/{isbn}")
    def stock(isbn: str) -> dict:
        with engine.connect() as conn:
            row = conn.execute(select(books).where(books.c.isbn == isbn)).mappings().first()
        if row is None:
            return {"branch": branch, "isbn": isbn, "copies": 0, "title": None}
        return {"branch": branch, "isbn": isbn, "copies": row["copies"], "title": row["title"]}

    @app.post("/borrow")
    def borrow(payload: StockOp) -> dict:
        with engine.begin() as conn:
            row = conn.execute(select(books).where(books.c.isbn == payload.isbn)).mappings().first()
            if row is None or row["copies"] <= 0:
                raise HTTPException(409, "out of stock")
            conn.execute(
                books.update()
                .where(books.c.isbn == payload.isbn)
                .values(copies=row["copies"] - 1)
            )
        return {"branch": branch, "isbn": payload.isbn, "copies_remaining": row["copies"] - 1}

    @app.post("/return")
    def return_book(payload: StockOp) -> dict:
        with engine.begin() as conn:
            row = conn.execute(select(books).where(books.c.isbn == payload.isbn)).mappings().first()
            if row is None:
                raise HTTPException(404, "book not registered at this branch")
            conn.execute(
                books.update()
                .where(books.c.isbn == payload.isbn)
                .values(copies=row["copies"] + 1)
            )
        return {"branch": branch, "isbn": payload.isbn, "copies_remaining": row["copies"] + 1}

    @app.post("/transfer/receive", status_code=201)
    def transfer_receive(payload: TransferIn) -> dict:
        """Called by another branch when shipping us a copy."""
        with engine.begin() as conn:
            row = conn.execute(select(books).where(books.c.isbn == payload.isbn)).mappings().first()
            if row is None:
                conn.execute(
                    books.insert().values(isbn=payload.isbn, title=payload.title, copies=1)
                )
            else:
                conn.execute(
                    books.update()
                    .where(books.c.isbn == payload.isbn)
                    .values(copies=row["copies"] + 1)
                )
        return {"branch": branch, "isbn": payload.isbn, "received": True}

    @app.post("/transfer/send")
    def transfer_send(payload: TransferOut) -> dict:
        """Decrement locally; ship via HTTP to peer; on failure restore locally (compensation)."""
        target = peers.get(payload.to_branch)
        if target is None:
            raise HTTPException(400, f"unknown branch {payload.to_branch}")

        with engine.begin() as conn:
            row = conn.execute(select(books).where(books.c.isbn == payload.isbn)).mappings().first()
            if row is None or row["copies"] <= 0:
                raise HTTPException(409, "no copies to ship")
            title = row["title"]
            conn.execute(
                books.update()
                .where(books.c.isbn == payload.isbn)
                .values(copies=row["copies"] - 1)
            )

        try:
            r = httpx.post(
                f"{target}/transfer/receive",
                json={"isbn": payload.isbn, "title": title},
                timeout=5.0,
            )
            r.raise_for_status()
        except Exception as exc:
            # Compensation: restore local stock.
            with engine.begin() as conn:
                row = conn.execute(select(books).where(books.c.isbn == payload.isbn)).mappings().first()
                conn.execute(
                    books.update()
                    .where(books.c.isbn == payload.isbn)
                    .values(copies=(row["copies"] if row else 0) + 1)
                )
            raise HTTPException(502, f"shipment failed and was compensated: {exc}") from exc

        return {"branch": branch, "isbn": payload.isbn, "shipped_to": payload.to_branch}

    return app


def run() -> None:
    branch = os.environ["BRANCH"]
    port = int(os.environ.get("PORT", "8000"))
    db_url = os.environ["DB_URL"]
    # PEERS like "south=http://south:8000,west=http://west:8000"
    peers_raw = os.environ.get("PEERS", "")
    peers: dict[str, str] = {}
    for chunk in peers_raw.split(","):
        if not chunk.strip():
            continue
        name, url = chunk.split("=", 1)
        peers[name.strip()] = url.strip()

    app = make_app(branch=branch, port=port, db_url=db_url, peers=peers)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


if __name__ == "__main__":
    run()
