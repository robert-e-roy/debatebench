"""The ``debate`` command: one argument, stderr only, nothing written to output:."""

import socket
import subprocess
import sys
from pathlib import Path

import pytest

from debatebench.cli import main
from helpers import edit_yaml
from test_orchestrator import configure


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


def test_prep_is_reported_as_not_built_yet(run_dir: Path, capfd):
    configure(run_dir, ("prep", "opening"))
    assert main([str(run_dir / "run.yaml")]) == 1
    out, err = capfd.readouterr()
    assert out == ""
    assert "debate: debate failed:" in err and "arrives in B4" in err


def _closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_unreachable_server_fails_loudly(run_dir: Path, capfd):
    # A real connection attempt to a port nothing listens on: no model, no server.
    url = f"http://127.0.0.1:{_closed_port()}/v1"

    def point_at_nothing(data):
        del data["seed"]
        data["format"]["phases"] = ["opening"]
        for side in data["teams"]:
            side["base_url"] = url
            side.pop("prep_budget", None)

    edit_yaml(run_dir / "run.yaml", point_at_nothing)
    assert main([str(run_dir / "run.yaml")]) == 1
    out, err = capfd.readouterr()
    assert out == ""
    assert "generated seed" in err  # ADR-007 §5: logged to stderr immediately
    assert "debate: debate failed: phase 0 (opening), side 0 (pro" in err
    assert not (run_dir / "transcript.json").exists()
