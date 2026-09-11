"""Live tests against AFM via fm serve (ADR-003). Opt in with DEBATEBENCH_LIVE_TESTS=1.

The fixture starts fm serve itself and stops it afterwards. That's test setup,
not the tool, which never starts servers (ADR-003, ADR-004).
"""

import asyncio
import os
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

from debatebench.backend import BackendError, GenerationRequest, Message
from debatebench.cli import main
from debatebench.config import load_run
from debatebench.events import EventBus, EventType
from debatebench.openai_compat import OpenAICompatibleBackend, open_client
from debatebench.orchestrator import DebateError, run_debate
from helpers import edit_yaml

pytestmark = pytest.mark.skipif(
    os.environ.get("DEBATEBENCH_LIVE_TESTS") != "1",
    reason="live model tests are opt-in: set DEBATEBENCH_LIVE_TESTS=1",
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_fm(log_dir: Path):
    """Start one fm serve on a free port and wait for it to answer."""
    fm = shutil.which("fm")
    if fm is None:
        # Opted in but can't run: fail, never skip (ADR-004).
        pytest.fail("DEBATEBENCH_LIVE_TESTS=1 but no fm CLI found; AFM needs macOS 27 (ADR-003)")
    port = _free_port()
    log = log_dir / f"fm-serve-{port}.log"
    with log.open("wb") as log_file:
        server = subprocess.Popen([fm, "serve", "--port", str(port)], stdout=log_file, stderr=log_file)
    deadline = time.monotonic() + 60
    while True:
        if server.poll() is not None:
            pytest.fail(f"fm serve exited with {server.returncode}: {log.read_text()}")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1):
                return server, f"http://127.0.0.1:{port}/v1"
        except OSError:
            if time.monotonic() > deadline:
                pytest.fail(f"fm serve not ready after 60 s: {log.read_text()}")
            time.sleep(0.2)


def _stop(server):
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()


@pytest.fixture(scope="module")
def afm_base_url(tmp_path_factory):
    server, base_url = _start_fm(tmp_path_factory.mktemp("fm"))
    try:
        yield base_url
    finally:
        _stop(server)


def _use_afm(base_url: str, phases, budget: int):
    def mutate(data):
        data["format"]["phases"] = list(phases)
        for side in data["teams"]:
            side.update(model="system", base_url=base_url, budget=budget)
            side.pop("prep_budget", None)

    return mutate


async def _debate(config, base_url, events=None):
    async with open_client() as client:
        backends = [OpenAICompatibleBackend(client, base_url, "system") for _ in config.sides]
        return await run_debate(config, backends, events)


def _generate(base_url: str, request: GenerationRequest):
    async def go():
        async with open_client() as client:
            return await OpenAICompatibleBackend(client, base_url, "system").generate(request)

    return asyncio.run(go())


def test_afm_replies_through_the_protocol(afm_base_url):
    request = GenerationRequest(
        messages=(
            Message("system", "You are a debater. Be brief."),
            Message("user", "In one sentence: should cities ban cars from their centers?"),
        ),
        max_completion_tokens=64,
    )
    result = _generate(afm_base_url, request)
    print(f"\nAFM: {result}")
    assert result.text.strip()
    assert result.prompt_tokens > 0 and result.completion_tokens > 0
    assert result.finish_reason
    assert result.latency_ms > 0


def test_afm_context_overflow_is_a_backend_error(afm_base_url):
    # Over AFM's ~4,096-token limit: HTTP 500, which must fail the turn (ADR-003).
    # Use ordinary prose: "word " * 6000 trips the guardrails instead, which is
    # also HTTP 500, so only the message proves this is the overflow case.
    sentence = (
        "The city council met on Tuesday to review the transit budget, "
        "hear public comment on bus routes, and schedule a vote on bike lanes. "
    )
    request = GenerationRequest(messages=(Message("user", sentence * 200),), max_completion_tokens=16)
    with pytest.raises(BackendError, match="HTTP 500: The session's transcript exceeded the model's context size"):
        _generate(afm_base_url, request)


def test_a_full_debate_runs_on_afm(run_dir: Path, afm_base_url):
    # B2's deliverable: every phase, both sides, one transcript in memory.
    phases = ("opening", "rebuttal", "retort", "conclusion")
    edit_yaml(run_dir / "run.yaml", _use_afm(afm_base_url, phases, budget=96))
    config = load_run(run_dir / "run.yaml")

    transcript = asyncio.run(_debate(config, afm_base_url))

    assert [t.phase for t in transcript.turns] == [p for p in phases for _ in range(2)]
    assert len({(t.phase_index, t.side_index) for t in transcript.turns}) == 8
    assert all(t.text.strip() for t in transcript.turns)
    assert all(t.usage.completion_tokens <= 96 + 16 for t in transcript.turns)
    print("\n" + "\n".join(
        f"[{t.phase} - side {t.side_index}, {t.usage.completion_tokens} tok] {t.text.strip()[:100]}…"
        for t in transcript.turns
    ))


def test_killing_the_server_mid_run_aborts_the_debate(run_dir: Path, tmp_path_factory):
    # B2's exit gate: break a phase mid-run and confirm the run hard-fails.
    server, base_url = _start_fm(tmp_path_factory.mktemp("fm-kill"))
    try:
        edit_yaml(run_dir / "run.yaml", _use_afm(base_url, ("opening", "rebuttal"), budget=48))
        config = load_run(run_dir / "run.yaml")

        events = EventBus()

        def kill_after_the_first_turn(event):
            if event.type is EventType.TURN_COMPLETED and (event.phase_index, event.side_index) == (0, 0):
                _stop(server)

        events.subscribe(kill_after_the_first_turn)

        with pytest.raises(DebateError, match=r"phase 0 \(opening\), side 1"):
            asyncio.run(_debate(config, base_url, events))
    finally:
        _stop(server)


def test_debate_command_against_afm(run_dir: Path, afm_base_url, capfd):
    edit_yaml(run_dir / "run.yaml", _use_afm(afm_base_url, ("opening", "conclusion"), budget=96))
    code = main([str(run_dir / "run.yaml")])
    out, err = capfd.readouterr()
    print(f"\n{err}")
    assert code == 0, err
    assert out == ""  # Hard Rule 7
    assert "phase 0: opening" in err and "phase 1: conclusion" in err
    assert "4 turns over 2 phases" in err
    assert not (run_dir / "transcript.json").exists()
