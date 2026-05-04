# Phase 8 — CQRS read paths

## What this phase shows

Writes still go through aggregates, the UoW, and the outbox (Phases 4–7). Reads get their own life: a thin `service_layer/views.py` issues raw SQL against the same DB and returns dicts shaped for the consumer.

The endpoints `/views/available_books`, `/views/overdue_loans`, and `/views/member_history/{id}` never load a `Book` or a `Member` aggregate. They don't need to — they're not changing state, they don't care about invariants, and they want shapes the domain model wouldn't naturally give them (joined `member_name`, computed `is_overdue`, etc.).

## Use case

After borrowing a book, the user wants a list of available titles and the member's loan history. Loading the full Book aggregate to compute "available" or stitching loan + book + member through the ORM is wasteful for a screen that just shows a table.

## Run

```bash
uv run python server.py     # port 8008
uv run python client.py
uv run pytest
```

## When NOT to split read and write

If your read shapes happen to match your aggregate shapes 1:1, just expose the aggregate. Splitting helps when the read shape is denormalised or aggregated across many entities.

## Smell that you're overdoing it

Building a separate read DB, replication pipelines, and projection workers when one indexed SQL view would have done the job. The CQRS read path can be extremely lightweight; it earns weight only in proportion to the read load you can't satisfy from the write store.
