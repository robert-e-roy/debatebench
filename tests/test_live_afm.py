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
from debatebench.openai_compat import OpenAICompatibleBackend, open_client
from helpers import edit_yaml

pytestmark = pytest.mark.skipif(
    os.environ.get("DEBATEBENCH_LIVE_TESTS") != "1",
    reason="live model tests are opt-in: set DEBATEBENCH_LIVE_TESTS=1",
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def afm_base_url(tmp_path_factory):
    fm = shutil.which("fm")
    if fm is None:
        # Opted in but can't run: fail, never skip (ADR-004).
        pytest.fail("DEBATEBENCH_LIVE_TESTS=1 but no fm CLI found; AFM needs macOS 27 (ADR-003)")
    port = _free_port()
    log = tmp_path_factory.mktemp("fm") / "fm-serve.log"
    with log.open("wb") as log_file:
        server = subprocess.Popen([fm, "serve", "--port", str(port)], stdout=log_file, stderr=log_file)
    try:
        deadline = time.monotonic() + 60
        while True:
            if server.poll() is not None:
                pytest.fail(f"fm serve exited with {server.returncode}: {log.read_text()}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1):
                    break
            except OSError:
                if time.monotonic() > deadline:
                    pytest.fail(f"fm serve not ready after 60 s: {log.read_text()}")
                time.sleep(0.2)
        yield f"http://127.0.0.1:{port}/v1"
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()


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


def test_debate_command_against_afm(run_dir: Path, afm_base_url, capfd):
    def use_afm(data):
        data["format"]["phases"] = ["opening", "conclusion"]
        for side in data["teams"]:
            side.update(model="system", base_url=afm_base_url, budget=96)
            del side["prep_budget"]

    edit_yaml(run_dir / "run.yaml", use_afm)
    code = main([str(run_dir / "run.yaml")])
    out, err = capfd.readouterr()
    print(f"\n{err}")
    assert code == 0, err
    assert out == ""  # Hard Rule 7
    assert "side 0" in err and "side 1" in err
    assert not (run_dir / "transcript.json").exists()
