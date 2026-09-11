"""The scripted FakeBackend (ADR-004): no model, no server."""

from __future__ import annotations

import asyncio
import time

from debatebench.backend import GenerationRequest, GenerationResult


def reply(
    text: str = "A dummy reply.",
    *,
    prompt_tokens: int = 40,
    completion_tokens: int = 4,
    finish_reason: str = "stop",
    latency_ms: int = 1,
) -> GenerationResult:
    return GenerationResult(text, prompt_tokens, completion_tokens, finish_reason, latency_ms)


class FakeBackend:
    """Answers each call from its script, then from ``auto``, and records every request.

    A script step is a GenerationResult to return or an exception to raise, so a
    test can script a failure, an empty reply or a budget overshoot at a chosen
    turn. ``delay`` waits before answering; ``blocking`` makes that wait a
    deliberately wrong synchronous sleep, which is how the Hard Rule 4 test shows
    it can catch a blocking backend.
    """

    def __init__(
        self,
        *script: GenerationResult | BaseException,
        auto: str | None = None,
        delay: float = 0.0,
        blocking: bool = False,
    ) -> None:
        self._script = list(script)
        self._auto = auto
        self._delay = delay
        self._blocking = blocking
        self.requests: list[GenerationRequest] = []

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.requests.append(request)
        if self._delay:
            if self._blocking:
                time.sleep(self._delay)  # what ADR-001's anti-pattern 4 looks like
            else:
                await asyncio.sleep(self._delay)
        if self._script:
            step = self._script.pop(0)
            if isinstance(step, BaseException):
                raise step
            return step
        if self._auto is not None:
            return reply(f"{self._auto} turn {len(self.requests)}")
        raise AssertionError("FakeBackend called more times than scripted")
