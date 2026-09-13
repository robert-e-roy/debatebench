"""The openai-compatible adapter against a mocked transport: no server needed."""

import asyncio
import json
from dataclasses import replace

import httpx
import pytest

from debatebench.backend import BackendError, GenerationRequest, Message
from debatebench.openai_compat import OpenAICompatibleBackend, open_client

BASE_URL = "http://127.0.0.1:19760/v1"
REQUEST = GenerationRequest(
    messages=(Message("system", "You are terse."), Message("user", "Say hi.")),
    max_completion_tokens=64,
)


def _ok(content="Hi.", *, usage=None, finish_reason="stop"):
    body = {
        "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 2, "total_tokens": 14} if usage is None else usage,
    }
    return httpx.Response(200, json=body)


def _raises(error):
    def handler(request):
        raise error

    return handler


def _generate(handler, request=REQUEST, base_url=BASE_URL):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await OpenAICompatibleBackend(client, base_url, "system").generate(request)

    return asyncio.run(go())


def test_request_shape_sends_both_budget_fields():
    seen = []

    def handler(request):
        seen.append(request)
        return _ok()

    _generate(handler)
    (sent,) = seen
    assert sent.method == "POST"
    assert str(sent.url) == f"{BASE_URL}/chat/completions"
    assert json.loads(sent.content) == {
        "model": "system",
        "messages": [{"role": "system", "content": "You are terse."}, {"role": "user", "content": "Say hi."}],
        # Both, at the same value (ADR-018 §4). fm serve honours only the first,
        # vllm-mlx and Ollama only the second, mlx_lm both.
        "max_completion_tokens": 64,
        "max_tokens": 64,
        "stream": False,  # explicit, because fm serve streams otherwise
    }


def test_the_two_budget_fields_never_disagree():
    # A server honouring both must not see two different caps.
    seen = []
    _generate(lambda r: seen.append(r) or _ok(), request=replace(REQUEST, max_completion_tokens=123))
    body = json.loads(seen[0].content)

    assert body["max_tokens"] == body["max_completion_tokens"] == 123


def test_seed_is_sent_only_when_the_request_carries_one():
    with_seed, without_seed = [], []
    _generate(lambda r: with_seed.append(r) or _ok(), request=replace(REQUEST, seed=7))
    _generate(lambda r: without_seed.append(r) or _ok())

    assert json.loads(with_seed[0].content)["seed"] == 7
    assert "seed" not in json.loads(without_seed[0].content)


def test_trailing_slash_in_base_url():
    seen = []
    _generate(lambda r: seen.append(r) or _ok(), base_url=BASE_URL + "/")
    assert str(seen[0].url) == f"{BASE_URL}/chat/completions"


def test_reply_is_parsed():
    result = _generate(lambda r: _ok("Hello there."))
    assert result.text == "Hello there."
    assert (result.prompt_tokens, result.completion_tokens) == (12, 2)
    assert result.finish_reason == "stop"
    assert result.latency_ms >= 0


def test_over_budget_and_empty_replies_are_returned_as_they_are():
    # Judging a reply is the orchestrator's job (ADR-009).
    over = _generate(lambda r: _ok(usage={"prompt_tokens": 12, "completion_tokens": 99}))
    assert over.completion_tokens == 99
    assert _generate(lambda r: _ok("")).text == ""


FAILURES = [
    ("empty usage", lambda r: _ok(usage={}), "usage.prompt_tokens is None"),
    ("usage missing", lambda r: httpx.Response(200, json={"choices": [
        {"message": {"content": "Hi."}, "finish_reason": "stop"}]}), "no token usage"),
    ("usage is a boolean", lambda r: _ok(usage={"prompt_tokens": 1, "completion_tokens": True}),
     "usage.completion_tokens is True"),
    ("negative usage", lambda r: _ok(usage={"prompt_tokens": -1, "completion_tokens": 2}), "usage.prompt_tokens is -1"),
    ("no choices", lambda r: httpx.Response(200, json={"choices": [], "usage": {}}), "malformed reply: no choices"),
    ("null content", lambda r: _ok(None), "content is not a string"),
    ("no finish_reason", lambda r: _ok(finish_reason=None), "finish_reason is missing"),
    # A reasoning model can spend a whole budget thinking (mlx_lm.server, B3).
    ("reasoning but no answer", lambda r: httpx.Response(200, json={
        "choices": [{"message": {"role": "assistant", "reasoning": "Let me think…"}, "finish_reason": "length"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 32}}),
     "all reasoning and no answer"),
    ("not JSON", lambda r: httpx.Response(200, text="<html>"), "reply is not JSON"),
    # AFM's context overflow, as ADR-003 measured it: HTTP 500 with the reason only in the message.
    ("context overflow", lambda r: httpx.Response(500, json={"error": {
        "message": "The session's transcript exceeded the model's context size.", "type": "server_error"}}),
     "HTTP 500: The session's transcript exceeded the model's context size."),
    ("404 with a text body", lambda r: httpx.Response(404, text="Not Found"), "HTTP 404: Not Found"),
    ("connection refused", _raises(httpx.ConnectError("Connection refused")), "request failed: Connection refused"),
    ("read timeout", _raises(httpx.ReadTimeout("")), "timed out (ReadTimeout)"),
]


@pytest.mark.parametrize("handler, expected", [c[1:] for c in FAILURES], ids=[c[0] for c in FAILURES])
def test_failures_raise_backend_error(handler, expected):
    with pytest.raises(BackendError) as e:
        _generate(handler)
    assert expected in str(e.value)
    assert f"{BASE_URL}/chat/completions" in str(e.value)


def test_client_timeouts_are_not_httpx_defaults():
    # httpx's 5 s default would kill real turns (ADR-008).
    async def go():
        async with open_client() as client:
            return client.timeout

    timeout = asyncio.run(go())
    assert timeout.connect == 5.0
    assert timeout.read == 600.0
