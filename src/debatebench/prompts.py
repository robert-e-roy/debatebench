"""What each side is asked for, per phase (ADR-010 §2).

The debate so far goes into a single labelled user message rather than
alternating user/assistant messages: this tool talks to any openai-compatible
server, some published chat templates require strictly alternating roles (which
alternating initiative breaks), both sides get an identically shaped prompt this
way, and each turn needs a phase label that a chat role can't carry (ADR-010).
Standard library only (ADR-008).
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .backend import GenerationRequest, Message
from .transcript import Evidence, PromptRecord, Turn

if TYPE_CHECKING:  # only for annotations: importing config here would pull in PyYAML
    from .config import Side

PHASE_INSTRUCTIONS = {
    "prep": (
        "Read the passages above and write your prep notes: the strongest arguments "
        "for your side, the evidence behind each one, and the passage id it came from. "
        "These notes are yours alone — the other side never sees them."
    ),
    "opening": "Give your opening statement: set out your case.",
    "rebuttal": (
        "Give your rebuttal. First state the other side's strongest argument fairly, in "
        "terms they would accept. Then answer it, and attack their other arguments."
    ),
    "retort": "Give your retort: answer the rebuttal aimed at your case, and defend your arguments.",
    "conclusion": "Give your conclusion: sum up why your side should win. Introduce no new arguments.",
}

# What a phase's :length suffix asks for (ADR-011 §2, carried over by ADR-016).
# A target stated in the prompt, not a cap: `budget` stays the hard ceiling.
LENGTH_SENTENCES = {"short": 2, "medium": 5, "long": 10}


@dataclass(frozen=True)
class Segment:
    """One fragment of a prompt and where it came from (ADR-036 §2).

    ``origin`` is for a human reading ``--show-prompt``: the file and key a
    fragment was written in, or ``built in`` for the sentences this module
    supplies. Joining every ``text`` reproduces the prompt **exactly** — that is
    what keeps the preview from drifting away from what is sent, and
    ``tests/test_show_prompt.py`` asserts it rather than trusting it.
    """

    text: str
    origin: str
    # ADR-037: the name this fragment fills when the prompt is read as a template.
    # None for text this module supplies, which is the same in every run — so
    # replacing every named slot leaves exactly debatebench's own contribution.
    slot: str | None = None


BUILT_IN = "built in"


def template(segments: Sequence[Segment]) -> str:
    """The prompt with every config value replaced by its ``{slot}`` (ADR-037).

    What is left is what ``debatebench`` supplies and a run cannot change, which
    is both what the fingerprint covers and what a tunable prompt file would hold.
    """
    return "".join(f"{{{s.slot}}}" if s.slot else s.text for s in segments)


def fingerprint(*parts: str) -> str:
    """A short digest over the prompt text this package contributes (ADR-037).

    Deliberately not a hash of the whole request: the debate so far differs
    between any two runs by construction, so that digest would always differ and
    could never answer "were these given the same instructions?".
    """
    digest = hashlib.blake2b(digest_size=8)
    for part in parts:
        digest.update(part.encode())
        digest.update(b"\0")  # so ("ab", "c") and ("a", "bc") cannot collide
    return digest.hexdigest()


def system_prompt_segments(topic: str, side: Side) -> tuple[Segment, ...]:
    """``system_prompt`` broken at every boundary between config and this module."""
    team = side.team
    where = side.team_file
    return (
        Segment("You are ", BUILT_IN),
        Segment(team.name, f"{where}  name:", slot="name"),
        Segment(", a debater. Your outlook: ", BUILT_IN),
        Segment(team.stance, f"{where}  stance:", slot="stance"),
        Segment(". Your voice: ", BUILT_IN),
        Segment(team.voice, f"{where}  voice:", slot="voice"),
        Segment(". What you value: ", BUILT_IN),
        Segment(", ".join(team.values), f"{where}  values:", slot="values"),
        Segment(".\n\nThe motion is: ", BUILT_IN),
        Segment(topic, "run.yaml  topic:", slot="topic"),
        Segment("\nYou argue ", BUILT_IN),
        # Not a setting: run.yaml says pro or con, and this module decides the word.
        Segment(
            "for" if side.side == "pro" else "against",
            f"{BUILT_IN}, from run.yaml side: {side.side}",
            slot="position",
        ),
        Segment(" the motion, whatever your own view.", BUILT_IN),
    )


def instruction_segments(phase: str, length: str | None) -> tuple[Segment, ...]:
    """The ask at the end of a turn's user message, fragment by fragment.

    Nothing here comes from a config file. A run.yaml chooses a phase *name* and
    a length *word*; both sentences below, and the number, are this module's.
    """
    segments = [Segment(PHASE_INSTRUCTIONS[phase], f'{BUILT_IN}: PHASE_INSTRUCTIONS["{phase}"]')]
    if length is not None:
        sentences = LENGTH_SENTENCES[length]
        segments.append(
            Segment(
                f" Answer in about {sentences} sentences.",
                f'{BUILT_IN}: LENGTH_SENTENCES["{length}"] = {sentences}, '
                f"asked for by the :{length} suffix",
            )
        )
    return tuple(segments)


def joined(segments: Sequence[Segment]) -> str:
    return "".join(segment.text for segment in segments)


def prompt_record(
    topic: str, side: Side, phases: Sequence[str], lengths: Sequence[str | None]
) -> PromptRecord:
    """What this module contributed to a run's prompts, for the transcript (ADR-037).

    ``side`` only supplies the shape: every value it carries is a ``{slot}`` in
    the template, so either side of a run yields the same record. A repeated
    phase label collapses to one entry, correctly — the same label is the same
    instruction.
    """
    system = template(system_prompt_segments(topic, side))
    instructions: dict[str, str] = {}
    for phase, length in zip(phases, lengths):
        label = phase if length is None else f"{phase}:{length}"
        instructions[label] = joined(instruction_segments(phase, length))
    ordered = tuple(instructions.items())
    return PromptRecord(
        fingerprint=fingerprint(system, *(f"{k}\n{v}" for k, v in ordered)),
        system=system,
        phases=ordered,
    )


def build_request(
    topic: str,
    side: Side,
    phase: str,
    sides: tuple[Side, ...],
    turns: list[Turn],
    seed: int | None = None,
    length: str | None = None,
) -> GenerationRequest:
    # Built from the same segments --show-prompt renders, so the preview cannot
    # describe a prompt this function does not send (ADR-036 §1). Both sides get
    # the same target for the same phase (ADR-016 §1).
    instruction = joined(instruction_segments(phase, length))
    return GenerationRequest(
        messages=(
            Message("system", system_prompt(topic, side)),
            Message("user", f"{render_debate(sides, turns, side.index)}\n\n{instruction}"),
        ),
        max_completion_tokens=side.budget,
        seed=seed,
        thinking=side.thinking,   # ADR-033, per side
    )


def build_prep_request(
    topic: str,
    side: Side,
    passages: Sequence[Evidence],
    seed: int | None = None,
) -> GenerationRequest:
    """Prep's one model call: turn the retrieved passages into this side's notes (ADR-012 §3).

    The passages reach the model only here. Afterwards only the notes travel
    forward, and only to this side (ADR-014 §2). The budget is ``prep_budget``,
    and ADR-011's ``length`` deliberately doesn't apply to prep.
    """
    if side.prep_budget is None:  # config guarantees this; a wrong caller shouldn't pass silently
        raise ValueError(f"side {side.index} has no prep_budget")
    rendered = "\n\n".join(
        f"[{passage.id} - {passage.source}]\n{passage.text.strip()}" for passage in passages
    )
    return GenerationRequest(
        messages=(
            Message("system", system_prompt(topic, side)),
            Message(
                "user",
                f"Your research, {len(passages)} passages:\n\n{rendered}\n\n"
                # Same segments --show-prompt renders; prep takes no length (ADR-016 §4).
                f"{joined(instruction_segments('prep', None))}",
            ),
        ),
        max_completion_tokens=side.prep_budget,
        seed=seed,
    )


def system_prompt(topic: str, side: Side) -> str:
    """Who this side is and which way it argues — the same in every phase."""
    return joined(system_prompt_segments(topic, side))


def render_debate(sides: tuple[Side, ...], turns: list[Turn], viewer_index: int) -> str:
    """Every turn ``viewer_index`` is entitled to see, in the order spoken.

    Prep is private (ADR-014 §2): a side sees its own prep notes and never the
    opponent's. ``viewer_index`` is required rather than defaulted, because a
    default is exactly how the opponent's prep would leak back in.
    """
    visible = [
        turn for turn in turns if turn.phase != "prep" or turn.side_index == viewer_index
    ]
    if not visible:
        return "Nothing has been said yet. You speak first."
    lines = ["The debate so far:", ""]
    for number, turn in enumerate(visible, start=1):
        speaker = sides[turn.side_index]
        label = "Your prep notes" if turn.phase == "prep" else (
            f"{turn.phase.capitalize()} - {speaker.side.upper()}, {speaker.team.name}"
        )
        lines.append(f"[{number}. {label}]")
        lines.append(turn.text.strip())
        lines.append("")
    return "\n".join(lines).strip()
