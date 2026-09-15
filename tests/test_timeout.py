"""ADR-025: the read timeout is a setting, not a constant."""

from pathlib import Path

import pytest

from debatebench.backend import DEFAULT_READ_TIMEOUT
from debatebench.config import ConfigError, load_run
from helpers import edit_yaml
from test_orchestrator import configure


def test_an_absent_timeout_keeps_the_old_constant(run_dir: Path):
    # 600 was hardcoded before ADR-025; nothing existing may start behaving
    # differently just because the key now exists.
    config = configure(run_dir, ("opening",))
    assert config.timeout == DEFAULT_READ_TIMEOUT == 600


def test_a_run_yaml_timeout_is_read(run_dir: Path):
    edit_yaml(run_dir / "run.yaml", lambda d: d.__setitem__("timeout", 1800))
    assert load_run(run_dir / "run.yaml").timeout == 1800


def test_the_judge_block_carries_its_own(run_dir: Path):
    def mutate(data):
        data["timeout"] = 900
        data["judge"] = {"model": "m", "base_url": "http://127.0.0.1:1/v1",
                         "budget": 10, "output": "s.json", "timeout": 1800}

    edit_yaml(run_dir / "run.yaml", mutate)
    config = load_run(run_dir / "run.yaml")
    # The debate's timeout and the judge's are independent settings (ADR-025 §1).
    assert (config.timeout, config.judge.timeout) == (900, 1800)


def test_a_judge_block_without_one_falls_back(run_dir: Path):
    def mutate(data):
        data["timeout"] = 900  # the run's, which must NOT leak into the judge's
        data["judge"] = {"model": "m", "base_url": "http://127.0.0.1:1/v1",
                         "budget": 10, "output": "s.json"}

    edit_yaml(run_dir / "run.yaml", mutate)
    assert load_run(run_dir / "run.yaml").judge.timeout == DEFAULT_READ_TIMEOUT


@pytest.mark.parametrize("value", [0, -1])
def test_a_non_positive_timeout_is_rejected(run_dir: Path, value):
    edit_yaml(run_dir / "run.yaml", lambda d: d.__setitem__("timeout", value))
    with pytest.raises(ConfigError, match="timeout"):
        load_run(run_dir / "run.yaml")


def test_the_transcript_does_not_record_it(run_dir: Path):
    """ADR-025 §6: the snapshot records what shaped the output. This didn't."""
    import asyncio

    from debatebench.orchestrator import run_debate
    from debatebench.transcript import as_json_dict
    from test_orchestrator import fakes

    config = configure(run_dir, ("opening",))  # no prep, so no dataset is needed
    edit_yaml(run_dir / "run.yaml", lambda d: d.__setitem__("timeout", 1800))
    config = load_run(run_dir / "run.yaml")
    assert config.timeout == 1800
    transcript = asyncio.run(run_debate(config, fakes()))

    assert "timeout" not in as_json_dict(transcript)["run"]
