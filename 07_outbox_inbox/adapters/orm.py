"""SQLAlchemy imperative mapping. The domain model stays a POPO — no ORM bases."""

from __future__ import annotations

from sqlalchemy import (
    Column,
    Date,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import registry, relationship
from sqlalchemy.types import String as SAString, TypeDecorator

from domain.model import Book, ISBN, Loan, Member, Reservation


class ISBNType(TypeDecorator):
    """Round-trip ISBN value object <-> VARCHAR."""

    impl = SAString(20)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if isinstance(value, ISBN):
            return value.value
        return value

    def process_result_value(self, value, dialect):
        return ISBN(value) if value is not None else None


metadata = MetaData()
mapper_registry = registry(metadata=metadata)


books_table = Table(
    "books",
    metadata,
    Column("isbn", ISBNType, primary_key=True),
    Column("title", String(200), nullable=False),
    Column("total_copies", Integer, nullable=False),
    Column("available_copies", Integer, nullable=False),
    Column("version", Integer, nullable=False, default=0),
)


members_table = Table(
    "members",
    metadata,
    Column("member_id", String(50), primary_key=True),
    Column("name", String(100), nullable=False),
)


loans_table = Table(
    "loans",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("member_id", String(50), ForeignKey("members.member_id"), nullable=False),
    Column("isbn", ISBNType, nullable=False),
    Column("borrowed_on", Date, nullable=False),
    Column("due_on", Date, nullable=False),
    Column("returned_on", Date, nullable=True),
)


reservations_table = Table(
    "reservations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("member_id", String(50), ForeignKey("members.member_id"), nullable=False),
    Column("isbn", ISBNType, nullable=False),
    Column("placed_on", Date, nullable=False),
    Column("fulfilled_on", Date, nullable=True),
)


_mapped = False


def map_domain() -> None:
    """Map domain classes to tables. Idempotent — guarded for repeated import."""
    global _mapped
    if _mapped:
        return
    mapper_registry.map_imperatively(
        Book,
        books_table,
        version_id_col=books_table.c.version,
        version_id_generator=False,  # the domain bumps the version itself
    )

    @event.listens_for(Book, "load")
    def _init_events_on_load(target, _ctx) -> None:
        # SQLAlchemy bypasses __init__ on load; reset the events list explicitly.
        target.events = []

    mapper_registry.map_imperatively(Loan, loans_table)
    mapper_registry.map_imperatively(Reservation, reservations_table)
    mapper_registry.map_imperatively(
        Member,
        members_table,
        properties={
            "loans": relationship(
                Loan,
                primaryjoin=members_table.c.member_id == loans_table.c.member_id,
                foreign_keys=[loans_table.c.member_id],
                cascade="all, delete-orphan",
                lazy="joined",
            ),
        },
    )
    _mapped = True


def create_schema(engine: Engine) -> None:
    metadata.create_all(engine)
