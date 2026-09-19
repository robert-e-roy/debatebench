"""ADR-037: a transcript and a score file record what shaped their output.

The tests that matter here assert a **difference**, not a presence. A field that
exists but never varies closes no confound, and the confound is the whole reason
for this ADR: two arms of a comparison separated on 2026-09-19 only by the
filenames someone had chosen.
"""

import asyncio
import json
from dataclasses import replace
from pathlib import Path

from debatebench import prompts
from debatebench.api import judge as api_judge
from debatebench.judging import write_scores
from debatebench.orchestrator import run_debate
from debatebench.retrieval import describe_sources
from debatebench.transcript import load_transcript, write_transcript
from fakes import FakeBackend, reply
from test_judging import debated, judge_reply, side
from test_orchestrator import configure, fakes
from test_prep import prep_debate

PHASES = ("opening:medium", "rebuttal:long", "conclusion:short")


def _judged(transcript, *, strict_json=True, thinking=True, fact_check=False):
    replies = [reply(judge_reply(side(0), side(1)), completion_tokens=400)]
    if fact_check:
        replies.append(reply(json.dumps({"claims": []}), completion_tokens=100))
    backend = FakeBackend(*replies)
    sheet = asyncio.run(
        api_judge(
            transcript,
            model="judge-model",
            budget=4000,
            backend=backend,
            fact_check=fact_check,
            strict_json=strict_json,
            thinking=thinking,
        )
    )
    return sheet, backend


# --- the confound this closes: two runs that differed, and now say so ---------


def test_two_runs_differing_only_in_thinking_are_distinguishable(run_dir: Path):
    """ADR-033 measured this turning 2,254 characters of reasoning into none."""
    config = configure(run_dir, PHASES)
    thinking_on = asyncio.run(run_debate(config, fakes()))
    off = replace(config, sides=tuple(replace(s, thinking=False) for s in config.sides))
    thinking_off = asyncio.run(run_debate(off, fakes()))

    assert [s.thinking for s in thinking_on.run.sides] == [True, True]
    assert [s.thinking for s in thinking_off.run.sides] == [False, False]
    # And it survives the round trip, which is where it has to be useful.
    for transcript, expected in ((thinking_on, True), (thinking_off, False)):
        path = run_dir / f"t-{expected}.json"
        write_transcript(transcript, path)
        assert all(s.thinking is expected for s in load_transcript(path).run.sides)


def test_two_judgings_differing_only_in_strict_json_are_distinguishable(run_dir: Path):
    """ADR-032 measured this taking parse failures from 5 of 9 to 0 of 9."""
    _, transcript = debated(run_dir)
    on, _ = _judged(transcript, strict_json=True)
    off, _ = _judged(transcript, strict_json=False)

    assert on.strict_json is True and off.strict_json is False
    path = run_dir / "scores.json"
    write_scores(off, path)
    assert json.loads(path.read_text())["strict_json"] is False


def test_two_judgings_differing_only_in_thinking_are_distinguishable(run_dir: Path):
    _, transcript = debated(run_dir)
    on, _ = _judged(transcript, thinking=True)
    off, _ = _judged(transcript, thinking=False)
    assert on.thinking is True and off.thinking is False


def test_a_changed_pool_changes_the_recorded_fingerprint(run_dir: Path, prepared_sources):
    """The pools are rebuildable and DEBATEBENCH_SOURCES_DIR can redirect them,
    so the name alone cannot say two runs read the same passages."""
    _, transcript, _ = prep_debate(run_dir)
    before = {s.name: s.fingerprint for s in transcript.run.sources}
    assert before, "a prep run must record the pool it read"

    pool = prepared_sources / "args-me.jsonl"
    rows = pool.read_text().splitlines()
    edited = json.loads(rows[0])
    edited["text"] = edited["text"] + " (edited)"
    pool.write_text("\n".join([json.dumps(edited), *rows[1:]]) + "\n")

    after = {s.name: s.fingerprint for s in describe_sources(["args-me"], [])}
    assert after["args-me"] != before["args-me"]


def test_a_run_without_prep_claims_no_corpus(run_dir: Path):
    # It read no pool, so it must not record one — absent, never an empty claim.
    _, transcript = debated(run_dir, PHASES)
    assert transcript.run.sources == ()
    path = run_dir / "t.json"
    write_transcript(transcript, path)
    assert "sources" not in json.loads(path.read_text())["run"]


# --- the record is enough to reconstruct what was sent ------------------------


def test_the_recorded_template_rebuilds_the_prompt_that_was_sent(run_dir: Path):
    """The strongest check available: fill the recorded template from the
    recorded snapshot and get back, byte for byte, the system prompt the model
    received. If that holds, the file is self-describing."""
    config = configure(run_dir, PHASES)
    transcript = asyncio.run(run_debate(config, fakes()))
    record = transcript.run.prompt
    assert record is not None

    for side_snapshot, live in zip(transcript.run.sides, config.sides):
        rebuilt = record.system.format(
            name=side_snapshot.team.name,
            stance=side_snapshot.team.stance,
            voice=side_snapshot.team.voice,
            values=", ".join(side_snapshot.team.values),
            topic=transcript.run.topic,
            position="for" if side_snapshot.side == "pro" else "against",
        )
        assert rebuilt == prompts.system_prompt(config.topic, live)


def test_the_recorded_instruction_is_the_one_a_turn_was_given(run_dir: Path):
    config = configure(run_dir, PHASES)
    backends = fakes()
    transcript = asyncio.run(run_debate(config, backends))
    recorded = dict(transcript.run.prompt.phases)

    for backend in backends:
        for request in backend.requests:
            user = request.messages[1].content
            assert any(user.endswith(instruction) for instruction in recorded.values()), user
    # Every label carries its resolved sentence count, which no config file states.
    assert "rebuttal:long" in recorded
    assert "about 10 sentences" in recorded["rebuttal:long"]
    assert "about 2 sentences" in recorded["conclusion:short"]


def test_the_recorded_judge_prompts_are_the_messages_the_backend_received(run_dir: Path):
    _, transcript = debated(run_dir)
    sheet, backend = _judged(transcript, fact_check=True)

    assert sheet.prompt.score_system == backend.requests[0].messages[0].content
    assert sheet.prompt.fact_check_system == backend.requests[1].messages[0].content


def test_without_the_audit_no_audit_prompt_is_claimed(run_dir: Path):
    _, transcript = debated(run_dir)
    sheet, _ = _judged(transcript, fact_check=False)
    assert sheet.prompt.fact_check_system is None
    path = run_dir / "scores.json"
    write_scores(sheet, path)
    assert "fact_check_system" not in json.loads(path.read_text())["prompt"]


# --- what the fingerprint is, and is not --------------------------------------


def test_the_fingerprint_ignores_everything_a_run_chose(run_dir: Path):
    """Different motion, different teams, same instructions — one fingerprint.
    That is what makes "were these given the same prompt?" answerable at a glance."""
    config = configure(run_dir, PHASES)
    first = prompts.prompt_record(config.topic, config.sides[0], config.phases, config.lengths)
    other = replace(
        config,
        topic="Something else entirely.",
        sides=tuple(
            replace(s, team=replace(s.team, name="Renamed", stance="different"))
            for s in config.sides
        ),
    )
    second = prompts.prompt_record(other.topic, other.sides[0], other.phases, other.lengths)
    assert first.fingerprint == second.fingerprint


def test_the_fingerprint_moves_when_an_instruction_changes(run_dir: Path, monkeypatch):
    config = configure(run_dir, PHASES)
    before = prompts.prompt_record(config.topic, config.sides[0], config.phases, config.lengths)

    edited = dict(prompts.PHASE_INSTRUCTIONS)
    edited["rebuttal"] = "Give your rebuttal, but differently."
    monkeypatch.setattr(prompts, "PHASE_INSTRUCTIONS", edited)
    after = prompts.prompt_record(config.topic, config.sides[0], config.phases, config.lengths)

    assert after.fingerprint != before.fingerprint


def test_the_fingerprint_moves_when_a_phase_length_changes(run_dir: Path):
    # `rebuttal:long` and `rebuttal:short` ask for different prompts, so they are
    # different instructions even though the phase name is the same.
    config = configure(run_dir, PHASES)
    long = prompts.prompt_record(config.topic, config.sides[0], config.phases, config.lengths)
    short = prompts.prompt_record(
        config.topic, config.sides[0], config.phases, ("medium", "short", "short")
    )
    assert long.fingerprint != short.fingerprint


def test_a_side_neutral_record(run_dir: Path):
    # Every value a side carries is a slot, so either side yields the same record.
    config = configure(run_dir, PHASES)
    pro = prompts.prompt_record(config.topic, config.sides[0], config.phases, config.lengths)
    con = prompts.prompt_record(config.topic, config.sides[1], config.phases, config.lengths)
    assert pro == con


# --- older files still read ---------------------------------------------------


def test_a_version_2_transcript_still_reads_and_says_nothing_it_does_not_know(run_dir: Path):
    config = configure(run_dir, PHASES)
    transcript = asyncio.run(run_debate(config, fakes()))
    path = run_dir / "t.json"
    write_transcript(transcript, path)

    document = json.loads(path.read_text())
    document["schema_version"] = 2
    del document["run"]["prompt"]
    for entry in document["run"]["sides"]:
        del entry["thinking"]
    path.write_text(json.dumps(document))

    reread = load_transcript(path)
    assert reread.schema_version == 2
    assert reread.run.prompt is None  # not recorded is not the same as recorded empty
    assert reread.run.sources == ()
    # ADR-033 made thinking opt-in, so True is what those runs actually sent.
    assert all(s.thinking is True for s in reread.run.sides)
