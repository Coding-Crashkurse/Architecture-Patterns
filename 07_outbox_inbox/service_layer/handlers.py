"""Command handlers and event handlers.

Command handlers do the work and must succeed; event handlers react to facts and
may emit further commands. The reservation flow shows the chain:

    ReturnBook (cmd) --> BookReturned (evt) --> FulfillReservation (cmd)
        --> BookBorrowed (evt) + ReservationFulfilled (evt) --> notifications
"""

from __future__ import annotations

from datetime import date

from domain.commands import (
    AddBook,
    AddMember,
    BorrowBook,
    FulfillReservation,
    ReserveBook,
    ReturnBook,
)
from domain.events import (
    BookBorrowed,
    BookReserved,
    BookReturned,
    BookRunningLow,
    ReservationFulfilled,
)
from domain.model import (
    ISBN,
    AlreadyExists,
    Book,
    CannotReserve,
    Member,
    NotFound,
    Reservation,
)


# In-memory log of side-effects (handlers append to it; client can query).
notifications: list[dict] = []


# --------- Command handlers ---------


def add_book(cmd: AddBook, bus) -> None:
    with bus.uow_factory() as uow:
        uow.books.add(
            Book(
                isbn=ISBN(cmd.isbn),
                title=cmd.title,
                total_copies=cmd.total_copies,
                available_copies=cmd.total_copies,
            )
        )
        uow.commit()


def add_member(cmd: AddMember, bus) -> None:
    with bus.uow_factory() as uow:
        if uow.members.get(cmd.member_id) is not None:
            raise AlreadyExists(f"member {cmd.member_id} already exists")
        uow.members.add(Member(member_id=cmd.member_id, name=cmd.name))
        uow.commit()


def borrow_book(cmd: BorrowBook, bus) -> dict:
    with bus.uow_factory() as uow:
        member = uow.members.get(cmd.member_id)
        book = uow.books.get(ISBN(cmd.isbn))
        if member is None:
            raise NotFound(f"member {cmd.member_id} not found")
        if book is None:
            raise NotFound(f"book {cmd.isbn} not found")
        loan = member.borrow(book, today=date.today())
        for ev in uow.commit_with_outbox():
            bus.enqueue(ev)
        return {
            "member_id": loan.member_id,
            "isbn": loan.isbn.value,
            "due_on": loan.due_on.isoformat(),
        }


def return_book(cmd: ReturnBook, bus) -> dict:
    with bus.uow_factory() as uow:
        member = uow.members.get(cmd.member_id)
        book = uow.books.get(ISBN(cmd.isbn))
        if member is None:
            raise NotFound(f"member {cmd.member_id} not found")
        if book is None:
            raise NotFound(f"book {cmd.isbn} not found")
        loan = member.return_book(book, today=date.today())
        for ev in uow.commit_with_outbox():
            bus.enqueue(ev)
        return {
            "member_id": loan.member_id,
            "isbn": loan.isbn.value,
            "returned_on": loan.returned_on.isoformat() if loan.returned_on else "",
        }


def reserve_book(cmd: ReserveBook, bus) -> dict:
    with bus.uow_factory() as uow:
        member = uow.members.get(cmd.member_id)
        book = uow.books.get(ISBN(cmd.isbn))
        if member is None:
            raise NotFound(f"member {cmd.member_id} not found")
        if book is None:
            raise NotFound(f"book {cmd.isbn} not found")
        if book.available_copies > 0:
            raise CannotReserve(
                "book is currently available — borrow it directly instead of reserving"
            )
        reservation = Reservation(
            member_id=cmd.member_id, isbn=ISBN(cmd.isbn), placed_on=date.today()
        )
        uow.reservations.add(reservation)
        uow.commit()
        bus.enqueue(BookReserved(member_id=cmd.member_id, isbn=cmd.isbn))
        return {"member_id": cmd.member_id, "isbn": cmd.isbn, "status": "reserved"}


def fulfill_reservation(cmd: FulfillReservation, bus) -> None:
    """Internal command emitted by an event handler. Best-effort: if no reservation queued, no-op."""
    with bus.uow_factory() as uow:
        reservation = uow.reservations.first_open_for(ISBN(cmd.isbn))
        if reservation is None:
            return
        member = uow.members.get(reservation.member_id)
        book = uow.books.get(ISBN(cmd.isbn))
        if member is None or book is None or book.available_copies == 0:
            return
        reservation.fulfill(on=date.today())
        member.borrow(book, today=date.today())
        for ev in uow.commit_with_outbox():
            bus.enqueue(ev)
        bus.enqueue(ReservationFulfilled(member_id=reservation.member_id, isbn=cmd.isbn))


# --------- Event handlers ---------


def notify_borrow(event: BookBorrowed, bus) -> None:
    notifications.append(
        {
            "type": "BookBorrowed",
            "member_id": event.member_id,
            "isbn": event.isbn,
            "due_on": event.due_on.isoformat(),
        }
    )


def notify_return(event: BookReturned, bus) -> None:
    notifications.append(
        {
            "type": "BookReturned",
            "member_id": event.member_id,
            "isbn": event.isbn,
            "returned_on": event.returned_on.isoformat(),
        }
    )


def alert_running_low(event: BookRunningLow, bus) -> None:
    notifications.append({"type": "BookRunningLow", "isbn": event.isbn, "title": event.title})


def trigger_fulfill_on_return(event: BookReturned, bus) -> None:
    """When a book comes back, kick off a FulfillReservation command."""
    bus.enqueue(FulfillReservation(member_id="<auto>", isbn=event.isbn))


def notify_reserved(event: BookReserved, bus) -> None:
    notifications.append({"type": "BookReserved", "member_id": event.member_id, "isbn": event.isbn})


def notify_fulfilled(event: ReservationFulfilled, bus) -> None:
    notifications.append(
        {"type": "ReservationFulfilled", "member_id": event.member_id, "isbn": event.isbn}
    )


# --------- Wiring ---------


def build_handler_maps() -> tuple[dict, dict]:
    command_handlers = {
        AddBook: add_book,
        AddMember: add_member,
        BorrowBook: borrow_book,
        ReturnBook: return_book,
        ReserveBook: reserve_book,
        FulfillReservation: fulfill_reservation,
    }
    event_handlers: dict = {
        BookBorrowed: [notify_borrow],
        BookReturned: [notify_return, trigger_fulfill_on_return],
        BookRunningLow: [alert_running_low],
        BookReserved: [notify_reserved],
        ReservationFulfilled: [notify_fulfilled],
    }
    return command_handlers, event_handlers


def get_notifications() -> list[dict]:
    return list(notifications)
