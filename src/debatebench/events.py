"""Typed events, the seam a live dashboard or fact-check panel attaches to.

The shape — a typed event enum, a dataclass payload, dispatch that takes sync and
async listeners, and one listener's failure never stopping the others — is a
design lift from aragora-debate's `events.py` (MIT; see ADR-001). Nothing
consumes these yet beyond the CLI's own logging. Standard library only (ADR-008).
"""

from __future__ import annotations

import inspect
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum

from .transcript import Turn


class EventType(StrEnum):
    RUN_STARTED = "run_started"
    PHASE_STARTED = "phase_started"
    TURN_STARTED = "turn_started"
    TURN_COMPLETED = "turn_completed"
    PHASE_COMPLETED = "phase_completed"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"


@dataclass(frozen=True)
class DebateEvent:
    type: EventType
    phase_index: int | None = None
    phase: str | None = None
    side_index: int | None = None
    turn: Turn | None = None
    error: str | None = None


Listener = Callable[[DebateEvent], None | Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._listeners: list[Listener] = []

    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    async def emit(self, event: DebateEvent) -> None:
        for listener in list(self._listeners):
            try:
                result = listener(event)
                if inspect.isawaitable(result):
                    await result
            except Exception as e:
                # A broken listener must not abort a debate, but it is never silent.
                name = getattr(listener, "__name__", repr(listener))
                print(f"debatebench: event listener {name} failed: {e!r}", file=sys.stderr)
