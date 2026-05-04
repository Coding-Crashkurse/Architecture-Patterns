"""Process Manager / Saga for inter-branch book transfers.

State machine:
    requested -> shipped -> received                        (happy path)
    requested -> shipped -> [receive fails] -> compensated  (failure path)

Each handler updates the Transfer state, mutates BranchStock for source/destination,
and emits an event. Event handlers chain the next command. The saga owns the
state, so a crashed process can resume by re-reading the Transfer row.
"""

from __future__ import annotations

from adapters.repository import BranchStockRepository, TransferRepository
from domain.commands import (
    CompensateShipment,
    ReceiveBook,
    RequestTransfer,
    ShipBook,
)
from domain.events import (
    BookReceived,
    BookShipped,
    TransferCompleted,
    TransferFailed,
    TransferRequested,
)
from domain.model import ISBN, Transfer, TransferError


def request_transfer(cmd: RequestTransfer, bus) -> dict:
    with bus.uow_factory() as uow:
        TransferRepository(uow.session).add(
            Transfer(
                transfer_id=cmd.transfer_id,
                isbn=ISBN(cmd.isbn),
                from_branch=cmd.from_branch,
                to_branch=cmd.to_branch,
                state="requested",
                simulate_receive_failure=getattr(cmd, "simulate_receive_failure", False),
            )
        )
        uow.commit()
    bus.enqueue(
        TransferRequested(
            transfer_id=cmd.transfer_id,
            isbn=cmd.isbn,
            from_branch=cmd.from_branch,
            to_branch=cmd.to_branch,
        )
    )
    return {"transfer_id": cmd.transfer_id, "state": "requested"}


def ship_book(cmd: ShipBook, bus) -> None:
    with bus.uow_factory() as uow:
        stock_repo = BranchStockRepository(uow.session)
        transfer_repo = TransferRepository(uow.session)
        transfer = transfer_repo.get(cmd.transfer_id)
        if transfer is None:
            return
        source = stock_repo.get(ISBN(cmd.isbn), cmd.from_branch)
        if source is None:
            transfer.state = "failed"
            transfer.failure_reason = f"branch {cmd.from_branch} has no stock row"
            uow.commit()
            bus.enqueue(TransferFailed(transfer_id=cmd.transfer_id, isbn=cmd.isbn, reason=transfer.failure_reason))
            return
        try:
            source.ship_one()
        except TransferError as exc:
            transfer.state = "failed"
            transfer.failure_reason = str(exc)
            uow.commit()
            bus.enqueue(TransferFailed(transfer_id=cmd.transfer_id, isbn=cmd.isbn, reason=str(exc)))
            return
        transfer.state = "shipped"
        uow.commit()
    bus.enqueue(
        BookShipped(
            transfer_id=cmd.transfer_id,
            isbn=cmd.isbn,
            from_branch=cmd.from_branch,
            to_branch=cmd.to_branch,
        )
    )


def receive_book(cmd: ReceiveBook, bus) -> None:
    with bus.uow_factory() as uow:
        transfer_repo = TransferRepository(uow.session)
        transfer = transfer_repo.get(cmd.transfer_id)
        if transfer is None:
            return
        if transfer.simulate_receive_failure:
            transfer.failure_reason = "simulated downstream failure during receive"
            uow.commit()
            bus.enqueue(TransferFailed(transfer_id=cmd.transfer_id, isbn=cmd.isbn, reason=transfer.failure_reason))
            bus.enqueue(
                CompensateShipment(
                    transfer_id=cmd.transfer_id,
                    isbn=cmd.isbn,
                    from_branch=transfer.from_branch,
                )
            )
            return
        stock = BranchStockRepository(uow.session).get_or_create(ISBN(cmd.isbn), cmd.to_branch)
        stock.receive_one()
        transfer.state = "received"
        uow.commit()
    bus.enqueue(BookReceived(transfer_id=cmd.transfer_id, isbn=cmd.isbn, to_branch=cmd.to_branch))
    bus.enqueue(
        TransferCompleted(
            transfer_id=cmd.transfer_id,
            isbn=cmd.isbn,
            from_branch=transfer.from_branch,
            to_branch=cmd.to_branch,
        )
    )


def compensate_shipment(cmd: CompensateShipment, bus) -> None:
    """The receive failed after the source already shipped — give the copy back."""
    with bus.uow_factory() as uow:
        stock = BranchStockRepository(uow.session).get_or_create(ISBN(cmd.isbn), cmd.from_branch)
        stock.receive_one()
        transfer = TransferRepository(uow.session).get(cmd.transfer_id)
        if transfer is not None:
            transfer.state = "compensated"
        uow.commit()


# --------- Event-side glue: turn TransferRequested -> ShipBook, BookShipped -> ReceiveBook ---------


def on_transfer_requested(event: TransferRequested, bus) -> None:
    bus.enqueue(
        ShipBook(
            transfer_id=event.transfer_id,
            isbn=event.isbn,
            from_branch=event.from_branch,
            to_branch=event.to_branch,
        )
    )


def on_book_shipped(event: BookShipped, bus) -> None:
    bus.enqueue(
        ReceiveBook(transfer_id=event.transfer_id, isbn=event.isbn, to_branch=event.to_branch)
    )
