"""In-process message bus. Events fan out to N handlers. Failures are logged, not propagated."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

from domain.events import Event


logger = logging.getLogger(__name__)

E = TypeVar("E", bound=Event)
Handler = Callable[[E], None]

HANDLERS: dict[type[Event], list[Handler]] = {}


def register(event_type: type[E], handler: Handler) -> None:
    HANDLERS.setdefault(event_type, []).append(handler)


def handle(events: list[Event]) -> None:
    """Drain the queue, dispatching each event to every registered handler."""
    queue = list(events)
    while queue:
        event = queue.pop(0)
        for handler in HANDLERS.get(type(event), []):
            try:
                handler(event)
            except Exception:
                logger.exception("handler %r failed for event %r", handler, event)
