# Phase 7 — Outbox + Inbox

## What this phase shows

The Cosmic Python book publishes events directly from the message bus. That works for in-process consumers but breaks the moment a consumer is **external**: the DB commit and the network publish are two operations, and one can succeed while the other fails. This is the **dual-write problem**.

Phase 7 fixes it with two complementary tables:

- **outbox**: domain events are appended in the *same* SQL transaction as the domain change. A separate `Relay` thread later drains the outbox and `XADD`s to a Redis stream. If the publish fails, the row stays unsent and is retried on the next tick — at-least-once.
- **inbox**: a `Consumer` reads the stream, but before applying side-effects it checks the inbox table for the message ID. If already processed, skip. This makes consumers **idempotent** — at-least-once delivery is now safe.

The demo uses `fakeredis` so no infrastructure is needed; in Phase 11 the same code runs against real Redis.

## Use case

A `BookBorrowed` event needs to reach an external notification service. We model it by having the consumer thread append to `external_notifications`. The client borrows + returns a book, then polls `/notifications` and verifies that the events have crossed the outbox -> Redis -> inbox -> external sink path.

## Run

```bash
uv run python server.py     # port 8007 (in-process fakeredis, relay + consumer threads)
uv run python client.py
uv run pytest
```

## When NOT to use Outbox/Inbox

Strictly in-process, single-binary apps with no external consumers don't need it — the in-process bus is enough (Phase 5/6). The day a webhook, a separate service, or a Kafka topic appears, the dual-write problem appears with it; that is when this pattern earns its weight.

## Smell that you're overdoing it

Outbox tables that fill faster than the relay drains, or relay/consumer code that re-implements a real broker poorly. If you find yourself building consumer groups, retries, DLQs, and partition routing by hand, you're past the point where Kafka/NATS/RabbitMQ would be cheaper than maintaining your homemade plumbing.
