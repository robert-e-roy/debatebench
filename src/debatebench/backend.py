"""The backend seam: one async method between the orchestrator and a model server.

Types per ADR-009. The single-method async ``Protocol`` shape is a design lift
from arbgjr/multi-agent-debate's ``LLMProviderProtocol`` (MIT; see ADR-001).
This module imports only the standard library (ADR-008).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True)
class GenerationRequest:
    messages: tuple[Message, ...]
    max_completion_tokens: int  # the per-phase budget
    seed: int | None = None  # the run's seed, sent with every request (ADR-009)


@dataclass(frozen=True)
class GenerationResult:
    """A reply exactly as the server gave it.

    Empty text and a completion_tokens count over budget are returned as they
    are: judging a reply is the orchestrator's job (Hard Rules 1 and 5).
    """

    text: str
    prompt_tokens: int
    completion_tokens: int
    finish_reason: str
    latency_ms: int


class BackendError(Exception):
    """No usable reply: an HTTP error, a timeout, or a malformed or usage-less reply."""


class Backend(Protocol):
    async def generate(self, request: GenerationRequest) -> GenerationResult: ...
