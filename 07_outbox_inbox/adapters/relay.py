"""Relay worker: pulls unsent rows from the outbox and XADDs them to Redis Streams."""

from __future__ import annotations

import threading
import time

from sqlalchemy.orm import sessionmaker

from adapters.outbox import OutboxRepository


STREAM = "library.events"


class Relay:
    def __init__(
        self,
        session_factory: sessionmaker,
        redis_client,
        poll_interval: float = 0.05,
    ) -> None:
        self._session_factory = session_factory
        self._redis = redis_client
        self._poll = poll_interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="outbox-relay")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:
                pass
            self._stop.wait(self._poll)

    def _tick(self) -> None:
        with self._session_factory() as session:
            repo = OutboxRepository(session)
            rows = repo.fetch_unsent()
            if not rows:
                return
            for row in rows:
                self._redis.xadd(
                    STREAM,
                    {
                        "message_id": row.message_id,
                        "event_type": row.event_type,
                        "payload": row.payload,
                    },
                )
                repo.mark_sent(row)
            session.commit()
