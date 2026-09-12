"""B3: writing the transcript, and rotating whatever was already there (ADR-005)."""

import asyncio
import json
from pathlib import Path

from debatebench.config import load_run
from debatebench.orchestrator import run_debate
from debatebench.transcript import write_transcript
from fakes import FakeBackend, reply
from test_orchestrator import configure, fakes


def transcript_for(run_dir: Path, phases=("opening",), backends=None):
    config = configure(run_dir, phases)
    return config, asyncio.run(run_debate(config, backends or fakes()))


def test_written_file_is_the_adr_005_document(run_dir: Path):
    config, transcript = transcript_for(run_dir, ("opening", "rebuttal"))

    assert write_transcript(transcript, config.output) is None  # nothing to rotate
    document = json.loads(config.output.read_text(encoding="utf-8"))

    assert document["schema_version"] == 1
    assert document["debatebench_version"]
    assert document["started_at"].endswith("Z") and document["finished_at"].endswith("Z")
    assert document["run"]["topic"] == config.topic
    assert document["run"]["seed"] == 42
    assert document["run"]["budget_tolerance"] == 16
    assert document["run"]["phases"] == ["opening", "rebuttal"]
    assert document["run"]["sides"][0]["team_file"] == "teams/liberal.yaml"
    assert document["run"]["sides"][0]["team"]["values"] == [
        "collective-action", "precaution", "equity",
    ]

    turns = document["turns"]
    assert len(turns) == 4
    assert {(t["phase_index"], t["side_index"]) for t in turns} == {(0, 0), (0, 1), (1, 0), (1, 1)}
    first = turns[0]
    assert first["usage"] == {"prompt_tokens": 40, "completion_tokens": 4}
    assert first["budget"] == 2000 and first["hit_budget"] is False
    assert first["finish_reason"] == "stop" and first["phase"] == "opening"


def test_the_file_holds_nothing_but_json(run_dir: Path, capfd):
    # Hard Rule 7: logging never reaches the output file.
    config, transcript = transcript_for(run_dir)
    write_transcript(transcript, config.output)

    text = config.output.read_text(encoding="utf-8")
    assert text.lstrip().startswith("{") and text.rstrip().endswith("}")
    json.loads(text)
    assert capfd.readouterr().out == ""


def test_non_ascii_text_is_kept_as_written(run_dir: Path):
    config, transcript = transcript_for(
        run_dir, backends=[FakeBackend(reply("Café — naïve «quotes»")), FakeBackend(auto="con")]
    )
    write_transcript(transcript, config.output)

    assert "Café — naïve «quotes»" in config.output.read_text(encoding="utf-8")


def test_an_existing_transcript_is_rotated(run_dir: Path):
    config, first = transcript_for(run_dir)
    write_transcript(first, config.output)
    original = config.output.read_text(encoding="utf-8")

    _, second = transcript_for(run_dir, backends=[FakeBackend(reply("a later run")), FakeBackend(auto="con")])
    backup = write_transcript(second, config.output)

    assert backup == config.output.with_name("transcript.json.1")
    assert backup.read_text(encoding="utf-8") == original  # the old run, untouched
    assert "a later run" in config.output.read_text(encoding="utf-8")  # the new one


def test_only_one_generation_is_kept(run_dir: Path):
    config, transcript = transcript_for(run_dir)
    for _ in range(3):
        write_transcript(transcript, config.output)

    assert config.output.with_name("transcript.json.1").exists()
    assert not config.output.with_name("transcript.json.2").exists()
    assert not config.output.with_name("transcript.json.1.1").exists()


def test_no_temporary_files_are_left_behind(run_dir: Path):
    config, transcript = transcript_for(run_dir)
    write_transcript(transcript, config.output)

    assert [p.name for p in run_dir.iterdir() if p.name.endswith(".tmp")] == []


def test_a_failed_run_leaves_an_existing_transcript_alone(run_dir: Path, capfd):
    # The CLI writes only after a complete run, so a failure can't rotate anything.
    from debatebench.cli import main
    from helpers import edit_yaml

    config, transcript = transcript_for(run_dir)
    write_transcript(transcript, config.output)
    before = config.output.read_text(encoding="utf-8")

    def point_at_nothing(data):
        data["format"]["phases"] = ["opening"]
        for side in data["teams"]:
            side["base_url"] = "http://127.0.0.1:9/v1"  # discard port: nothing listens
            side.pop("prep_budget", None)

    edit_yaml(run_dir / "run.yaml", point_at_nothing)
    assert main([str(run_dir / "run.yaml")]) == 1

    assert config.output.read_text(encoding="utf-8") == before
    assert not config.output.with_name("transcript.json.1").exists()


def test_a_missing_output_directory_is_caught_before_the_debate(run_dir: Path, capfd):
    from debatebench.cli import main
    from helpers import edit_yaml

    def into_a_missing_directory(data):
        data["format"]["phases"] = ["opening"]
        data["output"] = "nowhere/transcript.json"
        for side in data["teams"]:
            side.pop("prep_budget", None)

    edit_yaml(run_dir / "run.yaml", into_a_missing_directory)
    assert main([str(run_dir / "run.yaml")]) == 1
    assert "output directory does not exist" in capfd.readouterr().err


def test_the_run_seed_goes_to_the_backend(run_dir: Path):
    config = configure(run_dir, ("opening",))
    backends = fakes()
    asyncio.run(run_debate(config, backends))

    assert all(backend.requests[0].seed == config.seed == 42 for backend in backends)


def test_load_run_is_reusable_for_judge(run_dir: Path):
    # The written document is the only interface judge will have (ADR-005).
    config, transcript = transcript_for(run_dir)
    write_transcript(transcript, config.output)
    document = json.loads(config.output.read_text(encoding="utf-8"))

    assert load_run(run_dir / "run.yaml").topic == document["run"]["topic"]
