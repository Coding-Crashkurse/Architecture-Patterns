# Phase 10 — Event Sourcing (with Snapshots and Versioning)

## What this phase shows

A new, event-sourced `Loan` aggregate lives next to the older CRUD-style domain. For an event-sourced Loan:

- The **event store** (`loan_events` table) is the source of truth.
- State is computed by **folding** the stream: `state = reduce(apply, events, empty_state)`.
- Pure decision functions (`borrow`, `renew`, `return_loan`) take `(state, args) -> new_events`. No I/O, no mutability.
- A **snapshot** of state is persisted every N events (`SNAPSHOT_EVERY = 5`) so loading a long stream stays fast.
- Old event versions are handled by the **upcaster**: `LoanReturnedV1` payloads are mapped to `LoanReturnedV2` with `late_fee_cents=0`. New code never has to know about V1.

## Use case

A loan goes through borrow → renew → renew → return. Inspecting `/es/loans/{id}/history` shows the actual event stream that produced the current state. A third renew is rejected by the decision function, no event is appended.

## Run

```bash
uv run python server.py     # port 8010
uv run python client.py
uv run pytest
```

## When NOT to use Event Sourcing

Per-aggregate. Pick a context where the audit log, time-travel, or rebuilding read models are first-class needs (loans, money movements, regulated workflows). Don't ES the whole system because one corner of it benefits.

## Smell that you're overdoing it

Schema-evolving every event monthly, snapshots needed every dozen events, business questions answered with `SELECT FROM events WHERE …` — at that point the cost of ES exceeds the cost of a normal model with an audit log next to it.
