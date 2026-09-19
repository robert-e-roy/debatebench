"""``debate --show-prompt``: render what a run.yaml becomes, without running it (ADR-036).

A user writes four values in a team file and a word like ``rebuttal:medium``.
What the model receives is those values inside sentences this package supplies,
plus a phase instruction and a sentence count that appear in no file they wrote.
This module shows both halves, and says which is which.

Every string here comes from ``prompts``' own segment functions, so a preview
cannot describe a prompt that ``build_request`` would not send (ADR-036 §1).
What cannot be known before a run — the turns already spoken, the passages prep
will retrieve — is named as a slot rather than invented (ADR-036, "What it
cannot show honestly"). Standard library only (ADR-008).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from .orchestrator import speaking_order
from .prompts import Segment, instruction_segments, joined, system_prompt_segments

if TYPE_CHECKING:  # importing config here would pull in PyYAML (ADR-008 layering)
    from .config import RunConfig, Side

RULE = "─" * 72
HEAVY = "═" * 72

# Each slot the preview cannot fill, and why. Held here rather than inline so the
# wording that admits a limit is as reviewable as the wording that states a fact.
SPOKEN_SO_FAR = "built at run time from the turns already spoken"
RETRIEVED = "built at run time by prep's retrieval (ADR-012); --show-prompt runs none"


def render(config: RunConfig) -> str:
    """The whole preview, as one string the CLI prints to stdout."""
    out: list[str] = [
        f"run.yaml   {config.path}",
        f"motion     {config.topic}",
        f"phases     {', '.join(_phase_labels(config))}",
        f"seed       {config.seed}",
        "",
        "Values you wrote are marked with the file and key they came from.",
        "Everything marked 'built in' is supplied by debatebench and is not",
        "currently settable from a config file.",
    ]
    for side in config.sides:
        out += ["", HEAVY, f" side {side.index}  {side.side}  {side.team.name}  {side.model}", HEAVY]
        out += _system_block(config, side)
        for phase_index, phase in enumerate(config.phases):
            out += _user_block(config, side, phase_index, phase)
    return "\n".join(out)


def _phase_labels(config: RunConfig) -> list[str]:
    """``phases`` as run.yaml would write them, with ADR-022's implied medium shown."""
    return [
        phase if length is None else f"{phase}:{length}"
        for phase, length in zip(config.phases, config.lengths)
    ]


def _system_block(config: RunConfig, side: Side) -> list[str]:
    segments = system_prompt_segments(config.topic, side)
    return [
        "",
        "[system]   identical in every phase",
        RULE,
        joined(segments),
        RULE,
        *_provenance(segments),
    ]


def _user_block(config: RunConfig, side: Side, phase_index: int, phase: str) -> list[str]:
    length = config.lengths[phase_index]
    label = phase if length is None else f"{phase}:{length}"
    # Prep is not a turn order: both sides prep independently and neither sees the
    # other (ADR-014 §2-3), so naming an opener there would describe nothing.
    if phase == "prep":
        when = "both sides, independently"
    else:
        order = speaking_order(config, phase_index).index(side.index)
        when = f"speaks {'first' if order == 0 else 'second'}"
    header = (
        f"[user]     phase {phase_index + 1} of {len(config.phases)}  {label}  {when}  "
        f"budget {side.prep_budget if phase == 'prep' else side.budget}"
    )

    if phase == "prep":
        context: list[Segment] = [
            Segment(
                f"<your research: the passages retrieved for side {side.index} "
                f"({side.side}) from sources: {', '.join(config.sources)}>",
                RETRIEVED,
            )
        ]
    else:
        context = [Segment(_debate_so_far(config, side, phase_index), SPOKEN_SO_FAR)]

    instruction = instruction_segments(phase, length)
    body = "\n\n".join([joined(context), joined(instruction)])
    return ["", header, RULE, body, RULE, *_provenance((*context, *instruction))]


def _debate_so_far(config: RunConfig, side: Side, phase_index: int) -> str:
    """The turns this side will see, named exactly as ``render_debate`` labels them.

    Structural, not fabricated: the *text* of those turns cannot exist yet, but
    which turns they are, and in what order, follows from the phase list and
    ADR-010 §1's alternating opener. A side never sees the opponent's prep
    (ADR-014 §2), and that exclusion is visible here too.
    """
    lines: list[str] = []
    for earlier in range(phase_index + 1):
        phase = config.phases[earlier]
        for speaker_index in speaking_order(config, earlier):
            # The orchestrator appends a turn *after* taking it, so a side that
            # speaks second in a phase reads the first speaker's turn from that
            # same phase. Stop at this side's own turn, which has not happened.
            if earlier == phase_index and speaker_index == side.index:
                break
            if phase == "prep":
                if speaker_index != side.index:
                    continue  # the opponent's prep is private and never appears
                lines.append("Your prep notes")
            else:
                speaker = config.sides[speaker_index]
                lines.append(f"{phase.capitalize()} - {speaker.side.upper()}, {speaker.team.name}")
    if not lines:
        # Exact: this is the string render_debate emits for the first turn of a run.
        return "Nothing has been said yet. You speak first."
    numbered = "; ".join(f"{n}. {line}" for n, line in enumerate(lines, start=1))
    return f"<the debate so far, in the order spoken — {numbered}>"


def _provenance(segments: Sequence[Segment]) -> list[str]:
    """One line per fragment, in order, so 'which pieces are mine?' has an answer."""
    lines = ["where each piece comes from, in order"]
    width = min(max(len(_shown(s.text)) for s in segments), 46)
    for number, segment in enumerate(segments, start=1):
        lines.append(f"  {number:>2}  {_shown(segment.text):<{width}}  {segment.origin}")
    return lines


def _shown(text: str, limit: int = 46) -> str:
    """A fragment as one quoted line, elided in the middle so both ends stay legible."""
    flat = text.replace("\n", "\\n")
    if len(flat) > limit:
        keep = (limit - 3) // 2
        flat = f"{flat[:keep]}...{flat[-keep:]}"
    return f'"{flat}"'
