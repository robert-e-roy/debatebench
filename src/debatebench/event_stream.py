"""JSONL on stdout, one line per event: the machine-readable view of a run.

ADR-027. This exists so another program can watch a debate without scraping the
stderr log, whose wording is free to change, and without importing this package.
Standard library only (ADR-008).

The stream is **not** a transcript (ADR-027 §6). It is not rotated, it is not
atomic, and a failed run leaves a partial stream describing turns that were
never written anywhere. A consumer that wants the durable record reads
``run.yaml``'s ``output:`` after seeing ``run_completed`` — and must wait for
that line, because on failure the file it would otherwise find belongs to the
previous run.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from typing import IO, TYPE_CHECKING

from .events import DebateEvent, EventType, Listener

if TYPE_CHECKING:  # annotations only: importing config here would pull in PyYAML
    from .config import RunConfig

__all__ = ["SCHEMA_VERSION", "make_event_writer", "run_line"]

# On the `run` line only, and independent of ADR-005's transcript version: they
# describe different documents (ADR-027 §4).
SCHEMA_VERSION = 1


def run_line(config: RunConfig) -> dict:
    """The header a consumer needs before any turn arrives (ADR-027 §3).

    The bus's RUN_STARTED carries no payload, so this is built from the resolved
    config rather than by changing the event dataclass every consumer shares.
    """
    return {
        "event": "run",
        "schema_version": SCHEMA_VERSION,
        "topic": config.topic,
        "seed": config.seed,
        "phases": list(config.phases),
        "sides": [
            {
                "side_index": side.index,
                "side": side.side,
                "team": side.team.name,
                "model": side.model,
            }
            for side in config.sides
        ],
    }


def make_event_writer(config: RunConfig, stream: IO[str] | None = None) -> Listener:
    """A listener that writes each event as one flushed JSON line (ADR-027 §1–§2).

    Flushing per line is the whole point: Python block-buffers stdout when it is
    a pipe, and an unflushed stream would deliver nothing until kilobytes had
    accumulated — for a debate, most of the run.
    """
    out = stream if stream is not None else sys.stdout
    labels = tuple(side.side for side in config.sides)
    turns = 0

    def write(document: dict) -> None:
        out.write(json.dumps(document, ensure_ascii=False, allow_nan=False) + "\n")
        out.flush()

    def emit(event: DebateEvent) -> None:
        nonlocal turns
        if event.type is EventType.RUN_STARTED:
            # The header goes here, not at construction, so it is inside the bus's
            # guard: a consumer that has already died — `--events | head -2` closes
            # the pipe — must not take the debate down with it (events.py, ADR-001).
            # RUN_STARTED is emitted before any turn, so §3's ordering still holds.
            write(run_line(config))
            return
        document: dict = {"event": str(event.type)}
        if event.phase_index is not None:
            document["phase_index"] = event.phase_index
        if event.phase is not None:
            document["phase"] = event.phase
        if event.side_index is not None:
            # Named as well as numbered, so a reader never holds the mapping.
            document["side_index"] = event.side_index
            document["side"] = labels[event.side_index]
        if event.turn is not None:
            turn = event.turn
            document.update(
                order=turn.order,
                text=turn.text,
                budget=turn.budget,
                hit_budget=turn.hit_budget,
                finish_reason=turn.finish_reason,
                latency_ms=turn.latency_ms,
                started_at=turn.started_at,
                usage=asdict(turn.usage),
            )
            # Absent rather than null where they mean nothing, as the transcript
            # does (ADR-014 §6, ADR-016 §6).
            if turn.length is not None:
                document["length"] = turn.length
            if turn.evidence:
                document["evidence"] = [asdict(item) for item in turn.evidence]
            turns += 1
        if event.error is not None:
            document["error"] = event.error
        if event.type is EventType.RUN_COMPLETED:
            document["turns"] = turns
        write(document)

    return emit
