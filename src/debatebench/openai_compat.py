"""The one ``openai-compatible`` backend (ADR-001, ADR-003, ADR-009).

A single adapter reaches fm serve (AFM), mlx_lm.server, Ollama and LM Studio,
each through its team's ``base_url``. This is the only module that imports
httpx (ADR-008).
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx

from .backend import DEFAULT_READ_TIMEOUT, BackendError, GenerationRequest, GenerationResult


# httpx defaults to 5 s for every operation, which would kill real turns: B0
# measured 25 s to first token on a 4,000-token prompt (ADR-008). Connecting to
# a local server should be quick; a reply can legitimately take minutes.
# ADR-025 §1: only `read` is configurable. A connect taking over five seconds to
# a local server is a fault, not patience. The default lives in config, which may
# not import httpx (ADR-008).
_FIXED = {"connect": 5.0, "write": 30.0, "pool": 5.0}
TIMEOUT = httpx.Timeout(read=float(DEFAULT_READ_TIMEOUT), **_FIXED)

_ERROR_TEXT_LIMIT = 500


@asynccontextmanager
async def open_client(read_timeout: int = DEFAULT_READ_TIMEOUT) -> AsyncIterator[httpx.AsyncClient]:
    """One HTTP client for a run, shared by every side's backend.

    ``read_timeout`` is seconds to wait for a reply (ADR-025). A 12B reasoning
    model at a large budget can exceed the 600-second default on a cold load —
    measured, and the reason this is not a constant any more.
    """
    async with httpx.AsyncClient(timeout=httpx.Timeout(read=float(read_timeout), **_FIXED)) as client:
        yield client


class OpenAICompatibleBackend:
    """Chat Completions over HTTP: one non-streaming request per call."""

    def __init__(self, client: httpx.AsyncClient, base_url: str, model: str) -> None:
        self._client = client
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        body = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            # Both fields, same value: no single one works everywhere (ADR-018 §4,
            # superseding ADR-003's "never max_tokens"). fm serve honours only
            # max_completion_tokens; vllm-mlx and Ollama honour only max_tokens and
            # returned 305 and 1287 tokens against a cap of 20; mlx_lm honours both.
            # Each server reads the one it knows and ignores the other, and since the
            # value is identical there is nothing to reconcile.
            "max_completion_tokens": request.max_completion_tokens,
            "max_tokens": request.max_completion_tokens,
            # fm serve streams when this is omitted (ADR-003).
            "stream": False,
        }
        if request.seed is not None:
            body["seed"] = request.seed
        if request.response_schema is not None:
            # ADR-032: Ollama constrains decoding to this, so a markdown fence, a
            # stray sentence or an off-enum value becomes unemittable rather than
            # merely discouraged. A server that ignores the field is unaffected;
            # mlx_lm is why this is opt-in (BACKEND-PROBE-RESULTS).
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "debatebench_reply",
                    "strict": True,
                    "schema": request.response_schema,
                },
            }
        started = time.monotonic()
        try:
            response = await self._client.post(self._url, json=body)
        except httpx.TimeoutException as e:
            raise BackendError(f"{self._url}: timed out ({type(e).__name__})") from e
        except (httpx.HTTPError, httpx.InvalidURL) as e:
            raise BackendError(f"{self._url}: request failed: {str(e) or type(e).__name__}") from e
        latency_ms = round((time.monotonic() - started) * 1000)

        # Any non-2xx is a failed turn, including AFM's HTTP 500 on context overflow (ADR-003).
        if not response.is_success:
            raise BackendError(f"{self._url}: HTTP {response.status_code}: {_error_text(response)}")
        try:
            payload = response.json()
        except ValueError as e:
            raise BackendError(f"{self._url}: reply is not JSON: {response.text[:_ERROR_TEXT_LIMIT]!r}") from e
        return _parse(payload, latency_ms, self._url)


def _error_text(response: httpx.Response) -> str:
    """The server's own error message, which is all that tells AFM's failures apart (ADR-003)."""
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"]
        if isinstance(error, str):
            return error
    return response.text[:_ERROR_TEXT_LIMIT] or "(empty body)"


def _parse(payload: Any, latency_ms: int, url: str) -> GenerationResult:
    def malformed(problem: str) -> BackendError:
        return BackendError(f"{url}: malformed reply: {problem}")

    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise malformed("no choices")
    choice = choices[0]
    message = choice.get("message")
    text = message.get("content") if isinstance(message, dict) else None
    reasoning = message.get("reasoning") if isinstance(message, dict) else None
    # A reasoning model can spend a whole budget thinking and never answer. Both
    # mlx_lm.server (B3) and Ollama report the thinking separately, as `reasoning` —
    # but Ollama returns content as "" rather than null when the budget runs out
    # mid-thought (measured 2026-09-14, gemma4:12b), so an empty string has to be
    # caught here too. It used to fall through, and the caller was told only that the
    # reply was empty, or — in judge — to raise a budget that more thinking would eat.
    if isinstance(reasoning, str) and reasoning.strip() and not (isinstance(text, str) and text.strip()):
        raise BackendError(
            f"{url}: the reply is all reasoning and no answer — {len(reasoning)} characters of "
            "thinking and nothing in content, so the budget ran out before the model started "
            "answering. Raising the budget only helps if it clears the whole thinking length; "
            "turning thinking off is the surer fix (Ollama honours reasoning_effort: none, "
            "measured — chat_template_kwargs and think:false do not)."
        )
    if not isinstance(text, str):
        raise malformed("choices[0].message.content is not a string")
    finish_reason = choice.get("finish_reason")
    if not isinstance(finish_reason, str):
        raise malformed("choices[0].finish_reason is missing")

    usage = payload.get("usage")
    if not isinstance(usage, dict):
        # Reporting zeros instead would let any reply pass the budget check (ADR-009).
        raise BackendError(f"{url}: reply has no token usage, so its budget can't be checked")
    counts: dict[str, int] = {}
    for key in ("prompt_tokens", "completion_tokens"):
        value = usage.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise BackendError(f"{url}: reply's usage.{key} is {value!r}, not a token count")
        counts[key] = value

    return GenerationResult(
        text=text,
        prompt_tokens=counts["prompt_tokens"],
        completion_tokens=counts["completion_tokens"],
        finish_reason=finish_reason,
        latency_ms=latency_ms,
    )
