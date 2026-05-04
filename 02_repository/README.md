# Phase 2 — Repository

## What this phase shows

The same domain model from Phase 1, now sitting behind a **Repository**: a domain-defined port (`AbstractBookRepository`, `AbstractMemberRepository`) with two implementations — a `Fake*` for tests and a `SqlAlchemy*` against SQLite.

The domain model still has zero awareness of SQL or sessions. The ORM is mapped imperatively in `adapters/orm.py`, so domain classes remain plain dataclasses.

## Use case

Same as Phase 1 (borrow / return), but state survives a server restart.

## Run

```bash
uv run python server.py     # port 8002
uv run python client.py
uv run pytest               # uses a temp SQLite file
```

## When NOT to use a Repository

For trivial CRUD with no domain logic, a Repository is overhead — the ORM session itself is already a fine repository. The pattern earns its weight only when there are domain rules worth protecting from SQL leaking in.

## Smell that you're overdoing it

Repositories that re-export every query the ORM can do (`find_by_x_and_y_and_z…`) become a leaky façade. Keep the surface narrow: `add` / `get` / a small number of domain-meaningful queries.
