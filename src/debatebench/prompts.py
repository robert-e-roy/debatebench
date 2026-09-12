"""What each side is asked for, per phase (ADR-010 §2).

The debate so far goes into a single labelled user message rather than
alternating user/assistant messages: this tool talks to any openai-compatible
server, some published chat templates require strictly alternating roles (which
alternating initiative breaks), both sides get an identically shaped prompt this
way, and each turn needs a phase label that a chat role can't carry (ADR-010).
Standard library only (ADR-008).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .backend import GenerationRequest, Message
from .transcript import Turn

if TYPE_CHECKING:  # only for annotations: importing config here would pull in PyYAML
    from .config import Side

PHASE_INSTRUCTIONS = {
    "opening": "Give your opening statement: set out your case.",
    "rebuttal": (
        "Give your rebuttal. First state the other side's strongest argument fairly, in "
        "terms they would accept. Then answer it, and attack their other arguments."
    ),
    "retort": "Give your retort: answer the rebuttal aimed at your case, and defend your arguments.",
    "conclusion": "Give your conclusion: sum up why your side should win. Introduce no new arguments.",
}


def build_request(
    topic: str,
    side: Side,
    phase: str,
    sides: tuple[Side, ...],
    turns: list[Turn],
    seed: int | None = None,
) -> GenerationRequest:
    position = "for" if side.side == "pro" else "against"
    team = side.team
    system = (
        f"You are {team.name}, a debater. Your outlook: {team.stance}. "
        f"Your voice: {team.voice}. What you value: {', '.join(team.values)}.\n\n"
        f"The motion is: {topic}\n"
        f"You argue {position} the motion, whatever your own view."
    )
    return GenerationRequest(
        messages=(
            Message("system", system),
            Message("user", f"{render_debate(sides, turns)}\n\n{PHASE_INSTRUCTIONS[phase]}"),
        ),
        max_completion_tokens=side.budget,
        seed=seed,
    )


def render_debate(sides: tuple[Side, ...], turns: list[Turn]) -> str:
    """Every turn so far, in the order spoken, labelled by phase and side."""
    if not turns:
        return "Nothing has been said yet. You speak first."
    lines = ["The debate so far:", ""]
    for number, turn in enumerate(turns, start=1):
        speaker = sides[turn.side_index]
        lines.append(
            f"[{number}. {turn.phase.capitalize()} - "
            f"{speaker.side.upper()}, {speaker.team.name}]"
        )
        lines.append(turn.text.strip())
        lines.append("")
    return "\n".join(lines).strip()
