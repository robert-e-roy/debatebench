"""The scripted FakeBackend (ADR-004): no model, no server."""

from __future__ import annotations

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
    """Answers each call with the next step of its script, and records every request.

    A step is a GenerationResult to return or an exception to raise, so a test
    can script a failure, an empty reply or a budget overshoot. B2 adds delays.
    """

    def __init__(self, *script: GenerationResult | BaseException) -> None:
        self._script = list(script)
        self.requests: list[GenerationRequest] = []

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.requests.append(request)
        if not self._script:
            raise AssertionError("FakeBackend called more times than scripted")
        step = self._script.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step
