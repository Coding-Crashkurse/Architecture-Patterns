"""Consumer worker: XREADs the stream, dedupes via inbox, hands the event to a callback."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable

from sqlalchemy.orm import sessionmaker

from adapters.inbox import InboxRepository


STREAM = "library.events"


class Consumer:
    def __init__(
        self,
        session_factory: sessionmaker,
        redis_client,
        on_event: Callable[[str, dict], None],
        block_ms: int = 50,
    ) -> None:
        self._session_factory = session_factory
        self._redis = redis_client
        self._on_event = on_event
        self._block = block_ms
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_id = "0-0"

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="inbox-consumer")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                response = self._redis.xread({STREAM: self._last_id}, block=self._block, count=20)
            except Exception:
                continue
            if not response:
                continue
            for _stream, entries in response:
                for entry_id, fields in entries:
                    self._last_id = entry_id.decode() if isinstance(entry_id, bytes) else entry_id
                    self._handle(fields)

    def _handle(self, fields: dict) -> None:
        decoded = {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
            for k, v in fields.items()
        }
        message_id = decoded["message_id"]
        with self._session_factory() as session:
            inbox = InboxRepository(session)
            if inbox.is_processed(message_id):
                return  # idempotent: already handled
            payload = json.loads(decoded["payload"])
            try:
                self._on_event(decoded["event_type"], payload)
            except Exception:
                session.rollback()
                return
            inbox.mark_processed(message_id)
            session.commit()
