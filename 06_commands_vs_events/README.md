# Phase 6 — Commands vs. Events

## What this phase shows

A single message bus carries two distinct kinds of messages:

| | Command | Event |
|---|---|---|
| Imperative | "do X" | "X happened" |
| Handlers | exactly one | zero or more |
| Failure | propagates to the caller | logged, other handlers still run |
| Examples | `BorrowBook`, `ReturnBook`, `FulfillReservation` | `BookBorrowed`, `BookReturned`, `BookReserved` |

A command handler is allowed to enqueue further commands and events. That's how the **reservation chain** works: `ReturnBook → BookReturned → FulfillReservation → BookBorrowed + ReservationFulfilled`. The user only fired one HTTP call.

## Use case

A book has only one copy. Alice borrows it. Bob is denied a borrow (out of stock) and reserves instead. Alice returns the book; the bus chain automatically borrows the book on Bob's behalf and fires `ReservationFulfilled`. Bob's loans now contain the book — without Bob doing anything.

## Run

```bash
uv run python server.py     # port 8006
uv run python client.py
uv run pytest
```

## When NOT to split commands and events

If you only have one shape of message right now, don't preemptively split. The split earns its weight when (a) you find yourself wanting *N* handlers for the same fact, or (b) you need to model a chain where one operation's success triggers another. If a single function call expresses what you want, use that.

## Smell that you're overdoing it

Naming a command `XHappened` (event-shaped) or naming an event `DoX` (command-shaped) means the distinction has gone fuzzy. If your event handlers fan out into deep call chains, you've reinvented synchronous code with worse stack traces — model the chain explicitly as a Saga (Phase 9) instead.
