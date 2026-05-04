# Phase 1 — Domain Model

## What this phase shows

The domain model in isolation: `Book`, `Member`, `Loan` as plain Python classes carrying business invariants. No persistence, no framework, no service layer. State lives in module-level dicts in `server.py` to make it crystal clear that the domain model itself doesn't know about any of that.

## Use case

Borrowing and returning books, with rules:
- Members can have at most 3 active loans.
- A book can only be borrowed if a copy is available.
- A loan can only be returned once.

## Run

```bash
uv run python server.py     # terminal 1, port 8001
uv run python client.py     # terminal 2
uv run pytest               # automated
```

## When NOT to use this style

Never *ship* a system that keeps state in module-level dicts — this is purely a teaching layout. The point is to show the domain model first, before any infrastructure noise. From Phase 2 onward we put a real Repository in front.

## Smell that you're overdoing it

If your domain model imports `sqlalchemy`, `fastapi`, or `redis`, you've leaked infrastructure into the domain. That's the bug this whole repo's structure is fighting against.
