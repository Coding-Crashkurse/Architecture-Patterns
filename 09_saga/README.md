# Phase 9 — Saga / Process Manager

## What this phase shows

A **process manager** orchestrates a long-running workflow that spans multiple aggregates and may need **compensation** on failure. The book inter-branch transfer is the running example:

State machine on the `Transfer` entity:

```
requested -> shipped -> received                      (happy path)
requested -> shipped -> [receive fails] -> compensated  (failure path)
```

Each step is its own DB transaction, owned by one command handler. The saga does not need a full state-machine library — the `state` column on the `Transfer` row is the source of truth, and dispatching `ShipBook` / `ReceiveBook` is just the bus chain from Phase 6.

The compensation step (`CompensateShipment`) returns the shipped copy to the source branch when the destination's receive fails. That's the difference between **choreography** (handlers reacting to events with no global view) and **orchestration** (a saga that knows the steps and how to roll them back).

## Use case

`POST /transfer` with `simulate_receive_failure=false` moves a copy from `north` to `south`. With `simulate_receive_failure=true`, the same flow ships, then fails on receive, then compensates — final state of `north` is back to where it started.

## Run

```bash
uv run python server.py     # port 8009
uv run python client.py     # runs both happy and failure paths
uv run pytest
```

## When NOT to use a Saga

For a workflow that fits in a single transaction across one aggregate, just use a service function. Sagas pay off when steps cross transactional boundaries (different aggregates, different services, async waits). Don't introduce a saga to model what `borrow_book(...)` already does.

## Smell that you're overdoing it

Sagas with dozens of steps and compensations for every step start to look like distributed `try/except` ladders. If your workflow has that shape, consider whether the steps really need to be separate transactions, or whether a single richer aggregate would simplify it.
