"""The ``debate`` command: one argument, the path to a run.yaml (ADR-007).

At B1 it loads and validates the config, then gets one dummy reply per side
through the backend seam. There's no phase loop yet (B2) and no transcript
(B3), so nothing is written to the output: path. Everything the command says
goes to stderr (Hard Rule 7).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence

from .backend import Backend, BackendError, GenerationRequest, GenerationResult, Message
from .config import ConfigError, RunConfig, Side, load_run
from .openai_compat import OpenAICompatibleBackend, open_client


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

    try:
        asyncio.run(_run(config))
    except BackendError as e:
        _log(f"backend error: {e}")
        return 1
    _log(f"B1 has no transcript yet; nothing was written to {config.output}")
    return 0


async def _run(config: RunConfig) -> None:
    async with open_client() as client:
        backends = [OpenAICompatibleBackend(client, s.base_url, s.model) for s in config.sides]
        await dummy_replies(config, backends)


async def dummy_replies(config: RunConfig, backends: Sequence[Backend]) -> list[GenerationResult]:
    """B1's end-to-end check: one reply per side, in side order, through the Protocol."""
    results = []
    for side, backend in zip(config.sides, backends, strict=True):
        try:
            result = await backend.generate(dummy_request(config.topic, side))
        except BackendError as e:
            raise BackendError(f"side {side.index} ({side.team.name}): {e}") from e
        _log_reply(side, result)
        results.append(result)
    return results


def dummy_request(topic: str, side: Side) -> GenerationRequest:
    """A placeholder prompt that proves the pipe works. Real prompts are B2's."""
    team = side.team
    return GenerationRequest(
        messages=(
            Message(
                "system",
                f"You are {team.name}, arguing the {team.stance} side of a debate. "
                f"Your voice: {team.voice}.",
            ),
            Message("user", f"Topic: {topic}\n\nState your position in one or two sentences."),
        ),
        max_completion_tokens=side.budget,
    )


def _log_reply(side: Side, result: GenerationResult) -> None:
    # B1 only reports an overshoot; what it means for the turn is ADR-003's open question.
    over = " (over budget)" if result.completion_tokens > side.budget else ""
    _log(
        f"side {side.index}, {side.team.name} ({side.model}): "
        f"{result.completion_tokens} of {side.budget} completion tokens{over}, "
        f"{result.prompt_tokens} prompt tokens, finish_reason {result.finish_reason}, "
        f"{result.latency_ms} ms"
    )
    for line in (result.text.strip() or "(empty reply)").splitlines():
        _log(f"  | {line}")


def _log(message: str) -> None:
    print(f"debate: {message}", file=sys.stderr)
