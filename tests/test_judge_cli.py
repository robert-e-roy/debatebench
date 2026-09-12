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
from test_judging import debated, judge_reply, side


@pytest.fixture
def transcript_file(run_dir: Path) -> Path:
    config, transcript = debated(run_dir)
    write_transcript(transcript, config.output)
    return config.output


@pytest.fixture
def fake_judge(monkeypatch):
    """Answer the one scoring call without a server."""

    def install(text: str) -> list[FakeBackend]:
        made: list[FakeBackend] = []

        def build(client, base_url, model):
            made.append(FakeBackend(reply(text, completion_tokens=400)))
            return made[-1]

        monkeypatch.setattr(judge_cli, "OpenAICompatibleBackend", build)
        return made

    return install


def run(transcript: Path, output: Path, *extra: str) -> int:
    return main([
        str(transcript), "--model", "judge-model", "--base-url", "http://127.0.0.1:9/v1",
        "--budget", "4000", "--output", str(output), *extra,
    ])


# --- the flags ADR-007 and ADR-015 fix ---------------------------------------


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
def test_every_required_flag_is_required(transcript_file: Path, tmp_path: Path, missing: str):
    argv = [str(transcript_file), "--model", "m", "--base-url", "http://x/v1",
            "--budget", "100", "--output", str(tmp_path / "s.json")]
    index = argv.index(missing)
    with pytest.raises(SystemExit) as e:
        main(argv[:index] + argv[index + 2:])
    assert e.value.code == 2


def test_base_url_has_no_default(transcript_file: Path, tmp_path: Path, capfd):
    # ADR-015 §2: a hidden default would hide which server produced a score.
    with pytest.raises(SystemExit):
        main([str(transcript_file), "--model", "m", "--budget", "100",
              "--output", str(tmp_path / "s.json")])
    assert "--base-url" in capfd.readouterr().err


def test_asking_for_a_fact_check_is_an_error(transcript_file: Path, run_dir: Path, capfd):
    # ADR-015 §1: nothing can fact-check until B6, so it says so instead of pretending.
    assert run(transcript_file, run_dir / "score.json", "--fact-check") == 1
    out, err = capfd.readouterr()
    assert "fact-checking arrives in B6" in err and out == ""
    assert not (run_dir / "score.json").exists()


def test_no_fact_check_is_accepted(transcript_file: Path, run_dir: Path, fake_judge, capfd):
    fake_judge(judge_reply(side(0), side(1)))
    assert run(transcript_file, run_dir / "score.json", "--no-fact-check") == 0
    assert json.loads((run_dir / "score.json").read_text())["fact_check_enabled"] is False


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
    document["schema_version"] = 2
    transcript_file.write_text(json.dumps(document))

    assert run(transcript_file, run_dir / "score.json") == 1
    assert "schema_version is 2, and this build reads 1" in capfd.readouterr().err


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
