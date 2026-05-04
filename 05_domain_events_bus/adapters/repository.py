"""Repository ports + two implementations.

Each repository tracks `seen` aggregates so the UoW can drain their domain events after commit.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from domain.model import Book, ISBN, Member


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
