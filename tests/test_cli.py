"""The ``debate`` command: one argument, stderr only, nothing written to output:."""

import socket
import subprocess
import sys
from pathlib import Path

import pytest

from debatebench.cli import _OverrideError, _overridden, _parser, main
from debatebench.config import load_run
from debatebench.transcript import snapshot
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


def test_output_is_still_not_a_flag(run_dir: Path):
    # ADR-021 added override flags but deliberately not this one: Hard Rule 7
    # names the absence of --output as part of its content (ADR-021 §6).
    with pytest.raises(SystemExit) as e:
        main([str(run_dir / "run.yaml"), "--output", "x.json"])
    assert e.value.code == 2


def test_seed_is_still_not_a_flag(run_dir: Path):
    # ADR-021 §6: a seed sweep already works by omitting seed: from the file.
    with pytest.raises(SystemExit) as e:
        main([str(run_dir / "run.yaml"), "--seed", "7"])
    assert e.value.code == 2


# --- ADR-021: override flags -------------------------------------------------


def _overrides(run_dir: Path, *flags: str):
    """Through debate's own parser, so these tests pin the real flag names."""
    args = _parser().parse_args([str(run_dir / "run.yaml"), *flags])
    return _overridden(load_run(run_dir / "run.yaml"), args)


def test_a_symmetric_model_override_moves_both_sides(run_dir: Path):
    config, changed = _overrides(run_dir, "--model", "phi4-mini:latest")
    assert [side.model for side in config.sides] == ["phi4-mini:latest"] * 2
    assert len(changed) == 2


def test_a_per_side_override_moves_only_that_side(run_dir: Path):
    before = load_run(run_dir / "run.yaml")
    config, changed = _overrides(run_dir, "--con-model", "phi4-mini:latest")

    pro, con = config.sides
    assert con.model == "phi4-mini:latest"
    assert pro.model == before.sides[0].model  # untouched
    assert len(changed) == 1 and "--con-model" in changed[0]


def test_budget_overrides_independently_of_model(run_dir: Path):
    config, _ = _overrides(run_dir, "--model", "m", "--con-budget", "4000")
    pro, con = config.sides
    assert (pro.model, con.model) == ("m", "m")
    assert con.budget == 4000 and pro.budget == load_run(run_dir / "run.yaml").sides[0].budget


def test_both_forms_of_one_setting_conflict(run_dir: Path):
    # ADR-021 §4: no precedence, because either would discard something asked for.
    with pytest.raises(_OverrideError) as e:
        _overrides(run_dir, "--model", "a", "--pro-model", "b")
    assert "--model" in str(e.value) and "--pro-model" in str(e.value)


def test_an_override_faces_the_same_validation_and_names_the_flag(run_dir: Path):
    # ADR-021 §5, and the message must point at the flag, not the file's key.
    with pytest.raises(_OverrideError) as e:
        _overrides(run_dir, "--budget", "0")
    assert "--budget" in str(e.value) and "run.yaml" not in str(e.value)


def test_an_override_reaches_the_transcript_snapshot(run_dir: Path):
    # ADR-021 §5 is the whole point: a snapshot naming the file's model would be
    # a record of what did not run.
    config, _ = _overrides(run_dir, "--pro-model", "phi4-mini:latest")
    recorded = snapshot(config, budget_tolerance=16)
    assert recorded.sides[0].model == "phi4-mini:latest"
    assert recorded.sides[1].model == config.sides[1].model


def test_no_flags_changes_nothing(run_dir: Path):
    before = load_run(run_dir / "run.yaml")
    config, changed = _overrides(run_dir)
    assert changed == ()
    assert [s.model for s in config.sides] == [s.model for s in before.sides]
    assert [s.budget for s in config.sides] == [s.budget for s in before.sides]


def test_config_error_goes_to_stderr(run_dir: Path, capfd):
    edit_yaml(run_dir / "run.yaml", lambda d: d.pop("output"))
    assert main([str(run_dir / "run.yaml")]) == 1
    out, err = capfd.readouterr()
    assert out == ""
    assert "debate: config error:" in err and "output is required" in err


def test_unprepared_sources_are_reported_on_stderr(run_dir: Path, capfd, monkeypatch):
    monkeypatch.setenv("DEBATEBENCH_SOURCES_DIR", str(run_dir / "not-prepared"))
    configure(run_dir, ("prep", "opening"))
    assert main([str(run_dir / "run.yaml")]) == 1
    out, err = capfd.readouterr()
    assert out == ""
    assert "debate: debate failed:" in err and "is not prepared" in err


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
