"""The public API (ADR-028). Everything here is supported; everything else isn't.

Two functions, named for the two commands:

    import asyncio
    from debatebench.api import debate, judge, load_run, write_transcript

    config = load_run("run.yaml")
    transcript = asyncio.run(debate(config))
    write_transcript(transcript, config.output)

    sheet = asyncio.run(judge(transcript, model="qwen3:8b",
                              base_url="http://localhost:11434/v1", budget=6000))
    print(sheet.winner, [side.total for side in sheet.sides])

Nothing here writes a file on its own (ADR-028 §5) and nothing is synchronous
(§6). Pass ``backends=`` or ``backend=`` and no HTTP call is made at all —
anything with one ``async generate`` satisfies ADR-009's ``Backend``.

This is the one module allowed to import both httpx and PyYAML, because
composing the tool's two jobs needs both. That is why it is absent from
tests/test_layering.py, and why it is not re-exported from ``__init__.py``.
"""

from __future__ import annotations

# Aliased out of the namespace: this module's name list is its contract, so a
# name that is here only to implement something must not read as an export.
from collections.abc import Sequence as _Sequence
from dataclasses import replace as _replace

from .backend import (
    DEFAULT_READ_TIMEOUT,
    Backend,
    BackendError,
    GenerationRequest,
    GenerationResult,
    Message,
)
from .config import ConfigError, JudgeConfig, RunConfig, Side, Team, load_run
from .event_stream import SCHEMA_VERSION as EVENT_SCHEMA_VERSION
from .event_stream import make_event_writer
from .events import DebateEvent, EventBus, EventType
from .judging import (
    DIMENSIONS,
    HIT_STATUSES,
    SCORE_SCHEMA_VERSION,
    VERDICTS,
    Claim,
    DimensionScore,
    FactCheck,
    Hit,
    JudgeError,
    ScoreSheet,
    SideScore,
    write_scores,
)
from .judging import fact_check_debate as _fact_check_debate
from .judging import score_debate as _score_debate
from .judging import as_json_dict as scores_json
from .openai_compat import OpenAICompatibleBackend, open_client
from .orchestrator import DebateError
from .orchestrator import run_debate as _orchestrate
from .retrieval import RetrievalError
from .transcript import SCHEMA_VERSION as TRANSCRIPT_SCHEMA_VERSION
from .transcript import (
    Evidence,
    RunSnapshot,
    SideSnapshot,
    TeamSnapshot,
    Transcript,
    TranscriptError,
    Turn,
    Usage,
    load_transcript,
    write_transcript,
)
from .transcript import as_json_dict as transcript_json

__all__ = [
    # The two jobs (ADR-028 §2)
    "debate",
    "judge",
    # Reading configs and transcripts
    "load_run",
    "load_transcript",
    # Writing, which the two above deliberately do not do (ADR-028 §5)
    "write_transcript",
    "write_scores",
    "transcript_json",
    "scores_json",
    # The backend seam: implement this and the API makes no HTTP call (ADR-009)
    "Backend",
    "GenerationRequest",
    "GenerationResult",
    "Message",
    "OpenAICompatibleBackend",
    "open_client",
    "DEFAULT_READ_TIMEOUT",
    # Watching a run in-process; --events is the out-of-process equivalent (ADR-027)
    "DebateEvent",
    "EventBus",
    "EventType",
    "make_event_writer",
    # Config types
    "RunConfig",
    "JudgeConfig",
    "Side",
    "Team",
    # Transcript types (ADR-005)
    "Transcript",
    "Turn",
    "Usage",
    "Evidence",
    "RunSnapshot",
    "SideSnapshot",
    "TeamSnapshot",
    # Score types (ADR-013, ADR-015)
    "ScoreSheet",
    "SideScore",
    "DimensionScore",
    "Hit",
    "FactCheck",
    "Claim",
    # Every way this fails (ADR-028 Consequences: no common base, yet)
    "ConfigError",
    "DebateError",
    "JudgeError",
    "BackendError",
    "TranscriptError",
    "RetrievalError",
    # The vocabularies a score file uses
    "DIMENSIONS",
    "HIT_STATUSES",
    "VERDICTS",
    # The three durable contracts (ADR-028 §9)
    "TRANSCRIPT_SCHEMA_VERSION",
    "SCORE_SCHEMA_VERSION",
    "EVENT_SCHEMA_VERSION",
]


async def debate(
    config: RunConfig,
    *,
    backends: _Sequence[Backend] | None = None,
    events: EventBus | None = None,
) -> Transcript:
    """Run every configured phase and return the transcript. Writes nothing.

    ``backends`` is one per side, in side-index order; omit it and one
    ``OpenAICompatibleBackend`` per side is built from the config and torn down
    before this returns, honouring ``config.timeout`` (ADR-025).

    ``config.output`` is *not* used — ADR-007 requires the key, this function
    ignores it (ADR-028 §5). Write the result yourself:
    ``write_transcript(transcript, config.output)``.

    Raises ``DebateError`` if any phase fails (Hard Rule 1: nothing partial
    comes back), or ``BackendError`` if a server does.
    """
    if backends is not None:
        _check_backends(backends, config)
        return await _orchestrate(config, backends, events)
    async with open_client(config.timeout) as client:
        built = [OpenAICompatibleBackend(client, side.base_url, side.model) for side in config.sides]
        return await _orchestrate(config, built, events)


async def judge(
    transcript: Transcript,
    *,
    model: str,
    budget: int,
    base_url: str | None = None,
    backend: Backend | None = None,
    fact_check: bool = True,
    timeout: int = DEFAULT_READ_TIMEOUT,
) -> ScoreSheet:
    """Score a transcript, and audit its claims unless ``fact_check=False``.

    One call for the rubric and, when the fact-check is on, a second for the
    audit (ADR-015 §3). ``model`` is recorded in the sheet whichever backend
    runs, so an injected one should be passed the name it is really using.

    Pass ``base_url=`` to use the built-in adapter, or ``backend=`` for your
    own. Writes nothing: ``write_scores(sheet, path)`` does that.

    Raises ``JudgeError`` if the reply can't be parsed or overran its budget.
    """
    if backend is not None:
        return await _score(transcript, backend, model=model, budget=budget, fact_check=fact_check)
    if base_url is None:
        raise ValueError(
            "judge() has nowhere to send the call: pass base_url= to use the built-in "
            "openai-compatible adapter (e.g. 'http://localhost:11434/v1'), or backend= "
            "with your own implementation of the Backend protocol (ADR-009)"
        )
    async with open_client(timeout) as client:
        adapter = OpenAICompatibleBackend(client, base_url, model)
        return await _score(transcript, adapter, model=model, budget=budget, fact_check=fact_check)


async def _score(
    transcript: Transcript, backend: Backend, *, model: str, budget: int, fact_check: bool
) -> ScoreSheet:
    """The scoring call, then the fact-check call when it's on (ADR-015 §3)."""
    sheet = await _score_debate(
        transcript, backend, model=model, budget=budget, fact_check_enabled=fact_check
    )
    if not fact_check:
        return sheet
    checked = await _fact_check_debate(transcript, backend, budget=budget)
    return _replace(sheet, fact_check=checked)


def _check_backends(backends: _Sequence[Backend], config: RunConfig) -> None:
    """Caught here, not as an IndexError three turns into a run (Hard Rule 1)."""
    if len(backends) != len(config.sides):
        raise ValueError(
            f"debate() was given {len(backends)} backend(s) for {len(config.sides)} sides; "
            "pass one per side, in side-index order — backends[side.index] is the one "
            "each side speaks through"
        )
