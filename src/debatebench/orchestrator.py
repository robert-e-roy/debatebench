"""The debate loop: phases are data, turns are checked, failure stops the run.

Hard Rules 1, 2, 5 and 6 live here. The loop iterates the configured phase list
and never branches on a phase's position; every turn is checked before it's kept;
and any failure aborts the run with nothing returned. Standard library only
(ADR-008).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from .backend import Backend, BackendError
from .events import DebateEvent, EventBus, EventType
from .prompts import build_prep_request, build_request
from .retrieval import RetrievalError, retrieve
from .transcript import Evidence, Transcript, Turn, Usage, snapshot, utc_now

__all__ = ["BUDGET_TOLERANCE", "DebateError", "Transcript", "run_debate", "speaking_order"]

if TYPE_CHECKING:  # only for annotations: importing config here would pull in PyYAML
    from .config import RunConfig, Side

# How far a reply may exceed its budget before the turn fails (ADR-010 §3).
BUDGET_TOLERANCE = 16


class DebateError(Exception):
    """A run that can't continue. Nothing partial is returned or written (Hard Rule 1)."""


async def run_debate(
    config: RunConfig, backends: Sequence[Backend], events: EventBus | None = None
) -> Transcript:
    bus = events or EventBus()
    started_at = utc_now()
    turns: list[Turn] = []

    await bus.emit(DebateEvent(EventType.RUN_STARTED))
    try:
        for phase_index, phase in enumerate(config.phases):
            await bus.emit(DebateEvent(EventType.PHASE_STARTED, phase_index=phase_index, phase=phase))
            for order, side_index in enumerate(speaking_order(config, phase_index)):
                turns.append(
                    await _take_turn(config, backends, bus, phase_index, phase, side_index, order, turns)
                )
            await bus.emit(DebateEvent(EventType.PHASE_COMPLETED, phase_index=phase_index, phase=phase))
    except Exception as e:
        await bus.emit(DebateEvent(EventType.RUN_FAILED, error=str(e)))
        raise

    transcript = Transcript(
        run=snapshot(config, BUDGET_TOLERANCE),
        turns=tuple(turns),
        started_at=started_at,
        finished_at=utc_now(),
    )
    await bus.emit(DebateEvent(EventType.RUN_COMPLETED))
    return transcript


def speaking_order(config: RunConfig, phase_index: int) -> tuple[int, int]:
    """Pro opens the first argument phase, and the opener alternates after it (ADR-010 §1)."""
    pro = next(side.index for side in config.sides if side.side == "pro")
    con = 1 - pro
    argument_phases_before = sum(1 for phase in config.phases[:phase_index] if phase != "prep")
    return (pro, con) if argument_phases_before % 2 == 0 else (con, pro)


async def _take_turn(
    config: RunConfig,
    backends: Sequence[Backend],
    bus: EventBus,
    phase_index: int,
    phase: str,
    side_index: int,
    order: int,
    turns: list[Turn],
) -> Turn:
    side = config.sides[side_index]
    await bus.emit(
        DebateEvent(EventType.TURN_STARTED, phase_index=phase_index, phase=phase, side_index=side_index)
    )
    started_at = utc_now()
    if phase == "prep":
        evidence = _prepare(config, phase_index, side)
        request = build_prep_request(config.topic, side, evidence, config.seed)
        # Prep is capped by prep_budget, and nothing about it is sequential (ADR-014 §3).
        budget, order = side.prep_budget, 0
    else:
        evidence = ()
        request = build_request(config.topic, side, phase, config.sides, turns, config.seed)
        budget = side.budget
    try:
        result = await backends[side_index].generate(request)
    except BackendError as e:
        raise DebateError(f"{_where(phase_index, phase, side)}: {e}") from e

    # A turn is checked before it's kept: no silent empty or over-budget turns (ADR-010 §3).
    if not result.text.strip():
        raise DebateError(f"{_where(phase_index, phase, side)}: the model returned no text")
    if result.completion_tokens > budget + BUDGET_TOLERANCE:
        raise DebateError(
            f"{_where(phase_index, phase, side)}: {result.completion_tokens} completion tokens "
            f"for a budget of {budget}, over the {BUDGET_TOLERANCE}-token tolerance "
            "(Hard Rule 5)"
        )

    turn = Turn(
        phase_index=phase_index,
        phase=phase,
        side_index=side_index,
        order=order,
        text=result.text,
        usage=Usage(result.prompt_tokens, result.completion_tokens),
        budget=budget,
        hit_budget=result.completion_tokens >= budget,
        finish_reason=result.finish_reason,
        latency_ms=result.latency_ms,
        started_at=started_at,
        evidence=evidence,
    )
    await bus.emit(
        DebateEvent(
            EventType.TURN_COMPLETED,
            phase_index=phase_index,
            phase=phase,
            side_index=side_index,
            turn=turn,
        )
    )
    return turn


def _prepare(config: RunConfig, phase_index: int, side: Side) -> tuple[Evidence, ...]:
    """One side's retrieved passages, before its one prep call sees them (ADR-012 §§1–2)."""
    try:
        evidence = retrieve(config.topic, side.side, config.sources, side.team.corpus_path)
    except RetrievalError as e:
        raise DebateError(f"{_where(phase_index, 'prep', side)}: {e}") from e
    if not evidence:
        # Counted after both pools: a corpus-only side is properly prepared (ADR-014 §4).
        searched = ", ".join(config.sources) or "no sources"
        if side.team.corpus is not None:
            searched += f" and its own corpus ({side.team.corpus})"
        raise DebateError(
            f"{_where(phase_index, 'prep', side)}: nothing matched the topic in {searched}, "
            "so this side would go into the debate with no evidence at all"
        )
    return evidence


def _where(phase_index: int, phase: str, side: Side) -> str:
    return f"phase {phase_index} ({phase}), side {side.index} ({side.side}, {side.team.name})"
