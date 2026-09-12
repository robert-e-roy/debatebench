"""B2's loop: the hard rules, turn order, budget enforcement and events."""

import asyncio
import time
from pathlib import Path

import pytest

from debatebench.backend import BackendError
from debatebench.config import load_run
from debatebench.events import EventBus, EventType
from debatebench.orchestrator import BUDGET_TOLERANCE, DebateError, run_debate
from fakes import FakeBackend, reply
from helpers import edit_yaml

PHASES = ("opening", "rebuttal", "conclusion")


def configure(run_dir: Path, phases=PHASES, *, budget=2000, swap_sides=False):
    """Load the fixture config with a chosen phase list. Prep is left out (B4)."""

    def mutate(data):
        data["format"]["phases"] = list(phases)
        for team in data["teams"]:
            team["budget"] = budget
            if "prep" not in phases:
                team.pop("prep_budget", None)
        if swap_sides:
            data["teams"][0]["side"], data["teams"][1]["side"] = "con", "pro"

    edit_yaml(run_dir / "run.yaml", mutate)
    return load_run(run_dir / "run.yaml")


def fakes():
    return [FakeBackend(auto="pro"), FakeBackend(auto="con")]


def debate(config, backends, events=None):
    return asyncio.run(run_debate(config, backends, events))


# --- the loop ---------------------------------------------------------------


def test_every_phase_gets_a_turn_from_every_side(run_dir: Path):
    config = configure(run_dir)
    transcript = debate(config, fakes())

    assert [(t.phase_index, t.phase, t.side_index) for t in transcript.turns] == [
        (0, "opening", 0), (0, "opening", 1),
        (1, "rebuttal", 1), (1, "rebuttal", 0),
        (2, "conclusion", 0), (2, "conclusion", 1),
    ]


def test_repeated_phase_names_do_not_overwrite_each_other(run_dir: Path):
    # Hard Rule 2: keyed by (phase_index, side_index), so a repeated name can't collide.
    config = configure(run_dir, ("rebuttal", "rebuttal"))
    transcript = debate(config, fakes())

    assert len(transcript.turns) == 4
    assert len({(t.phase_index, t.side_index) for t in transcript.turns}) == 4
    assert transcript.turn(0, 0).text != transcript.turn(1, 0).text


def test_the_phase_list_is_followed_exactly(run_dir: Path):
    # Hard Rule 6: phases are data. The same loop, two different lists.
    short = debate(configure(run_dir, ("opening",)), fakes())
    long = debate(configure(run_dir, ("opening", "retort", "retort", "conclusion")), fakes())

    assert [t.phase for t in short.turns] == ["opening"] * 2
    assert [t.phase for t in long.turns] == [
        "opening", "opening", "retort", "retort", "retort", "retort", "conclusion", "conclusion",
    ]


def test_pro_opens_and_initiative_alternates(run_dir: Path):
    config = configure(run_dir, ("opening", "rebuttal", "retort"))
    transcript = debate(config, fakes())

    assert [t.side_index for t in transcript.turns] == [0, 1, 1, 0, 0, 1]
    assert [t.order for t in transcript.turns] == [0, 1, 0, 1, 0, 1]


def test_pro_opens_even_when_listed_second(run_dir: Path):
    config = configure(run_dir, ("opening", "rebuttal"), swap_sides=True)
    transcript = debate(config, fakes())

    first_speaker = transcript.turns[0]
    assert config.sides[first_speaker.side_index].side == "pro"
    assert first_speaker.side_index == 1  # listed second, still opens


def test_prep_needs_its_sources_prepared_before_any_model_call(run_dir: Path, monkeypatch):
    # Datasets are a one-time manual step, so a missing one is a named error (ADR-012 §5).
    monkeypatch.setenv("DEBATEBENCH_SOURCES_DIR", str(run_dir / "not-prepared"))
    config = configure(run_dir, ("prep", "opening"))
    backends = fakes()
    with pytest.raises(DebateError, match="source 'args-me' is not prepared"):
        debate(config, backends)
    assert all(not backend.requests for backend in backends)


# --- Hard Rule 1: no silent failure -----------------------------------------


def test_a_failed_turn_aborts_the_run(run_dir: Path):
    config = configure(run_dir)
    backends = [FakeBackend(auto="pro"), FakeBackend(reply(), BackendError("HTTP 500: boom"))]

    transcript = "not assigned"
    with pytest.raises(DebateError, match=r"phase 1 \(rebuttal\), side 1 \(con, .*\): HTTP 500: boom"):
        transcript = debate(config, backends)

    # The three turns that did succeed must not escape as a partial transcript.
    # (They were announced as events while they happened — that feed is live by
    # design; the transcript is the thing that must be all or nothing.)
    assert transcript == "not assigned"


def test_an_empty_reply_aborts_the_run(run_dir: Path):
    config = configure(run_dir)
    backends = [FakeBackend(reply("   ")), FakeBackend(auto="con")]

    with pytest.raises(DebateError, match="the model returned no text"):
        debate(config, backends)


# --- Hard Rule 5: the orchestrator enforces budgets -------------------------


def test_a_reply_over_the_tolerance_aborts_the_run(run_dir: Path):
    config = configure(run_dir, budget=100)
    over = reply(completion_tokens=100 + BUDGET_TOLERANCE + 1)
    backends = [FakeBackend(over), FakeBackend(auto="con")]

    with pytest.raises(DebateError, match=r"117 completion tokens for a budget of 100"):
        debate(config, backends)


def test_a_reply_within_the_tolerance_is_kept_and_flagged(run_dir: Path):
    config = configure(run_dir, ("opening",), budget=100)
    backends = [FakeBackend(reply(completion_tokens=100 + BUDGET_TOLERANCE)), FakeBackend(auto="con")]

    transcript = debate(config, backends)
    assert transcript.turn(0, 0).hit_budget is True
    assert transcript.turn(0, 1).hit_budget is False  # 4 tokens of 100


# --- Hard Rule 4: nothing blocks the event loop -----------------------------


def _longest_pause(config, backends, interval=0.005):
    """The longest gap between heartbeats while a debate runs."""

    async def go():
        gaps = []

        async def heartbeat():
            last = time.monotonic()
            while True:
                await asyncio.sleep(interval)
                now = time.monotonic()
                gaps.append(now - last)
                last = now

        ticker = asyncio.create_task(heartbeat())
        try:
            await run_debate(config, backends)
        finally:
            ticker.cancel()
        # No tick at all means the loop never got control back: the worst case.
        return max(gaps, default=float("inf"))

    return asyncio.run(go())


def test_turns_do_not_block_the_event_loop(run_dir: Path):
    config = configure(run_dir, ("opening",))
    backends = [FakeBackend(auto="pro", delay=0.05), FakeBackend(auto="con", delay=0.05)]
    assert _longest_pause(config, backends) < 0.03


def test_the_heartbeat_catches_a_blocking_backend(run_dir: Path):
    # The check above is only worth having if a blocking call makes it fail.
    config = configure(run_dir, ("opening",))
    backends = [FakeBackend(auto="pro", delay=0.05, blocking=True), FakeBackend(auto="con")]
    assert _longest_pause(config, backends) >= 0.04


# --- events -----------------------------------------------------------------


def test_events_describe_the_run(run_dir: Path):
    config = configure(run_dir, ("opening",))
    seen = []
    events = EventBus()
    events.subscribe(seen.append)

    debate(config, fakes(), events)

    assert [e.type for e in seen] == [
        EventType.RUN_STARTED,
        EventType.PHASE_STARTED,
        EventType.TURN_STARTED, EventType.TURN_COMPLETED,
        EventType.TURN_STARTED, EventType.TURN_COMPLETED,
        EventType.PHASE_COMPLETED,
        EventType.RUN_COMPLETED,
    ]
    assert seen[3].turn is not None and seen[3].turn.side_index == 0


def test_a_failure_emits_run_failed(run_dir: Path):
    config = configure(run_dir, ("opening",))
    seen = []
    events = EventBus()
    events.subscribe(seen.append)

    with pytest.raises(DebateError):
        debate(config, [FakeBackend(BackendError("boom")), FakeBackend(auto="con")], events)

    assert seen[-1].type is EventType.RUN_FAILED and "boom" in seen[-1].error


def test_a_broken_listener_does_not_stop_the_run(run_dir: Path, capfd):
    config = configure(run_dir, ("opening",))
    events = EventBus()
    seen = []

    def broken(event):
        raise RuntimeError("listener bug")

    events.subscribe(broken)
    events.subscribe(seen.append)

    transcript = debate(config, fakes(), events)

    assert len(transcript.turns) == 2 and seen  # the other listener still ran
    assert "event listener broken failed" in capfd.readouterr().err  # and it wasn't silent


# --- the transcript ---------------------------------------------------------


def test_transcript_snapshots_the_run(run_dir: Path):
    config = configure(run_dir, ("opening",))
    transcript = debate(config, fakes())

    assert transcript.schema_version == 2  # 2 since ADR-016 added per-turn length
    assert transcript.run.topic == config.topic
    assert transcript.run.seed == 42
    assert transcript.run.budget_tolerance == BUDGET_TOLERANCE
    assert transcript.run.phases == ("opening",)
    first = transcript.run.sides[0]
    assert first.team_file == "teams/liberal.yaml"  # as written, not an absolute path
    assert first.team.name == "Progressive Climate Advocate"
    assert first.team.values == ("collective-action", "precaution", "equity")
    assert (first.side, first.model) == ("pro", "qwen3-8b")
    assert transcript.started_at.endswith("Z") and transcript.finished_at.endswith("Z")


def test_credentials_in_a_base_url_are_not_recorded(run_dir: Path):
    def add_credentials(data):
        data["format"]["phases"] = ["opening"]
        for team in data["teams"]:
            team.pop("prep_budget", None)
        data["teams"][0]["base_url"] = "http://user:secret@127.0.0.1:8080/v1"

    edit_yaml(run_dir / "run.yaml", add_credentials)
    transcript = debate(load_run(run_dir / "run.yaml"), fakes())

    assert transcript.run.sides[0].base_url == "http://127.0.0.1:8080/v1"
