"""Scoring a transcript against the rubric (ADR-013, ADR-017).

Hard Rule 3 lives here. The model returns five independently-scored dimensions
per side and never a blended number; the total and the winner are computed here,
by arithmetic anyone can check, and are always written alongside every score
that went into them. Standard library only (ADR-008).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .backend import Backend, BackendError, GenerationRequest, Message
from .prompts import fingerprint
from .transcript import Transcript, package_version, utc_now, write_json

__all__ = [
    "Claim",
    "FactCheck",
    "JudgeError",
    "ScoreSheet",
    "fact_check_debate",
    "score_debate",
    "write_scores",
]

# 2 adds the optional fact_check section (ADR-015 §4).
# 3 adds ADR-037's record of what produced the scores: the prompt block, and the
# `strict_json` and `thinking` request settings. Both demonstrably change the
# ledger, and neither was written down before.
SCORE_SCHEMA_VERSION = 3

# What a fact-check verdict may be (ADR-015 §2). Checked against the record —
# both sides' evidence and turns — never against the model's own knowledge.
VERDICTS = ("supported", "contradicted", "unsupported", "not_checkable")
CHECKED_AGAINST = "recorded_evidence"

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
class Claim:
    """One factual claim a turn made, and how the record bears on it (ADR-015 §2)."""

    phase_index: int
    side_index: int
    claim: str
    verdict: str
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class FactCheck:
    checked_against: str  # always CHECKED_AGAINST in v1: the record, never the world
    claims: tuple[Claim, ...]
    note: str | None = None  # why every verdict is not_checkable, when that happens


@dataclass(frozen=True)
class SideScore:
    side_index: int
    side: str
    dimensions: tuple[DimensionScore, ...]
    total: int


@dataclass(frozen=True)
class JudgePrompt:
    """The system messages that produced a score file (ADR-037).

    Recorded verbatim rather than as a template, because both of these *branch*:
    the scoring prompt's `evidence_grounding` line differs on whether the
    transcript has prep, and the audit's passage-id line differs on whether any
    ids were recorded. A template would record a string that was never sent.
    Safe to record whole: the transcript travels in the *user* message, so
    neither string carries per-run content.
    """

    fingerprint: str
    score_system: str
    fact_check_system: str | None = None  # None when --no-fact-check


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
    fact_check: FactCheck | None = None  # absent, not empty, when disabled (ADR-015 §4)
    # ADR-037. Defaults keep every existing constructor call valid; the CLI and
    # api.judge always set them, so a file this build writes always has them.
    prompt: JudgePrompt | None = None
    strict_json: bool = True
    thinking: bool = True


async def score_debate(
    transcript: Transcript,
    backend: Backend,
    *,
    model: str,
    budget: int,
    fact_check_enabled: bool = False,
    strict_json: bool = True,
    thinking: bool = True,
) -> ScoreSheet:
    """One backend call, both sides, five dimensions each (ADR-013 §2)."""
    request = build_request(transcript, budget, strict_json=strict_json, thinking=thinking)
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
    winner, reason = decide(sides, transcript.run.seed)
    return ScoreSheet(
        judged_at=utc_now(),
        judge_model=model,
        judge_budget=budget,
        fact_check_enabled=fact_check_enabled,
        sides=sides,
        winner=winner,
        winner_reason=reason,
        debatebench_version=package_version(),
        # The message that was actually sent, taken from the request itself
        # rather than rebuilt — a second construction could differ from it.
        prompt=JudgePrompt(
            fingerprint=fingerprint(request.messages[0].content),
            score_system=request.messages[0].content,
        ),
        strict_json=strict_json,
        thinking=thinking,
    )


def decide(sides: tuple[SideScore, ...], seed: int) -> tuple[str, str]:
    """The winner, by arithmetic outside the model (ADR-013 §3).

    Higher total, then steelman fidelity, then a coin toss (ADR-023). The toss
    is the transcript's own seed, not a draw made here, so a tied transcript
    always resolves the same way — and so that the one step of the pipeline
    which is pure arithmetic stays that way.
    """
    first, second = sides
    if first.total != second.total:
        return (max(sides, key=lambda s: s.total).side, "total")
    steelman = {side.side_index: _dimension(side, "steelman_fidelity").score for side in sides}
    if steelman[first.side_index] != steelman[second.side_index]:
        return (max(sides, key=lambda s: steelman[s.side_index]).side, "steelman_tiebreak")
    # ADR-023 §2-3: keyed to the side index, not the team, so a sides-swapped
    # pair at one seed gives each team one toss (OPEN-QUESTIONS 9).
    won = next(side for side in sides if side.side_index == seed % 2)
    return (won.side, "coin_toss")


def _dimension(side: SideScore, name: str) -> DimensionScore:
    return next(dimension for dimension in side.dimensions if dimension.name == name)


# --- what the judge is asked ------------------------------------------------


def build_request(
    transcript: Transcript, budget: int, *, strict_json: bool = True, thinking: bool = True
) -> GenerationRequest:
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
        response_schema=score_schema() if strict_json else None,
        thinking=thinking,
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


def score_schema() -> dict:
    """The score reply, as a JSON schema (ADR-032 §3).

    Names every dimension and constrains `hit_ledger[].status` to ADR-017 §3's
    four values — the vocabulary `mistral-nemo` invented `partially rebutted`
    for. `parse_reply` still checks all of this; the schema only stops the
    sampler producing it (ADR-032 §6).
    """
    dimension = {
        "type": "object",
        "properties": {
            "score": {"type": "integer"},
            "justification": {"type": "string"},
        },
        "required": ["score", "justification"],
        "additionalProperties": False,
    }
    rebuttal = {
        "type": "object",
        "properties": {
            "score": {"type": "integer"},
            "justification": {"type": "string"},
            "hit_ledger": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "point": {"type": "string"},
                        "status": {"type": "string", "enum": list(HIT_STATUSES)},
                    },
                    "required": ["point", "status"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["score", "justification", "hit_ledger"],
        "additionalProperties": False,
    }
    side = {
        "type": "object",
        "properties": {
            "side_index": {"type": "integer"},
            **{name: dimension for name, _ in DIMENSIONS if name != "rebuttal_effectiveness"},
            "rebuttal_effectiveness": rebuttal,
        },
        "required": ["side_index", *(name for name, _ in DIMENSIONS)],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"sides": {"type": "array", "items": side}},
        "required": ["sides"],
        "additionalProperties": False,
    }


def claims_schema(transcript: Transcript) -> dict:
    """The claims reply, as a JSON schema closed over THIS transcript (ADR-032 §3).

    `verdict` is ADR-015 §2's four values. `evidence_ids` is an enum of the ids
    this transcript actually recorded — so `am-255`, which `phi4-mini` invented,
    is not a token the sampler may emit. A whole class of validation error stops
    being possible rather than being caught.
    """
    known = sorted(_evidence_ids(transcript))
    # With no prep there is nothing to cite, and an empty enum is not a legal
    # schema — so the array is simply constrained to be empty (ADR-015 §2's
    # degradation path, where every verdict is not_checkable anyway).
    ids = {"type": "array", "items": {"type": "string", "enum": known}} if known else {
        "type": "array", "maxItems": 0, "items": {"type": "string"}
    }
    return {
        "type": "object",
        "properties": {
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "turn": {"type": "integer", "minimum": 1,
                                 "maximum": max(len(transcript.turns), 1)},
                        "claim": {"type": "string"},
                        "verdict": {"type": "string", "enum": list(VERDICTS)},
                        "evidence_ids": ids,
                    },
                    "required": ["turn", "claim", "verdict", "evidence_ids"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["claims"],
        "additionalProperties": False,
    }


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
        # The coordinates are shown, not just the running number: the audit has to
        # cite phase_index/side_index, and inferring them from a 1..n display is
        # how a judge ends up pointing at a phase that doesn't exist.
        lines.append(
            f"[turn {number} | phase_index {turn.phase_index}, side_index {turn.side_index}"
            f" | {turn.phase.capitalize()} - {speaker.side.upper()}{cut}]"
        )
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
    # ADR-026 §2: the repair was measured after this message was written. The reply
    # is deterministic only while the model stays loaded, so an unload-and-rerun
    # gets a different one. Said here because the operator cannot guess it, and
    # NOT done automatically — ADR-017 §4, and a visible failure is what let the
    # project measure a 33% malformed rate at all.
    repair = (
        " Two things change the reply without touching the seed: stopping the model "
        "(ollama stop <model>) and judging again, which works on some models and not "
        "others, and changing --budget, which alters the request and so the reply. "
        "Neither is guaranteed — some models return the same fault every time."
    )
    if start == -1 or end <= start:
        raise JudgeError(
            f"the reply holds no JSON object.{hint}{'' if truncated else repair} "
            f"It said: {text.strip()[:300]!r}"
        )
    body = cleaned[start : end + 1]
    try:
        payload = json.loads(body)
    except ValueError:
        # One known, mechanical defect: an escape JSON doesn't define (ADR-017 §4).
        try:
            payload = json.loads(_repair_escapes(body))
        except ValueError as e:
            # Show the text at the fault. "Expecting ':' delimiter: line 35
            # column 78" is true and useless on its own: diagnosing it once cost
            # three throwaway scripts to recover a reply the error already held.
            raise JudgeError(
                f"the reply's JSON is malformed: {e}.{hint}{repair} "
                f"The text at the fault: {_around(body, getattr(e, 'pos', 0))}"
            ) from e
    if not isinstance(payload, dict):
        raise JudgeError("the reply's JSON is not an object")
    return payload


# The escapes JSON actually defines. Anything else after a backslash is invalid.
_JSON_ESCAPES = '"\\/bfnrtu'


def _around(text: str, position: int, width: int = 90) -> str:
    """The text either side of a fault, so the error carries its own diagnosis."""
    start = max(0, position - width // 2)
    window = text[start : start + width]
    return f"…{window}…" if start else f"{window}…"


def _repair_escapes(body: str) -> str:
    r"""Drop backslashes JSON doesn't define, keeping the character they escaped.

    Qwen through mlx_lm emits Python-style ``\'`` inside strings, and JSON defines
    no such escape, so a single apostrophe rejects an otherwise complete score
    sheet. Dropping the backslash changes no meaning, and a valid ``\\`` pair is
    left intact. This is lossless and deterministic — the same reply always
    repairs the same way — which is what separates it from the retry loop
    ADR-017 §4 refuses.
    """
    out: list[str] = []
    index = 0
    while index < len(body):
        character = body[index]
        if character == "\\" and index + 1 < len(body):
            following = body[index + 1]
            if following in _JSON_ESCAPES:
                out.append(character)  # a real escape: keep the pair as it is
            out.append(following)
            index += 2
            continue
        out.append(character)
        index += 1
    return "".join(out)


# --- the fact-check pass (ADR-015) ------------------------------------------


_NO_EVIDENCE_NOTE = (
    "this transcript has no prep evidence, so nothing was recorded to check a claim "
    "against; every factual claim is not_checkable rather than unsupported"
)


async def fact_check_debate(
    transcript: Transcript, backend: Backend, *, budget: int, strict_json: bool = True,
    thinking: bool = True
) -> FactCheck:
    """The second call: each turn's factual claims, judged against the record (ADR-015 §3).

    Never against the model's own knowledge — that is used only to tell a factual
    claim from an opinion. A transcript with no recorded evidence still gets its
    claims listed, all ``not_checkable``, with a note saying why (ADR-015 §2).
    """
    known = _evidence_ids(transcript)
    request = build_fact_check_request(transcript, budget, strict_json=strict_json,
                                       thinking=thinking)
    try:
        result = await backend.generate(request)
    except BackendError as e:
        raise JudgeError(str(e)) from e
    if result.completion_tokens > budget + BUDGET_TOLERANCE:
        raise JudgeError(
            f"the fact-check returned {result.completion_tokens} completion tokens for a "
            f"budget of {budget}, over the {BUDGET_TOLERANCE}-token tolerance (Hard Rule 5)"
        )

    claims = parse_claims(
        result.text, transcript, known, truncated=result.completion_tokens >= budget
    )
    if not known:
        # Nothing recorded to check against: say so once, rather than per claim.
        claims = tuple(replace(claim, verdict="not_checkable", evidence_ids=()) for claim in claims)
        return FactCheck(CHECKED_AGAINST, claims, note=_NO_EVIDENCE_NOTE)
    return FactCheck(CHECKED_AGAINST, claims)


def fact_check_prompt(
    transcript: Transcript, budget: int, *, strict_json: bool, thinking: bool
) -> str:
    """The audit's system message, for the score file's record (ADR-037).

    The same builder, called with the same arguments, so this is the string the
    audit was given — ``tests/test_record.py`` checks it against what the backend
    actually received rather than trusting that sentence.
    """
    request = build_fact_check_request(
        transcript, budget, strict_json=strict_json, thinking=thinking
    )
    return request.messages[0].content


def build_fact_check_request(
    transcript: Transcript, budget: int, *, strict_json: bool = True, thinking: bool = True
) -> GenerationRequest:
    known = sorted(_evidence_ids(transcript))
    available = (
        f"The recorded passage ids you may cite: {', '.join(known)}."
        if known
        else (
            "Nothing was recorded to check against: this debate had no prep phase. "
            "Cite no ids at all — there are none — and give every assertion the "
            "verdict not_checkable."
        )
    )
    system = "\n".join([
        "You are auditing a finished debate. For each argument turn, list every "
        "assertion it makes, then give each one a verdict. Filter nothing out: an "
        "assertion that turns out not to be factual is still listed, and its verdict "
        "is not_checkable.",
        "",
        # ADR-034 §1-2: turns tell you what the claim IS; passages decide the
        # verdict. Admitting a turn as grounds for `contradicted` makes the
        # verdict vacuous — in an adversarial debate the opponent always argued
        # against it — and produces a citation nobody can check, because only
        # passages have ids. Argument-versus-argument lives in the hit ledger.
        "A VERDICT IS DECIDED ONLY BY THE RETRIEVED PASSAGES. Read the turns to "
        "understand what each side is claiming, but a claim counts as supported or "
        "contradicted only when a listed PASSAGE backs or contradicts it. That the "
        "opposing side argued against a claim is not a contradiction — in a debate "
        "both sides always argue against each other, so it tells you nothing. Never "
        "treat your own knowledge as proof that a claim is true or false; use it "
        "only to tell a factual claim from an opinion.",
        "",
        "Before settling on any verdict, read every listed passage from BOTH sides. A "
        "claim one side makes is often contradicted by a passage the other side "
        "retrieved, and catching that is the point of this audit.",
        "",
        "CONTRADICTION WINS (ADR-019). If any passage contradicts the claim, the "
        "verdict is contradicted — even when another passage backs it, and even when "
        "the backing passage is the speaker's own. A claim is only supported when "
        "nothing in the record contradicts it. On a contested motion both sides "
        "usually retrieved passages on the same point, so check for a contradicting "
        "one before you answer supported.",
        "",
        # ADR-024 §3's reorder was measured and REVERTED (condition B, 2026-09-14):
        # leading with not_checkable produced no not_checkable at all and cost all
        # three cross-side contradictions in the warm state. Artifacts and the full
        # comparison are in probe/b6/README.md. This is the baseline order.
        "- supported: a recorded passage backs the claim AND no recorded passage "
        "contradicts it. Cite the backing id.",
        "- contradicted: a recorded PASSAGE contradicts it, including one the "
        "opponent retrieved. Cite the contradicting id, not the backing one. The "
        "cited passage must be the one that contradicts the claim — not merely a "
        "passage on the same subject.",
        "- unsupported: it is a factual claim, but no PASSAGE bears on it either "
        "way. A claim the other side merely argued against, with no passage "
        "against it, is unsupported — not contradicted. Cite nothing.",
        "- not_checkable: an opinion, a prediction or a value judgement rather than a "
        "factual claim. Cite nothing.",
        "",
        available,
        "",
        "Identify each turn by the `turn` number shown in its header above — the "
        "single number after the opening bracket. Do not copy phase_index or "
        "side_index; they are shown for reading only.",
        "",
        "Answer with one JSON object and nothing else:",
        _CLAIM_SHAPE,
    ])
    return GenerationRequest(
        messages=(
            Message("system", system),
            # This line said "factual claims", contradicting the system prompt's
            # "Filter nothing out" from the last position the model reads. Condition C
            # rewrote it and was REVERTED: no not_checkable appeared, and the warm
            # ledger collapsed from 20 claims to 5. See probe/b6/README.md.
            Message("user", f"{render(transcript)}\n\nAudit this debate's factual claims."),
        ),
        max_completion_tokens=budget,
        seed=transcript.run.seed,
        response_schema=claims_schema(transcript) if strict_json else None,
        thinking=thinking,
    )


_CLAIM_SHAPE = """{
  "claims": [
    {"turn": 3, "claim": "what was asserted",
     "verdict": "supported", "evidence_ids": ["am-1"]}
  ]
}"""


def parse_claims(
    text: str, transcript: Transcript, known: frozenset[str], *, truncated: bool = False
) -> tuple[Claim, ...]:
    """The claims ledger, checked as hard as the score sheet is."""
    payload = _json_object(text, truncated=truncated)
    listed = payload.get("claims")
    if not isinstance(listed, list):
        raise JudgeError("the fact-check reply has no claims list")

    # The audit cites the turn number the rendering already prints, and the
    # coordinates are mapped back here. Asking it to transcribe phase_index and
    # side_index was the field it kept mangling: three of the four malformed
    # replies measured across four backends corrupted a coordinate, not prose.
    # The stored Claim and the score file still carry both (ADR-015 §4).
    by_number = {number: turn for number, turn in enumerate(transcript.turns, start=1)}
    claims = []
    for position, entry in enumerate(listed):
        where = f"claims[{position}]"
        if not isinstance(entry, dict):
            raise JudgeError(f"{where} is not a JSON object")
        number = entry.get("turn")
        if isinstance(number, bool) or number not in by_number:
            raise JudgeError(
                f"{where} cites turn {number!r}, and this transcript has turns "
                f"1-{len(by_number)}"
            )
        phase_index = by_number[number].phase_index
        side_index = by_number[number].side_index
        claim = entry.get("claim")
        if not isinstance(claim, str) or not claim.strip():
            raise JudgeError(f"{where} has no claim text")
        verdict = entry.get("verdict")
        if verdict not in VERDICTS:
            raise JudgeError(
                f"{where} verdict is {verdict!r}, not one of {', '.join(VERDICTS)}"
            )
        ids = _evidence_citations(entry.get("evidence_ids"), where, verdict, known)
        claims.append(
            Claim(
                phase_index=phase_index,
                side_index=side_index,
                claim=claim.strip(),
                verdict=verdict,
                evidence_ids=ids,
            )
        )
    return tuple(claims)


def _evidence_citations(
    cited: Any, where: str, verdict: str, known: frozenset[str]
) -> tuple[str, ...]:
    """Ids a verdict rests on, which must be ids the transcript actually recorded.

    A supported or contradicted verdict citing nothing, or citing a passage that
    isn't in the record, is unfalsifiable — exactly what this pass exists to avoid.
    """
    if not known:
        # Nothing was recorded, so no citation can be checked either way, and every
        # verdict is forced to not_checkable with its ids cleared (ADR-015 §2).
        # Refusing here would abort a run over ids that are about to be discarded.
        return ()
    if cited is None:
        cited = []
    if not isinstance(cited, list) or not all(isinstance(item, str) for item in cited):
        raise JudgeError(f"{where} evidence_ids is {cited!r}, not a list of ids")
    unknown = [item for item in cited if item not in known]
    if unknown:
        raise JudgeError(
            f"{where} cites {', '.join(repr(item) for item in unknown)}, which "
            "the transcript never recorded"
        )
    if verdict in ("supported", "contradicted") and not cited:
        raise JudgeError(f"{where} is {verdict} but cites no passage, so nothing can check it")
    if verdict in ("unsupported", "not_checkable") and cited:
        raise JudgeError(f"{where} is {verdict} but cites {len(cited)} passage(s)")
    return tuple(cited)


def _evidence_ids(transcript: Transcript) -> frozenset[str]:
    return frozenset(item.id for turn in transcript.turns for item in turn.evidence)


# --- writing the score file --------------------------------------------------


def _prompt_dict(prompt: JudgePrompt) -> dict:
    """ADR-037's prompt block. ``fact_check_system`` is absent, not null, when the
    audit did not run — the same rule ``fact_check`` itself follows (ADR-015 §4)."""
    document = {"fingerprint": prompt.fingerprint, "score_system": prompt.score_system}
    if prompt.fact_check_system is not None:
        document["fact_check_system"] = prompt.fact_check_system
    return document


def as_json_dict(sheet: ScoreSheet) -> dict:
    """The score file ADR-013 §5 specifies, with its keys in that order."""
    return {
        "schema_version": sheet.schema_version,
        "debatebench_version": sheet.debatebench_version,
        "judged_at": sheet.judged_at,
        "judge_model": sheet.judge_model,
        "judge_budget": sheet.judge_budget,
        "fact_check_enabled": sheet.fact_check_enabled,
        # ADR-037: the request shape, beside the model and budget that were
        # already here. Both of these change the ledger and neither was recorded.
        "strict_json": sheet.strict_json,
        "thinking": sheet.thinking,
        **({} if sheet.prompt is None else {"prompt": _prompt_dict(sheet.prompt)}),
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
        # Absent when disabled, never an empty section (ADR-015 §4).
        **(
            {
                "fact_check": {
                    "checked_against": sheet.fact_check.checked_against,
                    **({"note": sheet.fact_check.note} if sheet.fact_check.note else {}),
                    "claims": [
                        {
                            "phase_index": claim.phase_index,
                            "side_index": claim.side_index,
                            "claim": claim.claim,
                            "verdict": claim.verdict,
                            "evidence_ids": list(claim.evidence_ids),
                        }
                        for claim in sheet.fact_check.claims
                    ],
                }
            }
            if sheet.fact_check is not None
            else {}
        ),
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
