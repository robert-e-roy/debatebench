"""The ``judge`` command: a transcript in, a score file out (ADR-007, ADR-013).

Flags rather than a config file, because the same transcript gets re-judged with
different settings (ADR-007, "CLI invocation"). Nothing but the score JSON goes
to the file; everything the command says goes to stderr.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

from collections import Counter
from dataclasses import replace

from .judging import (
    VERDICTS,
    JudgeError,
    ScoreSheet,
    fact_check_debate,
    score_debate,
    write_scores,
)
from .openai_compat import OpenAICompatibleBackend, open_client
from .transcript import Transcript, TranscriptError, load_transcript


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="judge",
        description="Score a debate transcript against the rubric. Five dimensions per "
        "side, never blended; the winner is arithmetic, not a model's opinion.",
    )
    parser.add_argument("transcript", metavar="transcript.json", help="a transcript debate wrote")
    parser.add_argument("--model", required=True, help="the judging model, ideally neither debater")
    parser.add_argument("--base-url", required=True, help="the judging model's server (ADR-017)")
    parser.add_argument(
        "--budget",
        required=True,
        type=int,
        help="completion-token cap, applied to the scoring call and to the fact-check on its own",
    )
    parser.add_argument("--output", required=True, help="where to write the score file")
    parser.add_argument(
        "--fact-check",
        dest="fact_check",
        action="store_true",
        default=True,
        help="audit each claim against the recorded evidence (the default; ADR-015)",
    )
    parser.add_argument(
        "--no-fact-check",
        dest="fact_check",
        action="store_false",
        help="score only, skipping the second call",
    )
    args = parser.parse_args(argv)

    if args.budget < 1:
        _log(f"--budget must be at least 1, got {args.budget}")
        return 1

    try:
        transcript = load_transcript(Path(args.transcript))
    except TranscriptError as e:
        _log(f"transcript error: {e}")
        return 1

    output = Path(args.output).expanduser()
    # Checked before the call, so a missing directory can't waste a judging run.
    if not output.parent.is_dir():
        _log(f"the output directory does not exist: {output.parent}")
        return 1

    _log(f"judging {len(transcript.turns)} turns on {args.model}")
    try:
        sheet = asyncio.run(_score(transcript, args))
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


async def _score(transcript: Transcript, args: argparse.Namespace) -> ScoreSheet:
    """The scoring call, then the fact-check call when it's on (ADR-015 §3)."""
    async with open_client() as client:
        backend = OpenAICompatibleBackend(client, args.base_url, args.model)
        sheet = await score_debate(
            transcript,
            backend,
            model=args.model,
            budget=args.budget,
            fact_check_enabled=args.fact_check,
        )
        if not args.fact_check:
            return sheet
        checked = await fact_check_debate(transcript, backend, budget=args.budget)
        return replace(sheet, fact_check=checked)


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
