"""ADR-033: `thinking: false` sends both switches, and is opt-in because AFM rejects one."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from debatebench.config import ConfigError, load_run
from debatebench.judging import build_fact_check_request, build_request
from debatebench.openai_compat import OpenAICompatibleBackend
from debatebench.prompts import build_request as turn_request
from helpers import edit_yaml
from test_judging import debated
from test_orchestrator import configure


def _sent(request) -> dict:
    """The body the adapter actually puts on the wire."""
    captured = {}

    def capture(req: httpx.Request) -> httpx.Response:
        captured.update(json.loads(req.content))
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1}})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(capture)) as client:
            await OpenAICompatibleBackend(client, "http://x/v1", "m").generate(request)

    asyncio.run(go())
    return captured


def test_thinking_on_is_the_default_and_sends_nothing(run_dir: Path):
    """ADR-033 §3: on by default, so every existing request is byte-identical.

    This is the opposite of ADR-032's field, and for a measured reason: nothing
    rejected `response_format`; AFM returns HTTP 400 on `reasoning_effort`.
    """
    _, transcript = debated(run_dir)
    body = _sent(build_request(transcript, 4000))
    assert "reasoning_effort" not in body
    assert "chat_template_kwargs" not in body


def test_thinking_off_sends_BOTH_switches(run_dir: Path):
    """ADR-033 §2, for ADR-018 §4's reason: no single field works everywhere.

    Ollama reads reasoning_effort and ignores the other; mlx_lm reads
    chat_template_kwargs and ignores this one. Both measured 2026-09-18.
    """
    _, transcript = debated(run_dir)
    body = _sent(build_request(transcript, 4000, thinking=False))
    assert body["reasoning_effort"] == "none"
    assert body["chat_template_kwargs"] == {"enable_thinking": False}


def test_the_fact_check_call_carries_it_too(run_dir: Path):
    _, transcript = debated(run_dir)
    assert _sent(build_fact_check_request(transcript, 4000, thinking=False))["reasoning_effort"] == "none"


def test_a_side_can_turn_it_off_in_run_yaml(run_dir: Path):
    # ADR-033 §4: the confound is about debaters, so it is a per-side key.
    edit_yaml(run_dir / "run.yaml", lambda d: d["teams"][0].update({"thinking": False}))
    config = load_run(run_dir / "run.yaml")
    assert config.sides[0].thinking is False
    assert config.sides[1].thinking is True


def test_a_turn_request_carries_its_own_sides_setting(run_dir: Path):
    edit_yaml(run_dir / "run.yaml", lambda d: d["teams"][0].update({"thinking": False}))
    config = load_run(run_dir / "run.yaml")
    off = turn_request(config.topic, config.sides[0], "opening", config.sides, [], 1)
    on = turn_request(config.topic, config.sides[1], "opening", config.sides, [], 1)
    assert off.thinking is False and on.thinking is True
    assert _sent(off)["reasoning_effort"] == "none"
    assert "reasoning_effort" not in _sent(on)


def test_the_judge_block_takes_it(run_dir: Path):
    def add(d):
        d["judge"] = {"model": "m", "base_url": "http://127.0.0.1:9/v1",
                      "budget": 100, "output": "s.json", "thinking": False}
    edit_yaml(run_dir / "run.yaml", add)
    assert load_run(run_dir / "run.yaml").judge.thinking is False


def test_it_defaults_to_true_everywhere(run_dir: Path):
    config = load_run(run_dir / "run.yaml")
    assert all(side.thinking for side in config.sides)


def test_a_non_boolean_is_a_config_error(run_dir: Path):
    edit_yaml(run_dir / "run.yaml", lambda d: d["teams"][0].update({"thinking": "off"}))
    with pytest.raises(ConfigError, match="thinking"):
        load_run(run_dir / "run.yaml")
