"""Message bus that distinguishes Commands from Events.

- Command: exactly one handler. Failure propagates. Caller sees the error.
- Event: 0..n handlers. Each one runs independently; failures are logged, never re-raised.

Both Commands and Events emitted while handling can be appended to the queue, so
a chain like (ReturnBook command) -> BookReturned event -> FulfillReservation command
is a single message-bus run.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

from domain.commands import Command
from domain.events import Event


logger = logging.getLogger(__name__)

E = TypeVar("E", bound=Event)
C = TypeVar("C", bound=Command)


class Bus:
    def __init__(
        self,
        uow_factory: Callable,
        event_handlers: dict[type[Event], list[Callable]],
        command_handlers: dict[type[Command], Callable],
    ) -> None:
        self.uow_factory = uow_factory
        self._event_handlers = event_handlers
        self._command_handlers = command_handlers
        self._queue: list[Command | Event] = []

    def handle(self, message: Command | Event) -> object:
        self._queue.append(message)
        first_result: object = None
        first = True
        while self._queue:
            current = self._queue.pop(0)
            if isinstance(current, Command):
                result = self._handle_command(current)
                if first:
                    first_result = result
                    first = False
            else:
                self._handle_event(current)
        return first_result

    def enqueue(self, message: Command | Event) -> None:
        self._queue.append(message)

    def _handle_command(self, command: Command) -> object:
        handler = self._command_handlers.get(type(command))
        if handler is None:
            raise RuntimeError(f"no command handler registered for {type(command).__name__}")
        return handler(command, self)

    def _handle_event(self, event: Event) -> None:
        for handler in self._event_handlers.get(type(event), []):
            try:
                handler(event, self)
            except Exception:
                logger.exception("event handler %r failed for %r — continuing", handler, event)
