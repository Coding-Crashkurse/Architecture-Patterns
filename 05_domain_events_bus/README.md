# Phase 5 — Domain Events + Internal Message Bus

## What this phase shows

Aggregates record what happened to them as **domain events** (`BookBorrowed`, `BookReturned`, `BookRunningLow`). The UoW collects those events from every aggregate it has seen, and after `commit()` succeeds, the **message bus** dispatches them to registered handlers.

Handlers are pure side effects (here: append to an in-memory `notifications` list, queryable via `GET /notifications`). One event can have N handlers. A handler failing does not roll back the transaction — it is logged and the next handler still runs.

## Use case

Borrowing the last copy of a book triggers two events: a `BookBorrowed` (general loan event) and a `BookRunningLow` (capacity alert). The bus dispatches both independently. The client verifies both notifications appear after a single borrow call.

## Run

```bash
uv run python server.py     # port 8005
uv run python client.py
uv run pytest
```

## When NOT to use a message bus

For a use case that has only one downstream effect, an explicit function call is clearer than going through a bus. Add the bus the moment you have **two or more independent reactions** to the same fact, or when one of those reactions is naturally async (notification, projection update).

## Smell that you're overdoing it

If your handlers know about each other ("after notify_borrow runs, then alert_running_low"), you've reinvented sequential code with extra indirection. Handlers must be independent. If they aren't, model the dependency explicitly as a Saga (Phase 9).
