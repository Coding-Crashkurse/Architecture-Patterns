# Phase 4 — Aggregates + Optimistic Concurrency

## What this phase shows

`Book` is now treated as an **aggregate root** with an explicit consistency boundary: the copy counter and a `version` field travel together. Every state change inside the aggregate (`borrow_one`, `return_one`) bumps `version`.

The SQLAlchemy mapper uses `version_id_col`, so every `UPDATE` is emitted with a `WHERE version = <expected>` predicate. If a concurrent transaction has already moved the row forward, the UPDATE matches zero rows and SQLAlchemy raises `StaleDataError`. The `SqlAlchemyUnitOfWork.commit()` translates that into a domain-level `ConcurrencyError`, and the API returns 409.

## Use case

Two members try to borrow the same book at the exact same instant. Without versioning, both transactions could read `available_copies = 2`, both decrement to 1, and one decrement is silently lost. With versioning, the second commit fails loudly.

The `/admin/race_borrow` endpoint deterministically reproduces the race using a `threading.Barrier`.

## Run

```bash
uv run python server.py     # port 8004
uv run python client.py
uv run pytest
```

## When NOT to use optimistic concurrency

If conflict is rare AND retrying is expensive (e.g., the user already saw a confirmation page), pessimistic locking (`SELECT ... FOR UPDATE`) is a reasonable alternative. Optimistic locking shines when conflict is rare AND retry is cheap (most user-facing flows).

## Smell that you're overdoing it

Bumping `version` on read-only operations, exposing `version` to API callers as a header they must echo back without good reason, or wrapping every mutation in retry-with-backoff regardless of conflict rate. Add complexity in proportion to the actual conflict rate you observe.
