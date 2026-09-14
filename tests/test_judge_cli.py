"""The ``judge`` command: flags, failure modes, and a score file with nothing else in it."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from debatebench import judge_cli
from debatebench.judge_cli import main
from debatebench.transcript import write_transcript
from fakes import FakeBackend, reply
from helpers import edit_yaml
from test_fact_check import claim, claims_reply
from test_judging import debated, judge_reply, side


@pytest.fixture
def transcript_file(run_dir: Path) -> Path:
    config, transcript = debated(run_dir)
    write_transcript(transcript, config.output)
    return config.output


@pytest.fixture
def fake_judge(monkeypatch):
    """Answer the one scoring call without a server."""

    def install(*texts: str) -> list[FakeBackend]:
        """One backend answers both calls, so script the scoring reply then the audit."""
        made: list[FakeBackend] = []

        def build(client, base_url, model):
            made.append(FakeBackend(*[reply(t, completion_tokens=400) for t in texts]))
            return made[-1]

        monkeypatch.setattr(judge_cli, "OpenAICompatibleBackend", build)
        return made

    return install


def run(transcript: Path, output: Path, *extra: str, fact_check: bool = False) -> int:
    # Most of these tests are about scoring, so they skip the second call (ADR-015 §3).
    return main([
        str(transcript), "--model", "judge-model", "--base-url", "http://127.0.0.1:9/v1",
        "--budget", "4000", "--output", str(output),
        "--fact-check" if fact_check else "--no-fact-check", *extra,
    ])


# --- the flags ADR-007 and ADR-017 fix ---------------------------------------


def test_no_argument_is_a_usage_error():
    with pytest.raises(SystemExit) as e:
        main([])
    assert e.value.code == 2


def test_console_script_is_installed():
    script = Path(sys.executable).parent / "judge"
    result = subprocess.run([str(script)], capture_output=True, text=True)
    assert result.returncode == 2
    assert "usage: judge" in result.stderr and result.stdout == ""


REQUIRED = ["--model", "--base-url", "--budget", "--output"]


@pytest.mark.parametrize("missing", REQUIRED)
def test_every_required_flag_is_required(transcript_file: Path, tmp_path: Path, missing: str, capfd):
    argv = [str(transcript_file), "--model", "m", "--base-url", "http://x/v1",
            "--budget", "100", "--output", str(tmp_path / "s.json")]
    index = argv.index(missing)
    # ADR-020 §4 moved requiredness out of argparse so one parser serves both
    # forms, so this is exit 1 with a message rather than argparse's exit 2 —
    # and the message has to name the flag and the other way to supply it.
    assert main(argv[:index] + argv[index + 2:]) == 1
    err = capfd.readouterr().err
    assert missing in err and "run.yaml" in err


def test_base_url_has_no_default(transcript_file: Path, tmp_path: Path, capfd):
    # ADR-017 §2: a hidden default would hide which server produced a score.
    # ADR-020 kept that true; only the exit path changed.
    assert main([str(transcript_file), "--model", "m", "--budget", "100",
                 "--output", str(tmp_path / "s.json")]) == 1
    assert "--base-url" in capfd.readouterr().err


# --- ADR-020: the judge: block in run.yaml -----------------------------------


def _with_judge_block(run_dir: Path, **overrides) -> Path:
    """Give the fixture run.yaml a judge: block, and hand back its path."""
    block = {
        "model": "block-model",
        "base_url": "http://127.0.0.1:9/v1",
        "budget": 4000,
        "output": "scores.json",
        "fact_check": False,
        **overrides,
    }
    return edit_yaml(run_dir / "run.yaml", lambda data: data.__setitem__("judge", block))


def test_judge_reads_the_block_and_finds_the_transcript_itself(
    transcript_file: Path, run_dir: Path, fake_judge
):
    # ADR-020 §3: one word, and the transcript comes from the run's own output:.
    made = fake_judge(judge_reply(side(0), side(1)))
    run_yaml = _with_judge_block(run_dir)

    assert main([str(run_yaml)]) == 0

    document = json.loads((run_dir / "scores.json").read_text())
    assert document["judge_model"] == "block-model"
    assert document["judge_budget"] == 4000
    assert document["fact_check_enabled"] is False
    assert len(made[0].requests) == 1


def test_a_flag_overrides_the_block(transcript_file: Path, run_dir: Path, fake_judge):
    # ADR-020 §4: a one-off change needs no edit to the file.
    fake_judge(judge_reply(side(0), side(1)))
    run_yaml = _with_judge_block(run_dir)

    assert main([str(run_yaml), "--model", "flag-model"]) == 0

    document = json.loads((run_dir / "scores.json").read_text())
    assert document["judge_model"] == "flag-model"  # the flag, not the block
    assert document["judge_budget"] == 4000  # untouched settings still come from the file


def test_fact_check_flag_overrides_the_block(transcript_file: Path, run_dir: Path, fake_judge):
    fake_judge(judge_reply(side(0), side(1)), claims_reply(claim(verdict="unsupported")))
    run_yaml = _with_judge_block(run_dir)  # fact_check: false in the file

    assert main([str(run_yaml), "--fact-check"]) == 0

    assert json.loads((run_dir / "scores.json").read_text())["fact_check_enabled"] is True


def test_a_run_yaml_without_a_judge_block_says_what_to_do(run_dir: Path, capfd):
    assert main([str(run_dir / "run.yaml")]) == 1
    err = capfd.readouterr().err
    assert "no judge: block" in err and "--model" in err


def test_a_broken_run_yaml_reports_a_config_error(run_dir: Path, capfd):
    edit_yaml(run_dir / "run.yaml", lambda data: data.__setitem__("seeed", 42))
    assert main([str(run_dir / "run.yaml")]) == 1
    assert "config error" in capfd.readouterr().err


def test_the_fact_check_runs_by_default(transcript_file: Path, run_dir: Path, fake_judge, capfd):
    # ADR-015 §1: on by default, as a second call after scoring.
    made = fake_judge(judge_reply(side(0), side(1)), claims_reply(claim(verdict="unsupported")))
    output = run_dir / "score.json"

    assert main([
        str(transcript_file), "--model", "judge-model", "--base-url", "http://127.0.0.1:9/v1",
        "--budget", "4000", "--output", str(output),
    ]) == 0

    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["fact_check_enabled"] is True
    assert document["fact_check"]["checked_against"] == "recorded_evidence"
    assert len(made[0].requests) == 2  # scoring, then the audit
    assert "fact-check: 1 claims" in capfd.readouterr().err


def test_no_fact_check_skips_the_second_call(
    transcript_file: Path, run_dir: Path, fake_judge, capfd
):
    made = fake_judge(judge_reply(side(0), side(1)))
    assert run(transcript_file, run_dir / "score.json") == 0

    document = json.loads((run_dir / "score.json").read_text())
    assert document["fact_check_enabled"] is False
    assert "fact_check" not in document  # absent, not an empty section (ADR-015 §4)
    assert len(made[0].requests) == 1


def test_a_budget_below_one_is_rejected(transcript_file: Path, run_dir: Path, capfd):
    assert main([str(transcript_file), "--model", "m", "--base-url", "http://x/v1",
                 "--budget", "0", "--output", str(run_dir / "score.json")]) == 1
    assert "--budget must be at least 1" in capfd.readouterr().err


# --- reading the transcript --------------------------------------------------


def test_a_missing_transcript_is_reported(run_dir: Path, capfd):
    assert run(run_dir / "nothing.json", run_dir / "score.json") == 1
    out, err = capfd.readouterr()
    assert "transcript error:" in err and "cannot be read" in err and out == ""


def test_a_transcript_from_a_newer_build_is_refused(transcript_file: Path, run_dir: Path, capfd):
    document = json.loads(transcript_file.read_text())
    document["schema_version"] = 3  # 1 and 2 are both readable (ADR-016 §6)
    transcript_file.write_text(json.dumps(document))

    assert run(transcript_file, run_dir / "score.json") == 1
    assert "schema_version is 3, and this build reads 1, 2" in capfd.readouterr().err


def test_a_transcript_that_is_not_json_is_refused(transcript_file: Path, run_dir: Path, capfd):
    transcript_file.write_text("just some text")
    assert run(transcript_file, run_dir / "score.json") == 1
    assert "not valid JSON" in capfd.readouterr().err


def test_a_missing_output_directory_is_caught_before_the_call(
    transcript_file: Path, run_dir: Path, fake_judge, capfd
):
    made = fake_judge(judge_reply(side(0), side(1)))
    assert run(transcript_file, run_dir / "nowhere" / "score.json") == 1
    assert "output directory does not exist" in capfd.readouterr().err
    assert not made  # the model was never called


# --- a complete run ----------------------------------------------------------


def test_it_writes_the_score_file_and_explains_itself(
    transcript_file: Path, run_dir: Path, fake_judge, capfd
):
    fake_judge(judge_reply(side(0), side(1, argument_quality=10)))
    output = run_dir / "score.json"

    assert run(transcript_file, output) == 0
    out, err = capfd.readouterr()

    assert out == ""  # the file is the output; everything else is stderr
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["winner"] == "pro"
    # The diagnostic value is the point: every dimension is reported, not just the total.
    assert "side 0 (pro): 76 of 100" in err
    assert "argument_quality: 24 of 30" in err
    assert "pro wins (total)" in err


def test_a_draw_is_reported_as_a_draw(transcript_file: Path, run_dir: Path, fake_judge, capfd):
    fake_judge(judge_reply(side(0), side(1)))
    assert run(transcript_file, run_dir / "score.json") == 0
    assert "a draw (tied after steelman tiebreak)" in capfd.readouterr().err


def test_the_score_file_holds_nothing_but_json(
    transcript_file: Path, run_dir: Path, fake_judge, capfd
):
    fake_judge(judge_reply(side(0), side(1)))
    output = run_dir / "score.json"
    run(transcript_file, output)

    text = output.read_text(encoding="utf-8")
    assert text.lstrip().startswith("{") and text.rstrip().endswith("}")
    json.loads(text)


def test_a_failed_judging_run_writes_nothing(
    transcript_file: Path, run_dir: Path, fake_judge, capfd
):
    fake_judge("I think side 0 won, roughly.")
    output = run_dir / "score.json"

    assert run(transcript_file, output) == 1
    assert "judging failed:" in capfd.readouterr().err
    assert not output.exists()


def test_a_rotated_score_file_is_reported(transcript_file: Path, run_dir: Path, fake_judge, capfd):
    output = run_dir / "score.json"
    fake_judge(judge_reply(side(0), side(1)))
    run(transcript_file, output)
    fake_judge(judge_reply(side(0), side(1, clarity=2)))
    run(transcript_file, output)

    assert "moved the previous score file to score.json.1" in capfd.readouterr().err
    assert output.with_name("score.json.1").exists()
