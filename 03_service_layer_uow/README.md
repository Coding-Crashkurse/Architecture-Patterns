# Phase 3 — Service Layer + Unit of Work

## What this phase shows

The HTTP endpoints are now stupid: they parse a Pydantic body and call into `service_layer.services`. The service functions take a **UnitOfWork** plus plain values, do the orchestration, and commit once.

The UoW packages two things into one object:
- a **transaction boundary** (`__enter__` opens, `commit()` flushes, `__exit__` rolls back),
- access to the right **repositories** (`uow.books`, `uow.members`).

`FakeUnitOfWork` exists so the service layer can be tested without any DB at all.

## Use case

`borrow_book(member_id, isbn, uow)` and `return_book(...)` — same domain logic, but now there is exactly one place to find it, and it is testable with no FastAPI and no SQLAlchemy.

## Run

```bash
uv run python server.py     # port 8003
uv run python client.py
uv run pytest
```

## When NOT to use a Service Layer

If your endpoint is genuinely just `INSERT INTO …` with one validation, a service layer is paperwork. Add it the moment a use case starts touching multiple aggregates or has rules that go beyond a single CRUD.

## Smell that you're overdoing it

A service layer that just shuffles values from Pydantic models into ORM models is anaemic — it's the FastAPI handler with extra steps. The smell: every service function is two lines and the test is `mock(repo); call_service; assert mock_called`.
