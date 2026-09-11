"""The B1 ``debate`` command: one argument, stderr only, nothing written to output:."""

import asyncio
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from debatebench.backend import BackendError
from debatebench.cli import dummy_replies, main
from debatebench.config import load_run
from fakes import FakeBackend, reply
from helpers import edit_yaml


def test_no_argument_is_a_usage_error():
    with pytest.raises(SystemExit) as e:
        main([])
    assert e.value.code == 2


def test_console_script_is_installed():
    # Pins the pyproject entry point, which main()-level tests don't exercise.
    script = Path(sys.executable).parent / "debate"
    result = subprocess.run([str(script)], capture_output=True, text=True)
    assert result.returncode == 2
    assert "usage: debate" in result.stderr and result.stdout == ""


def test_flags_are_rejected(run_dir: Path):
    # ADR-007: the file is the only input; there is no --output flag.
    with pytest.raises(SystemExit) as e:
        main([str(run_dir / "run.yaml"), "--output", "x.json"])
    assert e.value.code == 2


def test_config_error_goes_to_stderr(run_dir: Path, capfd):
    edit_yaml(run_dir / "run.yaml", lambda d: d.pop("output"))
    assert main([str(run_dir / "run.yaml")]) == 1
    out, err = capfd.readouterr()
    assert out == ""
    assert "debate: config error:" in err and "output is required" in err


def test_dummy_replies_one_per_side(run_dir: Path, capfd):
    config = load_run(run_dir / "run.yaml")
    fakes = [FakeBackend(reply("For the tax.")), FakeBackend(reply("Against the tax."))]

    results = asyncio.run(dummy_replies(config, fakes))

    assert [r.text for r in results] == ["For the tax.", "Against the tax."]
    for side, fake, position in zip(config.sides, fakes, ["for", "against"]):
        (request,) = fake.requests
        assert request.max_completion_tokens == side.budget
        system, user = request.messages
        assert side.team.name in system.content
        assert f"you argue {position} the motion" in system.content  # pro, then con
        assert config.topic in user.content
    out, err = capfd.readouterr()
    assert out == ""  # Hard Rule 7
    assert "side 0 (pro)" in err and "side 1 (con)" in err
    assert "For the tax." in err and "Against the tax." in err
    assert not config.output.exists()  # no transcript until B3 (ADR-005 is still Proposed)


def test_overshoot_is_reported_not_judged(run_dir: Path, capfd):
    config = load_run(run_dir / "run.yaml")
    fakes = [FakeBackend(reply(completion_tokens=2001)), FakeBackend(reply())]
    asyncio.run(dummy_replies(config, fakes))
    assert "2001 of 2000 completion tokens (over budget)" in capfd.readouterr().err


def test_failing_side_is_named(run_dir: Path):
    config = load_run(run_dir / "run.yaml")
    fakes = [FakeBackend(reply()), FakeBackend(BackendError("HTTP 500: boom"))]
    with pytest.raises(BackendError, match=r"side 1 \(Free-Market Conservative\): HTTP 500: boom"):
        asyncio.run(dummy_replies(config, fakes))


def _closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_unreachable_server_fails_loudly(run_dir: Path, capfd):
    # A real connection attempt to a port nothing listens on: no model, no server.
    url = f"http://127.0.0.1:{_closed_port()}/v1"

    def point_at_nothing(data):
        del data["seed"]
        for side in data["teams"]:
            side["base_url"] = url

    edit_yaml(run_dir / "run.yaml", point_at_nothing)
    assert main([str(run_dir / "run.yaml")]) == 1
    out, err = capfd.readouterr()
    assert out == ""
    assert "generated seed" in err  # ADR-007 §5: logged to stderr immediately
    assert "debate: backend error: side 0" in err
    assert not (run_dir / "transcript.json").exists()
