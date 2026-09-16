"""The ``judge`` command: a transcript in, a score file out (ADR-007, ADR-013).

Takes either a ``run.yaml`` with a ``judge:`` block or a transcript plus flags
(ADR-020 §3), told apart by extension. Flags override the file, so a one-off
change needs no edit. ADR-007 gave this command flags alone, when it had one;
it has four, and ADR-020 records why that reversed. Nothing but the score JSON
goes to the file; everything the command says goes to stderr.

The scoring and fact-check calls are `api.judge` (ADR-028 §4); this module is
that function plus argv, the ADR-020 merge, stderr and an exit code.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

from collections import Counter

from .api import judge
from .backend import DEFAULT_READ_TIMEOUT
from .config import ConfigError, JudgeConfig, load_run
from .judging import VERDICTS, JudgeError, ScoreSheet, write_scores
from .transcript import TranscriptError, load_transcript


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="judge",
        description="Score a debate transcript against the rubric. Five dimensions per "
        "side, never blended; the winner is arithmetic, not a model's opinion.",
    )
    parser.add_argument(
        "target",
        metavar="run.yaml | transcript.json",
        help="a run.yaml carrying a judge: block, or a transcript debate wrote",
    )
    # Not argparse-required: a judge: block may supply them instead. Requiredness
    # is checked after the merge, so one parser serves both forms (ADR-020 §4).
    parser.add_argument("--model", help="the judging model, ideally neither debater")
    parser.add_argument("--base-url", help="the judging model's server (ADR-017)")
    parser.add_argument(
        "--budget",
        type=int,
        help="completion-token cap, applied to the scoring call and to the fact-check on its own",
    )
    parser.add_argument("--output", help="where to write the score file")
    parser.add_argument("--timeout", type=int, help="seconds to wait for a reply (default 600)")
    parser.add_argument(
        "--fact-check",
        dest="fact_check",
        action="store_true",
        default=None,
        help="audit each claim against the recorded evidence (the default; ADR-015)",
    )
    parser.add_argument(
        "--no-fact-check",
        dest="fact_check",
        action="store_false",
        help="score only, skipping the second call",
    )
    args = parser.parse_args(argv)

    try:
        transcript_path, settings = _settings(args)
    except ConfigError as e:
        _log(f"config error: {e}")
        return 1
    except _Missing as e:
        _log(str(e))
        return 1
    args.model, args.base_url, args.budget, args.fact_check, args.timeout = (
        settings.model,
        settings.base_url,
        settings.budget,
        settings.fact_check,
        settings.timeout,
    )

    if args.timeout < 1:
        _log(f"--timeout must be at least 1 second, got {args.timeout}")
        return 1

    if args.budget < 1:
        _log(f"--budget must be at least 1, got {args.budget}")
        return 1

    try:
        transcript = load_transcript(transcript_path)
    except TranscriptError as e:
        _log(f"transcript error: {e}")
        return 1

    output = settings.output
    # Checked before the call, so a missing directory can't waste a judging run.
    if not output.parent.is_dir():
        _log(f"the output directory does not exist: {output.parent}")
        return 1

    _log(f'judging {len(transcript.turns)} turns on {args.model}: "{transcript.run.topic}"')
    try:
        sheet = asyncio.run(
            judge(
                transcript,
                model=args.model,
                budget=args.budget,
                base_url=args.base_url,
                fact_check=args.fact_check,
                timeout=args.timeout,
            )
        )
    except JudgeError as e:
        _log(f"judging failed: {e}")
        return 1

    try:
        backup = write_scores(sheet, output)
    except OSError as e:
        _log(f"could not write the score file to {output}: {e}")
        return 1
    if backup is not None:
        _log(f"moved the previous score file to {backup.name}")
    _report(sheet)
    _log(f"wrote the score file to {output}")
    return 0


class _Missing(Exception):
    """A setting given by neither the command line nor a judge: block."""


def _settings(args: argparse.Namespace) -> tuple[Path, JudgeConfig]:
    """Merge a judge: block with the flags, the flags winning (ADR-020 §3, §4)."""
    target = Path(args.target).expanduser()
    block: JudgeConfig | None = None
    transcript_path = target

    if target.suffix in (".yaml", ".yml"):
        config = load_run(target)
        if config.judge is None:
            raise _Missing(
                f"{target} has no judge: block, so there is nothing to judge with. "
                "Add one (ADR-020), or name a transcript and pass --model, --base-url, "
                "--budget and --output"
            )
        block, transcript_path = config.judge, config.judge.transcript

    def pick(flag: object, field: str, cli: str) -> object:
        if flag is not None:
            return flag
        if block is not None:
            return getattr(block, field)
        raise _Missing(
            f"{cli} is required: this is a transcript, not a run.yaml, so no judge: "
            f"block supplies it. Pass {cli}, or run judge against a run.yaml that has "
            "a judge: block (ADR-020)"
        )

    return transcript_path, JudgeConfig(
        transcript=transcript_path,
        model=pick(args.model, "model", "--model"),
        base_url=pick(args.base_url, "base_url", "--base-url"),
        budget=pick(args.budget, "budget", "--budget"),
        output=Path(pick(args.output, "output", "--output")).expanduser(),
        fact_check=_fact_check(args.fact_check, block),
        # ADR-025 §2: flag, else the block's, else the default. Unlike the four
        # above it is never required — a transcript run with no block still has one.
        timeout=args.timeout if args.timeout is not None
        else (block.timeout if block is not None else DEFAULT_READ_TIMEOUT),
    )


def _fact_check(flag: bool | None, block: JudgeConfig | None) -> bool:
    """--fact-check/--no-fact-check, else the block's, else on (ADR-015 §3)."""
    if flag is not None:
        return flag
    return block.fact_check if block is not None else True


def _report(sheet: ScoreSheet) -> None:
    """Every dimension alongside the total, because the total alone explains nothing."""
    for side in sheet.sides:
        _log(f"side {side.side_index} ({side.side}): {side.total} of 100")
        for dimension in side.dimensions:
            _log(f"    {dimension.name}: {dimension.score} of {dimension.max}")
    verdict = "a draw" if sheet.winner == "draw" else f"{sheet.winner} wins"
    _log(f"{verdict} ({sheet.winner_reason.replace('_', ' ')})")
    if sheet.fact_check is not None:
        counts = Counter(claim.verdict for claim in sheet.fact_check.claims)
        tally = ", ".join(f"{counts[name]} {name}" for name in VERDICTS if counts[name])
        _log(f"fact-check: {len(sheet.fact_check.claims)} claims — {tally or 'none found'}")
        if sheet.fact_check.note:
            _log(f"    {sheet.fact_check.note}")


def _log(message: str) -> None:
    print(f"judge: {message}", file=sys.stderr)
