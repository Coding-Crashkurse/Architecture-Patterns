# Phase 11 — Microservices via docker-compose

## What this phase shows

Three branch services (`north`, `south`, `west`), each its own FastAPI process with its own Postgres database, all wired up with `docker compose`. Plus a Redis container for the cross-service event channel (intentionally minimal in this draft — the saga in Phase 9 already proves the pattern; this phase is about the operational shape).

Inter-service communication:

- **HTTP (sync)** — `POST /transfer/send` on one branch calls `POST /transfer/receive` on another. The local decrement and the remote increment are not in one transaction; on remote failure, the sender restores its own copy (compensation).
- **Redis (async)** — wired but used minimally in the first draft. The point of having it is to show that the broker is now a real, separate process.

## Layout

```
11_microservices/
├── docker-compose.yml         # 3 FastAPI + 3 Postgres + 1 Redis
├── Dockerfile                 # used by all three branch services
├── branches/
│   ├── _shared/branch_app.py  # the shared service code (each branch is identical)
│   ├── north/server.py        # entry point
│   ├── south/server.py
│   └── west/server.py
├── client.py                  # talks to all three branches via host ports 8011/8012/8013
├── README.md
├── video.py                   # gitignored
└── video.mp4                  # gitignored
```

## Run

```bash
docker compose up --build -d            # start everything
uv run python client.py                 # smoke test against the running stack
docker compose logs -f north            # watch one branch
docker compose down -v                  # tear down (note: -v drops the volumes)
```

## What this phase is honest about

- Each branch service is intentionally simple (no aggregates, no UoW, no outbox). The point is to show **what changes when bounded contexts become deployable units**, not to re-pack the whole pattern stack.
- For full at-least-once cross-service messaging, copy the outbox/inbox setup from Phase 7 into each service. The shape stays the same — the transport changes from in-process to Redis Streams.

## Smell that you're overdoing it

If every business operation needs a saga across three services, your bounded contexts are wrong. Microservices earn their cost only when each service can be deployed and changed without coordinating with the others. If they can't, they were modules in a monolith all along — go back and ship the monolith.
