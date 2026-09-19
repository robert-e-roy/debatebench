"""The transcript: the `debate` → `judge` contract (ADR-005).

Defined once here, as dataclasses, so `debate` (which builds it) and `judge`
(which reads it) can't drift apart. B2 builds this in memory; B3 writes it as
JSON. Standard library only (ADR-008).
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

if TYPE_CHECKING:  # only for annotations: importing config here would pull in PyYAML
    from .config import RunConfig

# 2 adds each turn's optional `length` (ADR-016 §6). A v1 file migrates forward
# by doing nothing — it simply has no length fields — so both are readable.
# 3 adds ADR-037's record of what shaped the output: run.prompt, run.sources and
# each side's `thinking`. Earlier files migrate forward the same way: they carry
# no such keys, and a reader that finds none knows only that it was not recorded.
SCHEMA_VERSION = 3
READABLE_VERSIONS = (1, 2, 3)


def utc_now() -> str:
    """A timestamp in the form ADR-005's examples use."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def package_version() -> str:
    try:
        return version("debatebench")
    except PackageNotFoundError:  # running from a source tree that was never installed
        return "0+unknown"


def redact_url(url: str) -> str:
    """Drop any credentials embedded in a URL: a transcript never records them (ADR-005)."""
    parts = urlsplit(url)
    if not (parts.username or parts.password):
        return url
    host = parts.hostname or ""
    netloc = f"{host}:{parts.port}" if parts.port else host
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int


@dataclass(frozen=True)
class Evidence:
    """One retrieved passage a prep turn was given, in ADR-005's item shape."""

    id: str
    source: str
    text: str


@dataclass(frozen=True)
class Turn:
    """One side's turn in one phase, keyed by (phase_index, side_index) — Hard Rule 2."""

    phase_index: int
    phase: str
    side_index: int
    order: int  # 0 if this side spoke first in the phase, 1 if second; 0 on prep (ADR-014 §3)
    text: str
    usage: Usage
    budget: int
    hit_budget: bool  # reached its budget, so the reply may have been cut off (ADR-010 §3)
    finish_reason: str
    latency_ms: int
    started_at: str
    # Only a prep turn has evidence, and only there does the written document carry
    # the key at all: an empty list elsewhere would read as "prepared, found nothing".
    evidence: tuple[Evidence, ...] = ()
    # The length its phase asked for, present only when the entry carried a suffix
    # (ADR-016 §6). Never on a prep turn, which takes no suffix.
    length: str | None = None


@dataclass(frozen=True)
class PromptRecord:
    """What debatebench itself put in the prompt, and a digest of it (ADR-037).

    ``system`` is the prompt as a template — every config value replaced by its
    ``{slot}`` — so what remains is exactly this package's contribution. The
    values themselves are already recorded in ``TeamSnapshot`` and ``topic``;
    repeating them here would say nothing new and would make the digest move
    with the motion.
    """

    fingerprint: str
    system: str
    phases: tuple[tuple[str, str], ...]  # (phase:length, the instruction sent)


@dataclass(frozen=True)
class SourceRecord:
    """Which pool prep drew from, and whether it is still the same pool (ADR-037).

    Recorded only for a run that actually retrieved. ``fingerprint`` is over the
    file's bytes: the pools are rebuildable, and two runs on one machine can read
    different ones through ``DEBATEBENCH_SOURCES_DIR``.

    ``name`` is the shared pool's ``sources:`` name as run.yaml wrote it
    (``args-me``), or a team corpus's file name (``liberal-climate-corpus.jsonl``).
    The two are told apart by that extension, which is enough because a
    ``sources:`` entry never carries one (ADR-012 §5 appends it).
    """

    name: str
    rows: int
    fingerprint: str


@dataclass(frozen=True)
class TeamSnapshot:
    """A team file's contents, so a transcript stays readable after the file changes."""

    id: str
    name: str
    voice: str
    stance: str
    values: tuple[str, ...]
    corpus: str | None


@dataclass(frozen=True)
class SideSnapshot:
    index: int
    team_file: str
    team: TeamSnapshot
    side: str
    model: str
    base_url: str
    budget: int
    prep_budget: int | None
    # ADR-037: part of the request shape, not of the config's prose. ADR-033
    # measured this turning 2,254 characters of reasoning into none, so two runs
    # that differ only here are two different runs.
    thinking: bool = True


@dataclass(frozen=True)
class RunSnapshot:
    topic: str
    seed: int
    budget_tolerance: int
    phases: tuple[str, ...]
    sides: tuple[SideSnapshot, ...]
    # Both ADR-037, both optional so a v1 or v2 file still loads into this type.
    prompt: PromptRecord | None = None
    sources: tuple[SourceRecord, ...] = ()


@dataclass(frozen=True)
class Transcript:
    run: RunSnapshot
    turns: tuple[Turn, ...]
    started_at: str
    finished_at: str
    schema_version: int = SCHEMA_VERSION
    debatebench_version: str = field(default_factory=package_version)

    def turn(self, phase_index: int, side_index: int) -> Turn:
        for turn in self.turns:
            if (turn.phase_index, turn.side_index) == (phase_index, side_index):
                return turn
        raise KeyError((phase_index, side_index))


def as_json_dict(transcript: Transcript) -> dict:
    """The document ADR-005 specifies, with its keys in the order that ADR shows."""
    return {
        "schema_version": transcript.schema_version,
        "debatebench_version": transcript.debatebench_version,
        "started_at": transcript.started_at,
        "finished_at": transcript.finished_at,
        "run": _run_dict(transcript.run),
        "turns": [_turn_dict(turn) for turn in transcript.turns],
    }


def _run_dict(run: RunSnapshot) -> dict:
    """The run snapshot as written. ADR-037's keys are absent when there is
    nothing to say: a run judged from a v2 file recorded no prompt, and a run
    without prep read no pool. Absent says that; an empty object would not."""
    document = asdict(run)
    if run.prompt is None:
        del document["prompt"]
    else:
        # An object, not a list of pairs: the label is the key a reader looks up.
        document["prompt"]["phases"] = dict(run.prompt.phases)
    if not run.sources:
        del document["sources"]
    return document


def _turn_dict(turn: Turn) -> dict:
    """A turn as written, carrying `evidence` and `length` only where they mean
    something (ADR-014 §6, ADR-016 §6): absent, never null or empty."""
    document = asdict(turn)
    if not turn.evidence:
        del document["evidence"]
    if turn.length is None:
        del document["length"]
    return document


def write_transcript(transcript: Transcript, path: Path) -> Path | None:
    """Write the transcript to ``path``, rotating any file already there to ``<path>.1``."""
    return write_json(as_json_dict(transcript), path)


def write_json(document: dict, path: Path) -> Path | None:
    """Write one JSON document, rotating any file already there to ``<path>.1``.

    The new file is written in full first, so a failure while serializing leaves
    everything untouched. Returns the backup's path, or None if there was no file
    to rotate (ADR-005, "Writing"; ADR-017 §7 applies the same rule to score files).
    """
    text = json.dumps(document, allow_nan=False, ensure_ascii=False, indent=2)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f"{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write(text + "\n")
            file.flush()
            os.fsync(file.fileno())
        backup = None
        if path.exists():
            backup = path.with_name(f"{path.name}.1")
            os.replace(path, backup)
        os.replace(temporary, path)
        return backup
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


class TranscriptError(Exception):
    """A transcript file that can't be read as the document ADR-005 defines."""


def load_transcript(path: Path) -> Transcript:
    """Read a written transcript back. This document is judge's only interface (ADR-005)."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise TranscriptError(f"{path}: cannot be read: {e}") from e
    except ValueError as e:
        raise TranscriptError(f"{path}: not valid JSON: {e}") from e
    if not isinstance(document, dict):
        raise TranscriptError(f"{path}: the top level must be a JSON object")

    version = document.get("schema_version")
    if version not in READABLE_VERSIONS:
        readable = ", ".join(str(v) for v in READABLE_VERSIONS)
        raise TranscriptError(
            f"{path}: schema_version is {version!r}, and this build reads {readable}"
        )

    def need(holder: dict, key: str, kind: type, where: str):
        value = holder.get(key)
        if not isinstance(value, kind) or isinstance(value, bool) and kind is int:
            raise TranscriptError(f"{path}: {where}{key} is {value!r}, not {kind.__name__}")
        return value

    run = need(document, "run", dict, "")
    sides = []
    for index, side in enumerate(need(run, "sides", list, "run.")):
        where = f"run.sides[{index}]."
        if not isinstance(side, dict):
            raise TranscriptError(f"{path}: run.sides[{index}] is not an object")
        team = need(side, "team", dict, where)
        sides.append(
            SideSnapshot(
                index=need(side, "index", int, where),
                team_file=need(side, "team_file", str, where),
                team=TeamSnapshot(
                    id=need(team, "id", str, f"{where}team."),
                    name=need(team, "name", str, f"{where}team."),
                    voice=need(team, "voice", str, f"{where}team."),
                    stance=need(team, "stance", str, f"{where}team."),
                    values=tuple(team.get("values") or ()),
                    corpus=team.get("corpus"),
                ),
                side=need(side, "side", str, where),
                model=need(side, "model", str, where),
                base_url=need(side, "base_url", str, where),
                budget=need(side, "budget", int, where),
                prep_budget=side.get("prep_budget"),
                # ADR-037, absent in every v1 and v2 file. True is what those runs
                # actually sent (ADR-033 made it opt-in), so the default is the
                # historical fact rather than a guess.
                thinking=bool(side.get("thinking", True)),
            )
        )

    turns = []
    for index, turn in enumerate(need(document, "turns", list, "")):
        where = f"turns[{index}]."
        if not isinstance(turn, dict):
            raise TranscriptError(f"{path}: turns[{index}] is not an object")
        usage = need(turn, "usage", dict, where)
        turns.append(
            Turn(
                phase_index=need(turn, "phase_index", int, where),
                phase=need(turn, "phase", str, where),
                side_index=need(turn, "side_index", int, where),
                order=need(turn, "order", int, where),
                text=need(turn, "text", str, where),
                usage=Usage(
                    prompt_tokens=need(usage, "prompt_tokens", int, f"{where}usage."),
                    completion_tokens=need(usage, "completion_tokens", int, f"{where}usage."),
                ),
                budget=need(turn, "budget", int, where),
                hit_budget=bool(turn.get("hit_budget")),
                finish_reason=need(turn, "finish_reason", str, where),
                latency_ms=need(turn, "latency_ms", int, where),
                started_at=need(turn, "started_at", str, where),
                evidence=tuple(
                    Evidence(id=item["id"], source=item["source"], text=item["text"])
                    for item in turn.get("evidence", ())
                ),
                length=turn.get("length"),  # absent in every v1 file (ADR-016 §6)
            )
        )
    if not turns:
        raise TranscriptError(f"{path}: the transcript has no turns, so there is nothing to judge")

    return Transcript(
        run=RunSnapshot(
            topic=need(run, "topic", str, "run."),
            seed=need(run, "seed", int, "run."),
            budget_tolerance=need(run, "budget_tolerance", int, "run."),
            phases=tuple(need(run, "phases", list, "run.")),
            sides=tuple(sides),
            prompt=_prompt_record(run.get("prompt")),
            sources=tuple(
                SourceRecord(
                    name=str(item.get("name", "")),
                    rows=int(item.get("rows", 0)),
                    fingerprint=str(item.get("fingerprint", "")),
                )
                for item in run.get("sources", ())
                if isinstance(item, dict)
            ),
        ),
        turns=tuple(turns),
        started_at=need(document, "started_at", str, ""),
        finished_at=need(document, "finished_at", str, ""),
        schema_version=version,
        debatebench_version=str(document.get("debatebench_version", "")),
    )


def _prompt_record(value: object) -> PromptRecord | None:
    """ADR-037's prompt block, or None for a file written before it existed."""
    if not isinstance(value, dict):
        return None
    phases = value.get("phases")
    return PromptRecord(
        fingerprint=str(value.get("fingerprint", "")),
        system=str(value.get("system", "")),
        phases=tuple(phases.items()) if isinstance(phases, dict) else (),
    )


def snapshot(
    config: RunConfig,
    budget_tolerance: int,
    *,
    prompt: PromptRecord | None = None,
    sources: tuple[SourceRecord, ...] = (),
) -> RunSnapshot:
    """Freeze the resolved config into the run snapshot (ADR-005, ADR-037).

    ``prompt`` and ``sources`` are passed in rather than derived here: this
    module is imported *by* ``prompts`` and ``retrieval``, so building them here
    would make the import circular.
    """
    return RunSnapshot(
        topic=config.topic,
        seed=config.seed,
        budget_tolerance=budget_tolerance,
        phases=config.phases,
        prompt=prompt,
        sources=sources,
        sides=tuple(
            SideSnapshot(
                index=side.index,
                team_file=side.team_file,
                team=TeamSnapshot(
                    id=side.team.id,
                    name=side.team.name,
                    voice=side.team.voice,
                    stance=side.team.stance,
                    values=side.team.values,
                    corpus=side.team.corpus,
                ),
                side=side.side,
                model=side.model,
                base_url=redact_url(side.base_url),
                budget=side.budget,
                prep_budget=side.prep_budget,
                thinking=side.thinking,
            )
            for side in config.sides
        ),
    )
