"""What each side is asked for, per phase (ADR-010 §2).

The debate so far goes into a single labelled user message rather than
alternating user/assistant messages: this tool talks to any openai-compatible
server, some published chat templates require strictly alternating roles (which
alternating initiative breaks), both sides get an identically shaped prompt this
way, and each turn needs a phase label that a chat role can't carry (ADR-010).
Standard library only (ADR-008).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from .backend import GenerationRequest, Message
from .transcript import Evidence, Turn

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


def build_request(
    topic: str,
    side: Side,
    phase: str,
    sides: tuple[Side, ...],
    turns: list[Turn],
    seed: int | None = None,
    length: str | None = None,
) -> GenerationRequest:
    instruction = PHASE_INSTRUCTIONS[phase]
    if length is not None:
        # Both sides get the same target for the same phase (ADR-016 §1).
        instruction += f" Answer in about {LENGTH_SENTENCES[length]} sentences."
    return GenerationRequest(
        messages=(
            Message("system", system_prompt(topic, side)),
            Message("user", f"{render_debate(sides, turns, side.index)}\n\n{instruction}"),
        ),
        max_completion_tokens=side.budget,
        seed=seed,
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
                f"{PHASE_INSTRUCTIONS['prep']}",
            ),
        ),
        max_completion_tokens=side.prep_budget,
        seed=seed,
    )


def system_prompt(topic: str, side: Side) -> str:
    """Who this side is and which way it argues — the same in every phase."""
    position = "for" if side.side == "pro" else "against"
    team = side.team
    return (
        f"You are {team.name}, a debater. Your outlook: {team.stance}. "
        f"Your voice: {team.voice}. What you value: {', '.join(team.values)}.\n\n"
        f"The motion is: {topic}\n"
        f"You argue {position} the motion, whatever your own view."
    )


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
