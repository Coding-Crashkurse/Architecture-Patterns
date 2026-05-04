"""UoW with transactional outbox.

`commit_with_outbox()` is the new recommended path: it drains events from aggregates,
writes them to the outbox table inside the same DB transaction as the domain change,
then commits and returns the events so the caller can also dispatch them locally.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Self

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from adapters.outbox import OutboxRepository
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

    def _drain_aggregate_events(self) -> list[Event]:
        collected: list[Event] = []
        for book in self.books.seen:
            while book.events:
                collected.append(book.events.pop(0))
        return collected

    @abstractmethod
    def commit(self) -> None: ...

    @abstractmethod
    def commit_with_outbox(self) -> list[Event]: ...

    @abstractmethod
    def rollback(self) -> None: ...


class FakeUnitOfWork(AbstractUnitOfWork):
    def __init__(self) -> None:
        self.books = FakeBookRepository()
        self.members = FakeMemberRepository()
        self.reservations = FakeReservationRepository()
        self.committed = False
        self.outbox_log: list[Event] = []

    def commit(self) -> None:
        self.committed = True

    def commit_with_outbox(self) -> list[Event]:
        events = self._drain_aggregate_events()
        self.outbox_log.extend(events)
        self.commit()
        return events

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
                "concurrent update detected -- another transaction modified the aggregate"
            ) from exc

    def commit_with_outbox(self) -> list[Event]:
        """Drain aggregate events, persist to outbox, commit. One transaction."""
        assert self.session is not None
        events = self._drain_aggregate_events()
        outbox = OutboxRepository(self.session)
        for ev in events:
            outbox.append(ev)
        self.commit()
        return events

    def rollback(self) -> None:
        if self.session is not None:
            self.session.rollback()


def make_uow_factory(engine: Engine):
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return lambda: SqlAlchemyUnitOfWork(factory)
