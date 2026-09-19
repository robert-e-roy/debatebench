"""The ``debate`` command: a run.yaml, plus ADR-021's override flags.

It runs every configured phase, then writes the transcript as JSON to the
`output:` path, rotating any file already there to `<output>.1` (ADR-005).
Nothing but that JSON goes to the file; everything the command says goes to
stderr (Hard Rule 7).

`--model` and `--budget` override the file for one run, so an A/B needs no
second config (ADR-021). They change the loaded config before anything runs,
which is what keeps the transcript's snapshot a record of what actually spoke.

The run itself is `api.debate` (ADR-028 §4): this module is that function plus
argv, stderr and an exit code, so a library caller and this command cannot get
different behaviour out of the same config.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from .api import debate
from .backend import BackendError
from .config import ConfigError, RunConfig, Side, load_run
from .event_stream import make_event_writer
from .events import DebateEvent, EventBus, EventType, Listener
from .orchestrator import DebateError
from .preview import render as render_prompts
from .transcript import write_transcript


def _parser() -> argparse.ArgumentParser:
    """One definition of the flags, so tests pin the names the CLI really uses."""
    parser = argparse.ArgumentParser(
        prog="debate",
        description="Run a structured debate. Every setting, including the output path, "
        "comes from the run.yaml file; --model and --budget override it for one run.",
    )
    parser.add_argument("run_yaml", metavar="run.yaml", help="the run's config file")
    # ADR-021: model and budget only. Nothing else is overridable, on purpose —
    # see its §6 for why output, seed, base_url and topic are not.
    parser.add_argument("--model", help="override both sides' model for this run")
    parser.add_argument("--budget", type=int, help="override both sides' per-phase cap")
    parser.add_argument("--pro-model", help="override only the pro side's model")
    parser.add_argument("--con-model", help="override only the con side's model")
    parser.add_argument("--pro-budget", type=int, help="override only the pro side's cap")
    parser.add_argument("--con-budget", type=int, help="override only the con side's cap")
    # ADR-025 §5: not an experimental variable — it cannot change a token of the
    # output, only whether the output arrives, so it sits outside ADR-021's list.
    parser.add_argument("--timeout", type=int, help="seconds to wait for a reply (default 600)")
    # ADR-027: a machine-readable view on the one stream this command leaves free.
    parser.add_argument(
        "--events",
        action="store_true",
        help="stream one JSON object per event to stdout, for another program to read",
    )
    # ADR-036: not an override (ADR-021) — it runs nothing, so it can change nothing.
    parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="print the prompts this run would send, with each piece's origin, and exit "
        "without calling a model or writing a file",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    try:
        config = load_run(args.run_yaml)
    except ConfigError as e:
        _log(f"config error: {e}")
        return 1
    try:
        config, overrides = _overridden(config, args)
    except _OverrideError as e:
        _log(str(e))
        return 1
    for line in overrides:
        _log(line)
    if config.seed_generated:
        _log(f"run.yaml sets no seed; generated seed {config.seed}")

    if args.show_prompt:
        # After the overrides, so the preview is of what would actually run, and
        # before the output-directory check, which is about writing a transcript
        # this path never writes (ADR-036 §3).
        if args.events:
            _log(
                "--show-prompt and --events cannot be combined: --show-prompt runs no "
                "debate, so there are no events to stream, and both write to stdout. "
                "Drop --events to see the prompts, or --show-prompt to run"
            )
            return 1
        _log("--show-prompt: rendering only; no model is called and no file is written")
        print(render_prompts(config))
        return 0

    # Checked before the debate, so a missing directory can't waste a whole run.
    if not config.output.parent.is_dir():
        _log(f"config error: the output directory does not exist: {config.output.parent}")
        return 1

    events = EventBus()
    events.subscribe(make_log_event(tuple(side.side for side in config.sides)))
    if args.events:
        # stdout, which Hard Rule 7 left free by putting the transcript in a named
        # file rather than a redirect. The stderr log is unaffected (ADR-027 §1).
        events.subscribe(make_event_writer(config))
    try:
        transcript = asyncio.run(debate(config, events=events))
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


class _OverrideError(Exception):
    """An override flag that can't be used as given (ADR-021)."""


def _overridden(
    config: RunConfig, args: argparse.Namespace
) -> tuple[RunConfig, tuple[str, ...]]:
    """Apply ADR-021's override flags, before anything runs.

    Overriding the *config* rather than the backend call is what keeps ADR-005's
    snapshot honest: the transcript records the model that actually spoke, never
    the one the file happened to name.
    """
    one_side = {
        "model": {"pro": args.pro_model, "con": args.con_model},
        "budget": {"pro": args.pro_budget, "con": args.con_budget},
    }
    both = {"model": args.model, "budget": args.budget}

    # ADR-021 §4: no precedence rule, because any would discard something asked for.
    for setting, shared in both.items():
        if shared is None:
            continue
        clashing = [f"--{s}-{setting}" for s, v in one_side[setting].items() if v is not None]
        if clashing:
            raise _OverrideError(
                f"--{setting} sets both sides and {' and '.join(clashing)} sets one; "
                f"they conflict (ADR-021 §4). Drop one: --{setting} alone for a symmetric "
                f"change, or --pro-{setting}/--con-{setting} alone for an asymmetric one"
            )

    changed: list[str] = []
    sides: list[Side] = []
    for side in config.sides:
        values: dict[str, Any] = {}
        for setting in ("model", "budget"):
            picked = one_side[setting][side.side]
            flag = f"--{side.side}-{setting}" if picked is not None else f"--{setting}"
            new = picked if picked is not None else both[setting]
            if new is None:
                continue
            _validate_override(setting, new, flag)
            was = getattr(side, setting)
            if new == was:
                continue
            values[setting] = new
            changed.append(
                f"{flag}: side {side.index} ({side.side}) {setting} {was!r} -> {new!r}"
            )
        sides.append(replace(side, **values) if values else side)

    return replace(config, sides=(sides[0], sides[1])), tuple(changed)


def _validate_override(setting: str, value: Any, flag: str) -> None:
    """ADR-021 §5: a flag faces the check its file key does, named for the flag."""
    if setting == "budget" and value < 1:
        raise _OverrideError(f"{flag} must be an integer of at least 1, got {value}")
    if setting == "model" and not value.strip():
        raise _OverrideError(f"{flag} must be a non-empty model name")


def make_log_event(labels: tuple[str, ...]) -> Listener:
    """The CLI's own view of a run, through the same seam a dashboard would use.

    ``labels`` is each side's ``pro``/``con`` from run.yaml (ADR-007 §7). A bare
    index makes the reader hold the mapping in their head for the whole run, so a
    turn names its side the way ``judge`` already does: ``side 0 (pro)``.
    """

    def log_event(event: DebateEvent) -> None:
        if event.type is EventType.PHASE_STARTED:
            _log(f"phase {event.phase_index}: {event.phase}")
        elif event.type is EventType.TURN_COMPLETED and event.turn is not None:
            turn = event.turn
            # B2 only reports a reply that reached its budget; ADR-010 keeps it a valid turn.
            capped = " (hit budget)" if turn.hit_budget else ""
            _log(
                f"  side {turn.side_index} ({labels[turn.side_index]}), "
                f"spoke {'first' if turn.order == 0 else 'second'}: "
                f"{turn.usage.completion_tokens} of {turn.budget} completion tokens{capped}, "
                f"{turn.usage.prompt_tokens} prompt tokens, {turn.latency_ms} ms"
            )
            for line in turn.text.strip().splitlines():
                _log(f"    | {line}")

    return log_event


def _log(message: str) -> None:
    print(f"debate: {message}", file=sys.stderr)
