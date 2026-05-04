"""Unit of Work: a single atomic boundary around a use case."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Self

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from adapters.repository import (
    AbstractBookRepository,
    AbstractMemberRepository,
    AbstractReservationRepository,
    FakeBookRepository,
    FakeMemberRepository,
    FakeReservationRepository,
    SqlAlchemyBookRepository,
    SqlAlchemyMemberRepository,
    SqlAlchemyReservationRepository,
)
from domain.events import Event
from domain.model import ConcurrencyError


class AbstractUnitOfWork(ABC):
    books: AbstractBookRepository
    members: AbstractMemberRepository
    reservations: AbstractReservationRepository

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.rollback()

    def collect_new_events(self) -> list[Event]:
        """Drain pending events from every aggregate the repos have seen."""
        collected: list[Event] = []
        for book in self.books.seen:
            while book.events:
                collected.append(book.events.pop(0))
        return collected

    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def rollback(self) -> None: ...


class FakeUnitOfWork(AbstractUnitOfWork):
    def __init__(self) -> None:
        self.books = FakeBookRepository()
        self.members = FakeMemberRepository()
        self.reservations = FakeReservationRepository()
        self.committed = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        pass


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self.session: Session | None = None

    def __enter__(self) -> Self:
        self.session = self._session_factory()
        self.books = SqlAlchemyBookRepository(self.session)
        self.members = SqlAlchemyMemberRepository(self.session)
        self.reservations = SqlAlchemyReservationRepository(self.session)
        return self

    def __exit__(self, *exc) -> None:
        super().__exit__(*exc)
        if self.session is not None:
            self.session.close()
            self.session = None

    def commit(self) -> None:
        assert self.session is not None
        try:
            self.session.commit()
        except StaleDataError as exc:
            self.session.rollback()
            raise ConcurrencyError(
                "concurrent update detected — another transaction modified the aggregate"
            ) from exc

    def rollback(self) -> None:
        if self.session is not None:
            self.session.rollback()


def make_uow_factory(engine: Engine):
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return lambda: SqlAlchemyUnitOfWork(factory)
