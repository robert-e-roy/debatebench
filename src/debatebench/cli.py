"""The ``debate`` command: one argument, the path to a run.yaml (ADR-007).

It runs every configured phase, then writes the transcript as JSON to the
`output:` path, rotating any file already there to `<output>.1` (ADR-005).
Nothing but that JSON goes to the file; everything the command says goes to
stderr (Hard Rule 7).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence

from .backend import BackendError
from .config import ConfigError, RunConfig, load_run
from .events import DebateEvent, EventBus, EventType
from .openai_compat import OpenAICompatibleBackend, open_client
from .orchestrator import DebateError, Transcript, run_debate
from .transcript import write_transcript


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="debate",
        description="Run a structured debate. Every setting, including the output path, "
        "comes from the run.yaml file.",
    )
    parser.add_argument("run_yaml", metavar="run.yaml", help="the run's config file")
    args = parser.parse_args(argv)

    try:
        config = load_run(args.run_yaml)
    except ConfigError as e:
        _log(f"config error: {e}")
        return 1
    if config.seed_generated:
        _log(f"run.yaml sets no seed; generated seed {config.seed}")
    # Checked before the debate, so a missing directory can't waste a whole run.
    if not config.output.parent.is_dir():
        _log(f"config error: the output directory does not exist: {config.output.parent}")
        return 1

    events = EventBus()
    events.subscribe(log_event)
    try:
        transcript = asyncio.run(_run(config, events))
    except (DebateError, BackendError) as e:
        _log(f"debate failed: {e}")
        return 1

    try:
        backup = write_transcript(transcript, config.output)
    except OSError as e:
        _log(f"could not write the transcript to {config.output}: {e}")
        return 1
    if backup is not None:
        _log(f"moved the previous transcript to {backup.name}")
    _log(f"wrote {len(transcript.turns)} turns over {len(config.phases)} phases to {config.output}")
    return 0


async def _run(config: RunConfig, events: EventBus) -> Transcript:
    async with open_client() as client:
        backends = [OpenAICompatibleBackend(client, s.base_url, s.model) for s in config.sides]
        return await run_debate(config, backends, events)


def log_event(event: DebateEvent) -> None:
    """The CLI's own view of a run, through the same seam a dashboard would use."""
    if event.type is EventType.PHASE_STARTED:
        _log(f"phase {event.phase_index}: {event.phase}")
    elif event.type is EventType.TURN_COMPLETED and event.turn is not None:
        turn = event.turn
        # B2 only reports a reply that reached its budget; ADR-010 keeps it a valid turn.
        capped = " (hit budget)" if turn.hit_budget else ""
        _log(
            f"  side {turn.side_index}, spoke {'first' if turn.order == 0 else 'second'}: "
            f"{turn.usage.completion_tokens} of {turn.budget} completion tokens{capped}, "
            f"{turn.usage.prompt_tokens} prompt tokens, {turn.latency_ms} ms"
        )
        for line in turn.text.strip().splitlines():
            _log(f"    | {line}")


def _log(message: str) -> None:
    print(f"debate: {message}", file=sys.stderr)
