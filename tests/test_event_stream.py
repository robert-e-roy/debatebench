"""ADR-027: `debate --events` streams JSONL on stdout, as a contract for other programs.

These tests are the contract. A second project depends on these line shapes, so a
change that breaks them should break a test here rather than that project.
"""

import asyncio
import io
import json
from pathlib import Path

from debatebench.cli import _parser
from debatebench.event_stream import SCHEMA_VERSION, make_event_writer, run_line
from debatebench.events import DebateEvent, EventBus, EventType
from debatebench.orchestrator import run_debate
from test_orchestrator import configure, fakes


def streamed(run_dir: Path, phases=("opening", "rebuttal")) -> tuple[list[dict], io.StringIO]:
    """Run a debate with the writer attached, and return the parsed lines."""
    config = configure(run_dir, phases)
    out = io.StringIO()
    events = EventBus()
    events.subscribe(make_event_writer(config, out))
    asyncio.run(run_debate(config, fakes(), events))
    return [json.loads(line) for line in out.getvalue().splitlines()], out


# --- the flag ----------------------------------------------------------------


def test_the_flag_exists_and_is_off_by_default():
    args = _parser().parse_args(["run.yaml"])
    assert args.events is False


# --- the run header (ADR-027 §3-§4) ------------------------------------------


def test_the_first_line_describes_the_run(run_dir: Path):
    lines, _ = streamed(run_dir)
    head = lines[0]

    assert head["event"] == "run"
    assert head["schema_version"] == SCHEMA_VERSION
    assert head["phases"] == ["opening", "rebuttal"]
    assert head["seed"] == 42
    assert "topic" in head


def test_the_header_names_each_side_before_any_turn_arrives(run_dir: Path):
    # RUN_STARTED carries no payload, so without this a viewer cannot render a
    # heading until the first turn lands — 15-50s into a real run.
    head = run_line(configure(run_dir, ("opening",)))

    assert [s["side"] for s in head["sides"]] == ["pro", "con"]
    assert all({"side_index", "side", "team", "model"} <= set(s) for s in head["sides"])


def test_run_started_does_not_get_its_own_line(run_dir: Path):
    # It would be an empty line: the header above already said everything it holds.
    lines, _ = streamed(run_dir)
    assert not any(line["event"] == "run_started" for line in lines)


# --- the events (ADR-027 §3) -------------------------------------------------


def test_every_event_that_names_a_side_names_it_by_label_too(run_dir: Path):
    lines, _ = streamed(run_dir)
    sided = [line for line in lines if "side_index" in line]

    assert sided, "no event carried a side"
    for line in sided:
        assert line["side"] in ("pro", "con")


def test_a_completed_turn_carries_what_a_live_view_needs(run_dir: Path):
    lines, _ = streamed(run_dir, ("opening",))
    turn = next(line for line in lines if line["event"] == "turn_completed")

    # The text is in the stream because the file does not exist yet (§5).
    assert turn["text"]
    assert turn["usage"]["completion_tokens"] > 0
    assert {"order", "budget", "hit_budget", "latency_ms", "phase", "phase_index"} <= set(turn)


def test_the_phases_bracket_their_turns(run_dir: Path):
    lines, _ = streamed(run_dir, ("opening",))
    order = [line["event"] for line in lines]

    assert order[0] == "run"
    assert order[1] == "phase_started"
    assert order[-2] == "phase_completed"
    assert order[-1] == "run_completed"


def test_run_completed_counts_the_turns(run_dir: Path):
    lines, _ = streamed(run_dir, ("opening", "rebuttal"))
    assert lines[-1] == {"event": "run_completed", "turns": 4}


def test_length_is_absent_never_null(run_dir: Path):
    # The transcript's rule (ADR-016 §6), applied to the stream.
    lines, _ = streamed(run_dir, ("opening",))
    turn = next(line for line in lines if line["event"] == "turn_completed")
    assert turn["length"] == "medium"  # ADR-022 resolves a bare phase at load


# --- the properties a consumer relies on -------------------------------------


def test_each_line_is_flushed_as_it_is_written(run_dir: Path):
    """ADR-027 §2. Unflushed, a piped stream delivers nothing until kilobytes
    accumulate — for a debate, most of the run, which defeats the point."""
    flushes = []

    class Counting(io.StringIO):
        def flush(self):
            flushes.append(len(self.getvalue().splitlines()))

    config = configure(run_dir, ("opening",))
    out = Counting()
    events = EventBus()
    events.subscribe(make_event_writer(config, out))
    asyncio.run(run_debate(config, fakes(), events))

    lines = len(out.getvalue().splitlines())
    assert len(flushes) == lines  # one flush per line, not one at the end
    assert flushes == list(range(1, lines + 1))


def test_every_line_is_one_json_object(run_dir: Path):
    _, out = streamed(run_dir)
    for line in out.getvalue().splitlines():
        assert isinstance(json.loads(line), dict)
        assert "\n" not in line


def test_a_failed_run_ends_with_the_error_and_nothing_after(run_dir: Path):
    """§6: the stream is not a transcript. A failure leaves a partial stream
    describing turns that were never written anywhere."""
    config = configure(run_dir, ("opening",))
    out = io.StringIO()
    events = EventBus()
    events.subscribe(make_event_writer(config, out))
    asyncio.run(events.emit(DebateEvent(EventType.RUN_FAILED, error="the model returned no text")))

    lines = [json.loads(line) for line in out.getvalue().splitlines()]
    assert lines[-1] == {"event": "run_failed", "error": "the model returned no text"}
    assert not any(line["event"] == "run_completed" for line in lines)


def test_a_broken_consumer_cannot_abort_a_debate(run_dir: Path):
    # events.py catches a listener's failure by design; the stream must not be
    # the one exception to that.
    class Exploding(io.StringIO):
        def write(self, text):
            raise OSError("broken pipe")

    config = configure(run_dir, ("opening",))
    events = EventBus()
    events.subscribe(make_event_writer(config, Exploding()))
    transcript = asyncio.run(run_debate(config, fakes(), events))

    assert len(transcript.turns) == 2
