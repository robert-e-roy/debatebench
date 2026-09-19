"""B6: the fact-check pass inside `judge` (ADR-015).

Checked against the record — both sides' evidence and turns — never against the
model's own knowledge. A verdict that cites nothing checkable is refused.
"""

import asyncio
import json
from pathlib import Path

import pytest

from debatebench.judging import (
    BUDGET_TOLERANCE,
    CHECKED_AGAINST,
    VERDICTS,
    FactCheck,
    JudgeError,
    build_fact_check_request,
    fact_check_debate,
    write_scores,
)
from fakes import FakeBackend, reply
from test_judging import debated, judged, judge_reply, side
from test_prep import prep_debate

CITED = ("am-1",)  # a passage the pro side actually retrieves in the fixture pool


def claim(
    turn: int = 3,
    text: str = "Brindlewick cut household emissions by 14 percent.",
    verdict: str = "supported",
    evidence_ids=None,
) -> dict:
    """One audit entry. The wire shape cites the turn number the rendering
    prints; the coordinates are mapped back in code, so a model never has to
    transcribe phase_index and side_index — the field it kept mangling."""
    if evidence_ids is None:
        evidence_ids = CITED if verdict in ("supported", "contradicted") else ()
    return {
        "turn": turn,
        "claim": text,
        "verdict": verdict,
        "evidence_ids": list(evidence_ids),
    }


def claims_reply(*claims: dict) -> str:
    return json.dumps({"claims": list(claims)})


def checked(transcript, text: str, *, budget: int = 4000, completion_tokens: int = 300):
    backend = FakeBackend(reply(text, completion_tokens=completion_tokens))
    return asyncio.run(fact_check_debate(transcript, backend, budget=budget)), backend


# --- the ledger it produces ---------------------------------------------------


def test_a_claim_traces_to_the_passage_that_backs_it(run_dir: Path, prepared_sources):
    _, transcript, _ = prep_debate(run_dir)
    audit, _ = checked(transcript, claims_reply(claim()))

    (entry,) = audit.claims
    assert audit.checked_against == CHECKED_AGAINST  # the record, never "the world"
    assert (entry.verdict, entry.evidence_ids) == ("supported", CITED)
    assert audit.note is None


def test_a_claim_can_be_contradicted_by_the_opponents_evidence(run_dir: Path, prepared_sources):
    # The finding prep_grounded can never produce, and the reason this pass exists.
    _, transcript, _ = prep_debate(run_dir)
    audit, _ = checked(
        transcript,
        claims_reply(claim(verdict="contradicted", evidence_ids=("am-5",))),  # a con-side passage
    )

    (entry,) = audit.claims
    assert (entry.verdict, entry.evidence_ids) == ("contradicted", ("am-5",))


def test_a_turn_number_maps_back_to_its_coordinates(run_dir: Path, prepared_sources):
    # The whole point of citing a turn number: the model never transcribes
    # phase_index/side_index, but the recorded claim still carries them.
    _, transcript, _ = prep_debate(run_dir)
    expected = list(enumerate(transcript.turns, start=1))

    audit, _ = checked(transcript, claims_reply(claim(turn=3), claim(turn=4)))

    third, fourth = dict(expected)[3], dict(expected)[4]
    assert [(c.phase_index, c.side_index) for c in audit.claims] == [
        (third.phase_index, third.side_index),
        (fourth.phase_index, fourth.side_index),
    ]
    # And they are genuinely different turns, or this would pass vacuously.
    assert (third.phase_index, third.side_index) != (fourth.phase_index, fourth.side_index)


def test_the_audit_is_a_second_call_with_its_own_budget(run_dir: Path, prepared_sources):
    _, transcript, _ = prep_debate(run_dir)
    _, backend = checked(transcript, claims_reply(claim()), budget=1234)

    assert len(backend.requests) == 1  # one call per audit; the scoring call is separate
    assert backend.requests[0].max_completion_tokens == 1234
    assert backend.requests[0].seed == transcript.run.seed


def test_the_prompt_lists_the_ids_it_may_cite(run_dir: Path, prepared_sources):
    _, transcript, _ = prep_debate(run_dir)
    system = build_fact_check_request(transcript, 4000).messages[0].content

    assert "am-1" in system
    assert "Never treat your own knowledge as proof" in system


def test_the_prompt_states_that_contradiction_wins(run_dir: Path, prepared_sources):
    # ADR-019 §1. This asserts what we *send*, never what a model returns: §3 of
    # that ADR is explicit that precedence cannot be enforced in code, since
    # deciding whether a passage backs or refutes a claim is entailment and
    # ADR-008 fixes the runtime at httpx + PyYAML. What is testable is that the
    # instruction is still in the prompt, so it can't be dropped by accident.
    _, transcript, _ = prep_debate(run_dir)
    system = build_fact_check_request(transcript, 4000).messages[0].content

    assert "CONTRADICTION WINS" in system
    assert "even when another passage backs it" in system
    # supported must carry its narrowed meaning, or the rule is only half stated.
    assert "no recorded passage" in system and "contradicts it" in system


# --- a transcript with nothing recorded (ADR-015 §2) -------------------------


def test_without_evidence_every_claim_is_not_checkable(run_dir: Path):
    # Not "unsupported": nothing was recorded, so nothing could bear on it.
    _, transcript = debated(run_dir)
    audit, _ = checked(
        transcript,
        claims_reply(claim(verdict="unsupported"), claim(verdict="not_checkable")),
    )

    assert [entry.verdict for entry in audit.claims] == ["not_checkable", "not_checkable"]
    assert audit.note and "no prep evidence" in audit.note


def test_without_evidence_the_prompt_says_so(run_dir: Path):
    _, transcript = debated(run_dir)
    system = build_fact_check_request(transcript, 4000).messages[0].content

    assert "Nothing was recorded to check against" in system
    assert "Cite no ids at all" in system  # or it invents them from the turn numbering


def test_without_evidence_invented_citations_do_not_abort_the_run(run_dir: Path):
    # Measured against vllm-mlx: with nothing recorded, the judge cited '1'..'6',
    # the turn numbers from the rendering. Those ids are discarded anyway
    # (ADR-015 §2), so refusing them would fail a run over nothing.
    _, transcript = debated(run_dir)
    audit, _ = checked(
        transcript,
        claims_reply(claim(verdict="supported", evidence_ids=("1", "2", "3"))),
    )

    (entry,) = audit.claims
    assert (entry.verdict, entry.evidence_ids) == ("not_checkable", ())
    assert audit.note and "no prep evidence" in audit.note


# --- a malformed audit is an error, never a guess ----------------------------


BROKEN = [
    ("no claims list", lambda: json.dumps({"verdicts": []}), "has no claims list"),
    ("an unknown verdict", lambda: claims_reply(claim(verdict="probably true")),
     "verdict is 'probably true', not one of"),
    ("a claim with no text", lambda: claims_reply(claim(text="  ")), "has no claim text"),
    ("a turn number the transcript doesn't have", lambda: claims_reply(claim(turn=99)),
     r"cites turn 99, and this transcript has turns 1-4"),
    ("a turn number that isn't a number", lambda: claims_reply(claim(turn="second")),
     r"cites turn 'second', and this transcript has turns 1-4"),
    ("a passage the transcript never recorded", lambda: claims_reply(claim(evidence_ids=("am-99",))),
     "cites 'am-99', which the transcript never recorded"),
    ("supported but citing nothing", lambda: claims_reply(claim(evidence_ids=())),
     "is supported but cites no passage"),
    ("unsupported but citing a passage",
     lambda: claims_reply(claim(verdict="unsupported", evidence_ids=CITED)),
     "is unsupported but cites 1 passage"),
    ("evidence_ids that aren't ids", lambda: claims_reply(claim(evidence_ids=[7])),
     "not a list of ids"),
]


@pytest.mark.parametrize("make, expected", [case[1:] for case in BROKEN],
                         ids=[case[0] for case in BROKEN])
def test_a_malformed_audit_fails_the_run(run_dir: Path, prepared_sources, make, expected):
    _, transcript, _ = prep_debate(run_dir)
    with pytest.raises(JudgeError, match=expected):
        checked(transcript, make())


def test_an_audit_over_its_budget_fails(run_dir: Path, prepared_sources):
    _, transcript, _ = prep_debate(run_dir)
    with pytest.raises(JudgeError, match="over the 16-token tolerance"):
        checked(transcript, claims_reply(claim()), budget=100,
                completion_tokens=100 + BUDGET_TOLERANCE + 1)


def test_every_verdict_in_the_vocabulary_is_accepted(run_dir: Path, prepared_sources):
    _, transcript, _ = prep_debate(run_dir)
    audit, _ = checked(
        transcript, claims_reply(*[claim(verdict=verdict) for verdict in VERDICTS])
    )

    assert [entry.verdict for entry in audit.claims] == list(VERDICTS)


# --- how it reaches the score file -------------------------------------------


def test_the_section_is_written_beside_the_scores(run_dir: Path, prepared_sources):
    from dataclasses import replace

    _, transcript, _ = prep_debate(run_dir)
    sheet, _ = judged(transcript, judge_reply(side(0), side(1)))
    audit, _ = checked(transcript, claims_reply(claim()))
    output = run_dir / "score.json"

    write_scores(replace(sheet, fact_check=audit, fact_check_enabled=True), output)
    document = json.loads(output.read_text(encoding="utf-8"))

    assert document["schema_version"] == 3
    assert document["fact_check"]["checked_against"] == "recorded_evidence"
    (entry,) = document["fact_check"]["claims"]
    assert entry["verdict"] == "supported" and entry["evidence_ids"] == ["am-1"]
    assert document["sides"]  # the scores are untouched by the audit


def test_a_note_is_written_when_there_was_nothing_to_check(run_dir: Path):
    from dataclasses import replace

    _, transcript = debated(run_dir)
    sheet, _ = judged(transcript, judge_reply(side(0), side(1)))
    audit = FactCheck(CHECKED_AGAINST, (), note="nothing recorded")
    output = run_dir / "score.json"

    write_scores(replace(sheet, fact_check=audit, fact_check_enabled=True), output)
    document = json.loads(output.read_text(encoding="utf-8"))

    assert document["fact_check"]["note"] == "nothing recorded"


# --- ADR-034: passages decide the verdict, turns are context ------------------


def test_the_prompt_says_passages_decide_the_verdict(run_dir: Path, prepared_sources):
    """ADR-034 §1. Only passages have ids, so only a passage yields a citation a
    reader can check."""
    _, transcript, _ = prep_debate(run_dir)
    system = build_fact_check_request(transcript, budget=4000).messages[0].content
    assert "A VERDICT IS DECIDED ONLY BY THE RETRIEVED PASSAGES" in system


def test_the_prompt_says_an_opposing_argument_is_not_a_contradiction(
    run_dir: Path, prepared_sources
):
    """The argument that decides ADR-034.

    In an adversarial debate the opponent always argued against the claim, so
    admitting a turn as grounds makes `contradicted` vacuous — every assertion
    on a contested motion would earn it.
    """
    _, transcript, _ = prep_debate(run_dir)
    system = build_fact_check_request(transcript, budget=4000).messages[0].content
    assert "is not a contradiction" in system
    assert "both sides always argue against each other" in system


def test_unsupported_is_named_as_the_verdict_for_an_argued_against_claim(
    run_dir: Path, prepared_sources
):
    # ADR-034 §1: the direction the change is expected to move verdicts.
    _, transcript, _ = prep_debate(run_dir)
    system = build_fact_check_request(transcript, budget=4000).messages[0].content
    assert "unsupported — not contradicted" in system


def test_turns_are_still_read(run_dir: Path, prepared_sources):
    """ADR-034 §2: a narrowing of what may JUSTIFY a verdict, not of what is read.

    The judge still needs every turn to know what a claim means and which turn
    made it.
    """
    _, transcript, _ = prep_debate(run_dir)
    request = build_fact_check_request(transcript, budget=4000)
    rendered = request.messages[1].content
    for turn in transcript.turns:
        if turn.text.strip():
            assert turn.text.strip()[:40] in rendered


def test_adr_019_precedence_survives(run_dir: Path, prepared_sources):
    # ADR-034 narrows the range ADR-019 operates over; it does not touch the rule.
    _, transcript, _ = prep_debate(run_dir)
    system = build_fact_check_request(transcript, budget=4000).messages[0].content
    assert "CONTRADICTION WINS" in system
