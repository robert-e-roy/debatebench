"""ADR-036: `debate --show-prompt` renders what a run.yaml becomes, and runs nothing.

The load-bearing tests here are the two that pin the preview to reality: the
segments must rejoin to the prompt that is actually sent, and the described
"debate so far" must name the turns ``render_debate`` really shows. A preview
that can drift from the request is worse than no preview (ADR-036 §1).
"""

from pathlib import Path

import pytest

from debatebench import preview
from debatebench.cli import main
from debatebench.orchestrator import speaking_order
from debatebench.prompts import (
    build_request,
    instruction_segments,
    joined,
    render_debate,
    system_prompt,
    system_prompt_segments,
)
from debatebench.transcript import Turn, Usage
from test_orchestrator import configure

ALL_PHASES = ("prep", "opening", "rebuttal", "retort", "rebuttal", "conclusion")


def _turn(phase_index, phase, side_index, order, text):
    return Turn(
        phase_index=phase_index,
        phase=phase,
        side_index=side_index,
        order=order,
        text=text,
        usage=Usage(prompt_tokens=1, completion_tokens=1),
        budget=2000,
        hit_budget=False,
        finish_reason="stop",
        latency_ms=1,
        started_at="2026-09-19T00:00:00Z",
    )


# --- the preview cannot describe a prompt that is not sent -------------------


def test_system_prompt_segments_rejoin_to_the_prompt_actually_sent(run_dir: Path):
    config = configure(run_dir, ALL_PHASES)
    for side in config.sides:
        segments = system_prompt_segments(config.topic, side)
        assert joined(segments) == system_prompt(config.topic, side)


def test_system_segments_rejoin_to_the_request_a_turn_really_builds(run_dir: Path):
    config = configure(run_dir, ALL_PHASES)
    for side in config.sides:
        request = build_request(config.topic, side, "opening", config.sides, [], length="medium")
        assert request.messages[0].content == joined(system_prompt_segments(config.topic, side))


def test_instruction_segments_rejoin_to_the_user_message_tail(run_dir: Path):
    config = configure(run_dir, ALL_PHASES)
    side = config.sides[0]
    for phase, length in (("opening", "medium"), ("conclusion", "short"), ("rebuttal", "long")):
        request = build_request(config.topic, side, phase, config.sides, [], length=length)
        assert request.messages[1].content.endswith(joined(instruction_segments(phase, length)))


def test_the_values_a_user_wrote_are_all_attributed(run_dir: Path):
    config = configure(run_dir, ALL_PHASES)
    side = config.sides[0]
    attributed = {
        s.text: s.origin for s in system_prompt_segments(config.topic, side) if "built in" not in s.origin
    }
    assert attributed[side.team.name].endswith("name:")
    assert attributed[side.team.stance].endswith("stance:")
    assert attributed[side.team.voice].endswith("voice:")
    assert attributed[config.topic] == "run.yaml  topic:"


# --- the described "debate so far" is the one render_debate really produces ---


@pytest.mark.parametrize("swap_sides", [False, True])
def test_described_context_matches_what_render_debate_shows(run_dir: Path, swap_sides: bool):
    """Replay the run's turn order and check the preview named exactly those turns.

    Swapping which team is pro also swaps the opener (ADR-010 §1), so this covers
    the alternation rather than one fixed arrangement.
    """
    config = configure(run_dir, ALL_PHASES, swap_sides=swap_sides)
    turns: list[Turn] = []
    for phase_index, phase in enumerate(config.phases):
        for order, side_index in enumerate(speaking_order(config, phase_index)):
            side = config.sides[side_index]
            real = render_debate(config.sides, turns, side_index)
            described = preview._debate_so_far(config, side, phase_index)

            if not turns or real == "Nothing has been said yet. You speak first.":
                assert described == real
            else:
                # render_debate labels each visible turn "[n. label]"; the preview
                # promises those same labels, in that order, and nothing else.
                labels = [
                    line[line.index(". ") + 2 : -1]
                    for line in real.splitlines()
                    if line.startswith("[") and line.endswith("]")
                ]
                for label in labels:
                    assert label in described, (label, described)
                assert described.count(";") == max(len(labels) - 1, 0)

            turns.append(_turn(phase_index, phase, side_index, order, f"turn {len(turns)}"))


def test_a_side_is_never_told_it_will_see_the_opponents_prep(run_dir: Path):
    # ADR-014 §2: prep is private, and the preview must not imply otherwise.
    config = configure(run_dir, ALL_PHASES)
    for side in config.sides:
        for phase_index in range(1, len(config.phases)):
            described = preview._debate_so_far(config, side, phase_index)
            assert described.count("prep notes") == 1
            assert "Prep - " not in described


# --- the flag itself ---------------------------------------------------------


def test_show_prompt_writes_nothing_and_exits_zero(run_dir: Path, capsys):
    config_path = run_dir / "run.yaml"
    configure(run_dir, ALL_PHASES)
    assert main([str(config_path), "--show-prompt"]) == 0
    # Hard Rule 7's file is untouched: --show-prompt runs no debate.
    assert not (run_dir / "transcript.json").exists()
    out = capsys.readouterr()
    assert "no model is called and no file is written" in out.err
    assert "[system]" in out.out and "where each piece comes from" in out.out


def test_show_prompt_needs_no_server(run_dir: Path, capsys):
    # base_url points at a port nothing is listening on; rendering must not care.
    configure(run_dir, ALL_PHASES)
    assert main([str(run_dir / "run.yaml"), "--show-prompt"]) == 0


def test_show_prompt_refuses_events(run_dir: Path, capsys):
    configure(run_dir, ALL_PHASES)
    assert main([str(run_dir / "run.yaml"), "--show-prompt", "--events"]) == 1
    assert "cannot be combined" in capsys.readouterr().err


def test_show_prompt_reflects_an_override(run_dir: Path, capsys):
    # ADR-036 §3: the preview is of what would run, so it must apply ADR-021 first.
    configure(run_dir, ALL_PHASES)
    assert main([str(run_dir / "run.yaml"), "--pro-model", "some-other-model", "--show-prompt"]) == 0
    assert "some-other-model" in capsys.readouterr().out


def test_show_prompt_shows_the_length_a_bare_phase_resolved_to(run_dir: Path, capsys):
    # ADR-022: a bare entry asks for medium. The user never wrote "medium" or "5".
    configure(run_dir, ("opening", "conclusion:short"))
    assert main([str(run_dir / "run.yaml"), "--show-prompt"]) == 0
    out = capsys.readouterr().out
    assert "opening:medium" in out
    assert "Answer in about 5 sentences." in out
    assert 'LENGTH_SENTENCES["medium"] = 5' in out
    assert "Answer in about 2 sentences." in out


def test_show_prompt_marks_what_it_cannot_know(run_dir: Path, capsys):
    """ADR-036: prep's passages and later turns are slots, never invented text."""
    configure(run_dir, ALL_PHASES)
    assert main([str(run_dir / "run.yaml"), "--show-prompt"]) == 0
    out = capsys.readouterr().out
    assert preview.RETRIEVED in out
    assert preview.SPOKEN_SO_FAR in out
