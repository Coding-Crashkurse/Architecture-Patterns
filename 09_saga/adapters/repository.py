"""Repository ports + two implementations.

Each repository tracks `seen` aggregates so the UoW can drain their domain events after commit.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from domain.model import Book, BranchStock, ISBN, Member, Reservation, Transfer


class AbstractBookRepository(ABC):
    def __init__(self) -> None:
        self._seen: dict[str, Book] = {}

    def add(self, book: Book) -> None:
        self._add(book)
        self._seen[book.isbn.value] = book

    def get(self, isbn: ISBN) -> Book | None:
        book = self._get(isbn)
        if book is not None:
            self._seen[book.isbn.value] = book
        return book

    @property
    def seen(self) -> list[Book]:
        return list(self._seen.values())

    @abstractmethod
    def _add(self, book: Book) -> None: ...

    @abstractmethod
    def _get(self, isbn: ISBN) -> Book | None: ...


class AbstractMemberRepository(ABC):
    @abstractmethod
    def add(self, member: Member) -> None: ...

    @abstractmethod
    def get(self, member_id: str) -> Member | None: ...


class FakeBookRepository(AbstractBookRepository):
    def __init__(self) -> None:
        super().__init__()
        self._books: dict[str, Book] = {}

    def _add(self, book: Book) -> None:
        self._books[book.isbn.value] = book

    def _get(self, isbn: ISBN) -> Book | None:
        return self._books.get(isbn.value)


class FakeMemberRepository(AbstractMemberRepository):
    def __init__(self) -> None:
        self._members: dict[str, Member] = {}

    def add(self, member: Member) -> None:
        self._members[member.member_id] = member

    def get(self, member_id: str) -> Member | None:
        return self._members.get(member_id)


class SqlAlchemyBookRepository(AbstractBookRepository):
    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session

    def _add(self, book: Book) -> None:
        self.session.add(book)

    def _get(self, isbn: ISBN) -> Book | None:
        return self.session.query(Book).filter_by(isbn=isbn).first()


class SqlAlchemyMemberRepository(AbstractMemberRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, member: Member) -> None:
        self.session.add(member)

    def get(self, member_id: str) -> Member | None:
        return self.session.query(Member).filter_by(member_id=member_id).first()


class AbstractReservationRepository(ABC):
    @abstractmethod
    def add(self, reservation: Reservation) -> None: ...

    @abstractmethod
    def first_open_for(self, isbn: ISBN) -> Reservation | None: ...


class FakeReservationRepository(AbstractReservationRepository):
    def __init__(self) -> None:
        self._items: list[Reservation] = []

    def add(self, reservation: Reservation) -> None:
        self._items.append(reservation)

    def first_open_for(self, isbn: ISBN) -> Reservation | None:
        for r in self._items:
            if r.isbn == isbn and r.is_open:
                return r
        return None


class SqlAlchemyReservationRepository(AbstractReservationRepository):
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, reservation: Reservation) -> None:
        self.session.add(reservation)

    def first_open_for(self, isbn: ISBN) -> Reservation | None:
        return (
            self.session.query(Reservation)
            .filter_by(isbn=isbn, fulfilled_on=None)
            .order_by(Reservation.placed_on.asc(), Reservation.id.asc())
            .first()
        )


class BranchStockRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, isbn: ISBN, branch: str) -> BranchStock | None:
        return self.session.query(BranchStock).filter_by(isbn=isbn, branch=branch).first()

    def get_or_create(self, isbn: ISBN, branch: str) -> BranchStock:
        existing = self.get(isbn, branch)
        if existing is not None:
            return existing
        stock = BranchStock(isbn=isbn, branch=branch, copies=0)
        self.session.add(stock)
        return stock

    def add(self, stock: BranchStock) -> None:
        self.session.add(stock)


class TransferRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, transfer: Transfer) -> None:
        self.session.add(transfer)

    def get(self, transfer_id: str) -> Transfer | None:
        return self.session.query(Transfer).filter_by(transfer_id=transfer_id).first()
