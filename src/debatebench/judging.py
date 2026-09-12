"""Scoring a transcript against the rubric (ADR-013, ADR-017).

Hard Rule 3 lives here. The model returns five independently-scored dimensions
per side and never a blended number; the total and the winner are computed here,
by arithmetic anyone can check, and are always written alongside every score
that went into them. Standard library only (ADR-008).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .backend import Backend, BackendError, GenerationRequest, Message
from .transcript import Transcript, package_version, utc_now, write_json

__all__ = ["JudgeError", "ScoreSheet", "score_debate", "write_scores"]

SCORE_SCHEMA_VERSION = 1

# The rubric (ADR-002, "Judge design"). The weights are each dimension's maximum,
# so the weighting is the scale itself and there is nothing else to blend.
DIMENSIONS = (
    ("argument_quality", 30),
    ("evidence_grounding", 25),
    ("steelman_fidelity", 20),
    ("rebuttal_effectiveness", 15),
    ("clarity", 10),
)
MAXIMA = dict(DIMENSIONS)

# ADR-002's vocabulary, fixed by ADR-017 §3: anything else is a parse failure.
HIT_STATUSES = ("open", "conceded", "rebutted", "dodged")

# How far the judge's one reply may exceed --budget, as a turn may (ADR-010 §3).
BUDGET_TOLERANCE = 16


class JudgeError(Exception):
    """A judging run that can't produce a complete score sheet (Hard Rule 3)."""


@dataclass(frozen=True)
class Hit:
    point: str
    status: str


@dataclass(frozen=True)
class DimensionScore:
    name: str
    score: int
    max: int
    justification: str
    prep_grounded: bool | None = None  # evidence_grounding only (ADR-013 §4)
    hit_ledger: tuple[Hit, ...] | None = None  # rebuttal_effectiveness only
    hit_ledger_reported: bool | None = None  # False when the judge gave none (ADR-017 §8)


@dataclass(frozen=True)
class SideScore:
    side_index: int
    side: str
    dimensions: tuple[DimensionScore, ...]
    total: int


@dataclass(frozen=True)
class ScoreSheet:
    judged_at: str
    judge_model: str
    judge_budget: int
    fact_check_enabled: bool
    sides: tuple[SideScore, ...]
    winner: str  # "pro", "con" or "draw"
    winner_reason: str
    schema_version: int = SCORE_SCHEMA_VERSION
    debatebench_version: str = ""


async def score_debate(
    transcript: Transcript,
    backend: Backend,
    *,
    model: str,
    budget: int,
    fact_check_enabled: bool = False,
) -> ScoreSheet:
    """One backend call, both sides, five dimensions each (ADR-013 §2)."""
    request = build_request(transcript, budget)
    try:
        result = await backend.generate(request)
    except BackendError as e:
        raise JudgeError(str(e)) from e
    if result.completion_tokens > budget + BUDGET_TOLERANCE:
        raise JudgeError(
            f"the judge returned {result.completion_tokens} completion tokens for a budget "
            f"of {budget}, over the {BUDGET_TOLERANCE}-token tolerance (Hard Rule 5)"
        )

    scored = parse_reply(result.text, transcript, truncated=result.completion_tokens >= budget)
    sides = tuple(
        SideScore(
            side_index=side.index,
            side=side.side,
            dimensions=scored[side.index],
            total=sum(dimension.score for dimension in scored[side.index]),
        )
        for side in transcript.run.sides
    )
    winner, reason = decide(sides)
    return ScoreSheet(
        judged_at=utc_now(),
        judge_model=model,
        judge_budget=budget,
        fact_check_enabled=fact_check_enabled,
        sides=sides,
        winner=winner,
        winner_reason=reason,
        debatebench_version=package_version(),
    )


def decide(sides: tuple[SideScore, ...]) -> tuple[str, str]:
    """The winner, by arithmetic outside the model (ADR-013 §3).

    Higher total, then steelman fidelity, then an honest draw. A forced verdict
    the scores don't support would be worse than no verdict.
    """
    first, second = sides
    if first.total != second.total:
        return (max(sides, key=lambda s: s.total).side, "total")
    steelman = {side.side_index: _dimension(side, "steelman_fidelity").score for side in sides}
    if steelman[first.side_index] != steelman[second.side_index]:
        return (max(sides, key=lambda s: steelman[s.side_index]).side, "steelman_tiebreak")
    return ("draw", "tied_after_steelman_tiebreak")


def _dimension(side: SideScore, name: str) -> DimensionScore:
    return next(dimension for dimension in side.dimensions if dimension.name == name)


# --- what the judge is asked ------------------------------------------------


def build_request(transcript: Transcript, budget: int) -> GenerationRequest:
    """The one scoring call: the whole debate, both sides, one JSON object back."""
    lines = [
        "You are judging a formal debate against a fixed rubric. Score each side "
        "independently on five dimensions. Never combine them into one number: the "
        "totals and the winner are worked out from your scores, not by you.",
        "",
        "The dimensions and their maximum scores:",
        "- argument_quality (0-30): the logic, and whether the case holds together.",
        "- evidence_grounding (0-25): "
        + (
            "whether each claim traces to a passage in that side's own prep evidence, "
            "which is shown below. A claim citing something the side never had scores low."
            if _prep_grounded(transcript)
            else "how specific, internally consistent and plausible the claims are. "
            "This debate has no prep phase, so there is no recorded evidence to check against."
        ),
        "- steelman_fidelity (0-20): whether each side stated the opponent's strongest "
        "argument fairly before answering it.",
        "- rebuttal_effectiveness (0-15): what each side did with the points aimed at it. "
        "This dimension must also carry a hit_ledger array: one entry for each point the "
        "opponent aimed at this side, each with the point in a few words and one status. "
        "Give every side a hit_ledger, using [] only when nothing was aimed at it.",
        "- clarity (0-10): whether the case is followable.",
        "",
        "Answer with one JSON object and nothing else, in exactly this shape:",
        _WIRE_SHAPE,
        "",
        f"Every score is an integer within its dimension's range. Every status is one of: "
        f"{', '.join(HIT_STATUSES)}. Every justification says why, in one or two sentences.",
    ]
    return GenerationRequest(
        messages=(
            Message("system", "\n".join(lines)),
            Message("user", f"{render(transcript)}\n\nScore this debate."),
        ),
        max_completion_tokens=budget,
        # The debate's own seed, so re-judging one transcript is reproducible (ADR-017 §6).
        seed=transcript.run.seed,
    )


_WIRE_SHAPE = """{
  "sides": [
    {
      "side_index": 0,
      "argument_quality": {"score": 0, "justification": "..."},
      "evidence_grounding": {"score": 0, "justification": "..."},
      "steelman_fidelity": {"score": 0, "justification": "..."},
      "rebuttal_effectiveness": {"score": 0, "justification": "...",
        "hit_ledger": [{"point": "the point they made", "status": "rebutted"}]},
      "clarity": {"score": 0, "justification": "..."}
    },
    { "side_index": 1, "...": "the same five dimensions" }
  ]
}"""


def render(transcript: Transcript) -> str:
    """The whole debate as the judge sees it: both sides, every turn, all evidence.

    Prep privacy binds debaters, not the judge (ADR-017 §5) — scoring whether a
    claim traces to a side's own evidence means seeing that evidence.
    """
    run = transcript.run
    lines = [f"Motion: {run.topic}", ""]
    for side in run.sides:
        lines.append(
            f"Side {side.index} ({side.side.upper()}): {side.team.name}, arguing "
            f"{'for' if side.side == 'pro' else 'against'} the motion, on {side.model}."
        )
    lines.append("")
    for number, turn in enumerate(transcript.turns, start=1):
        speaker = run.sides[turn.side_index]
        cut = " — reached its budget and may be cut off" if turn.hit_budget else ""
        lines.append(f"[{number}. {turn.phase.capitalize()} - {speaker.side.upper()}{cut}]")
        if turn.evidence:
            lines.append(f"Evidence this side retrieved ({len(turn.evidence)} passages):")
            lines += [f"  ({item.id}) {item.text.strip()}" for item in turn.evidence]
            lines.append("Its notes on that evidence:")
        lines.append(turn.text.strip())
        lines.append("")
    return "\n".join(lines).strip()


def _prep_grounded(transcript: Transcript) -> bool:
    """Whether this transcript has recorded evidence to check claims against."""
    return any(turn.phase == "prep" and turn.evidence for turn in transcript.turns)


# --- reading the reply ------------------------------------------------------


def parse_reply(
    text: str, transcript: Transcript, *, truncated: bool = False
) -> dict[int, tuple[DimensionScore, ...]]:
    """The model's JSON, checked hard. A malformed dimension is an error, never a zero."""
    payload = _json_object(text, truncated=truncated)
    sides = payload.get("sides")
    expected = [side.index for side in transcript.run.sides]
    if not isinstance(sides, list) or len(sides) != len(expected):
        raise JudgeError(
            f"the reply scores {len(sides) if isinstance(sides, list) else 'no'} sides, "
            f"and this debate has {len(expected)}"
        )

    grounded = _prep_grounded(transcript)
    scored: dict[int, tuple[DimensionScore, ...]] = {}
    for position, side in enumerate(sides):
        if not isinstance(side, dict):
            raise JudgeError(f"sides[{position}] is not a JSON object")
        index = side.get("side_index")
        if index not in expected:
            raise JudgeError(f"sides[{position}].side_index is {index!r}, not one of {expected}")
        if index in scored:
            raise JudgeError(f"side {index} is scored twice")
        scored[index] = tuple(
            _dimension_score(side, name, maximum, index, grounded)
            for name, maximum in DIMENSIONS
        )
    return scored


def _dimension_score(
    side: dict, name: str, maximum: int, index: Any, grounded: bool
) -> DimensionScore:
    where = f"side {index}'s {name}"
    body = side.get(name)
    if not isinstance(body, dict):
        raise JudgeError(f"{where} is missing")
    score = body.get("score")
    if isinstance(score, bool) or not isinstance(score, int):
        raise JudgeError(f"{where} score is {score!r}, not a whole number")
    if not 0 <= score <= maximum:
        raise JudgeError(f"{where} score is {score}, outside 0-{maximum}")
    justification = body.get("justification")
    if not isinstance(justification, str) or not justification.strip():
        raise JudgeError(f"{where} has no justification, so the score can't be checked")

    ledger = reported = None
    if name == "rebuttal_effectiveness":
        ledger, reported = _hit_ledger(body.get("hit_ledger"), where)
    return DimensionScore(
        name=name,
        score=score,
        max=maximum,
        justification=justification.strip(),
        # A fact about the transcript, not a judgment, so it's taken from the
        # transcript and never from the reply (ADR-017 §5).
        prep_grounded=grounded if name == "evidence_grounding" else None,
        hit_ledger=ledger,
        hit_ledger_reported=reported,
    )


def _hit_ledger(ledger: Any, where: str) -> tuple[tuple[Hit, ...], bool]:
    """The ledger and whether the judge supplied one at all (ADR-017 §8).

    An absent ledger reads as empty: the score and its justification are both
    there, so no dimension failed to parse, and inventing a failure would throw
    away a complete score sheet over a diagnostic extra. A ledger that *is*
    present is checked as strictly as ever.
    """
    if ledger is None:
        return (), False
    if not isinstance(ledger, list):
        raise JudgeError(f"{where} hit_ledger is {ledger!r}, not a list")
    hits = []
    for position, hit in enumerate(ledger):
        if not isinstance(hit, dict):
            raise JudgeError(f"{where} hit_ledger[{position}] is not a JSON object")
        point, status = hit.get("point"), hit.get("status")
        if not isinstance(point, str) or not point.strip():
            raise JudgeError(f"{where} hit_ledger[{position}] has no point")
        if status not in HIT_STATUSES:
            raise JudgeError(
                f"{where} hit_ledger[{position}] status is {status!r}, "
                f"not one of {', '.join(HIT_STATUSES)}"
            )
        hits.append(Hit(point=point.strip(), status=status))
    return tuple(hits), True


def _json_object(text: str, *, truncated: bool) -> dict:
    """The JSON object in a reply, tolerating a code fence and a preamble (ADR-017 §4)."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    hint = (
        " The reply reached its budget, so it was probably cut off mid-JSON: raise --budget."
        if truncated
        else ""
    )
    if start == -1 or end <= start:
        raise JudgeError(f"the reply holds no JSON object.{hint} It said: {text.strip()[:300]!r}")
    try:
        payload = json.loads(cleaned[start : end + 1])
    except ValueError as e:
        raise JudgeError(f"the reply's JSON is malformed: {e}.{hint}") from e
    if not isinstance(payload, dict):
        raise JudgeError("the reply's JSON is not an object")
    return payload


# --- writing the score file --------------------------------------------------


def as_json_dict(sheet: ScoreSheet) -> dict:
    """The score file ADR-013 §5 specifies, with its keys in that order."""
    return {
        "schema_version": sheet.schema_version,
        "debatebench_version": sheet.debatebench_version,
        "judged_at": sheet.judged_at,
        "judge_model": sheet.judge_model,
        "judge_budget": sheet.judge_budget,
        "fact_check_enabled": sheet.fact_check_enabled,
        "sides": [
            {
                "side_index": side.side_index,
                "side": side.side,
                "dimensions": {
                    dimension.name: _dimension_dict(dimension) for dimension in side.dimensions
                },
                "total": side.total,
            }
            for side in sheet.sides
        ],
        "winner": sheet.winner,
        "winner_reason": sheet.winner_reason,
    }


def _dimension_dict(dimension: DimensionScore) -> dict:
    body: dict[str, Any] = {
        "score": dimension.score,
        "max": dimension.max,
        "justification": dimension.justification,
    }
    if dimension.prep_grounded is not None:
        body["prep_grounded"] = dimension.prep_grounded
    if dimension.hit_ledger is not None:
        body["hit_ledger"] = [
            {"point": hit.point, "status": hit.status} for hit in dimension.hit_ledger
        ]
        # An empty ledger the judge gave and one it never gave are different facts.
        body["hit_ledger_reported"] = dimension.hit_ledger_reported
    return body


def write_scores(sheet: ScoreSheet, path: Path) -> Path | None:
    """Write the score file, rotating any file already there to ``<path>.1`` (ADR-017 §7)."""
    return write_json(as_json_dict(sheet), path)
