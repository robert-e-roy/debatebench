"""What each side is told, and what it can see (ADR-010 §1 and §2)."""

import asyncio
from pathlib import Path

from debatebench.orchestrator import run_debate
from debatebench.prompts import PHASE_INSTRUCTIONS, build_request
from fakes import FakeBackend
from test_orchestrator import configure


def test_system_message_states_the_side_and_persona(run_dir: Path):
    config = configure(run_dir, ("opening",))
    pro, con = config.sides

    pro_system = build_request(config.topic, pro, "opening", config.sides, []).messages[0].content
    con_system = build_request(config.topic, con, "opening", config.sides, []).messages[0].content

    assert "You argue for the motion" in pro_system
    assert "You argue against the motion" in con_system
    assert config.topic in pro_system
    assert pro.team.name in pro_system and pro.team.voice in pro_system
    assert "collective-action" in pro_system  # its values


def test_the_first_speaker_is_told_the_debate_is_empty(run_dir: Path):
    config = configure(run_dir, ("opening",))
    user = build_request(config.topic, config.sides[0], "opening", config.sides, []).messages[1].content

    assert "Nothing has been said yet" in user
    assert PHASE_INSTRUCTIONS["opening"] in user


def test_the_second_speaker_sees_the_first_speakers_turn(run_dir: Path):
    config = configure(run_dir, ("opening", "rebuttal"))
    pro, con = FakeBackend(auto="pro"), FakeBackend(auto="con")

    asyncio.run(run_debate(config, [pro, con]))

    opening_by_pro = "pro turn 1"
    second_turn_prompt = con.requests[0].messages[1].content
    assert opening_by_pro in second_turn_prompt
    assert "[1. Opening - PRO, Progressive Climate Advocate]" in second_turn_prompt


def test_later_phases_carry_the_whole_debate(run_dir: Path):
    config = configure(run_dir, ("opening", "rebuttal"))
    pro, con = FakeBackend(auto="pro"), FakeBackend(auto="con")

    asyncio.run(run_debate(config, [pro, con]))

    # Pro speaks last in the rebuttal, so its prompt holds all three earlier turns.
    last_prompt = pro.requests[-1].messages[1].content
    for text in ("pro turn 1", "con turn 1", "con turn 2"):
        assert text in last_prompt
    assert PHASE_INSTRUCTIONS["rebuttal"] in last_prompt


def test_rebuttal_asks_for_a_steelman(run_dir: Path):
    # Steelman fidelity is B5's tiebreaker, and this is where the passages come from.
    assert "strongest argument fairly" in PHASE_INSTRUCTIONS["rebuttal"]
    assert "no new arguments" in PHASE_INSTRUCTIONS["conclusion"].lower()


def test_the_request_carries_the_side_budget(run_dir: Path):
    config = configure(run_dir, ("opening",), budget=321)
    request = build_request(config.topic, config.sides[0], "opening", config.sides, [])
    assert request.max_completion_tokens == 321
