"""The transcript: the `debate` → `judge` contract (ADR-005).

Defined once here, as dataclasses, so `debate` (which builds it) and `judge`
(which reads it) can't drift apart. B2 builds this in memory; B3 writes it as
JSON. Standard library only (ADR-008).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

if TYPE_CHECKING:  # only for annotations: importing config here would pull in PyYAML
    from .config import RunConfig

SCHEMA_VERSION = 1


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
class Turn:
    """One side's turn in one phase, keyed by (phase_index, side_index) — Hard Rule 2."""

    phase_index: int
    phase: str
    side_index: int
    order: int  # 0 if this side spoke first in the phase, 1 if second
    text: str
    usage: Usage
    budget: int
    hit_budget: bool  # reached its budget, so the reply may have been cut off (ADR-010 §3)
    finish_reason: str
    latency_ms: int
    started_at: str


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


@dataclass(frozen=True)
class RunSnapshot:
    topic: str
    seed: int
    budget_tolerance: int
    phases: tuple[str, ...]
    sides: tuple[SideSnapshot, ...]


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


def snapshot(config: RunConfig, budget_tolerance: int) -> RunSnapshot:
    """Freeze the resolved config into the run snapshot (ADR-005)."""
    return RunSnapshot(
        topic=config.topic,
        seed=config.seed,
        budget_tolerance=budget_tolerance,
        phases=config.phases,
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
            )
            for side in config.sides
        ),
    )
