"""B5: scoring a transcript — parsing, aggregation, the winner, the score file."""

import asyncio
import json
from pathlib import Path

import pytest

from debatebench.judging import (
    BUDGET_TOLERANCE,
    DIMENSIONS,
    JudgeError,
    build_request,
    parse_reply,
    render,
    score_debate,
    write_scores,
)
from debatebench.orchestrator import run_debate
from fakes import FakeBackend, reply
from test_orchestrator import configure, fakes
from test_prep import prep_debate

# 24 + 18 + 15 + 11 + 8 = 76, comfortably inside every dimension's range.
DEFAULTS = {
    "argument_quality": 24,
    "evidence_grounding": 18,
    "steelman_fidelity": 15,
    "rebuttal_effectiveness": 11,
    "clarity": 8,
}
LEDGER = [{"point": "carbon tax regressivity", "status": "rebutted"}]


def side(index: int, ledger=None, **overrides) -> dict:
    body = {"side_index": index}
    for name, score in {**DEFAULTS, **overrides}.items():
        body[name] = {"score": score, "justification": f"scored {name} this way because…"}
    body["rebuttal_effectiveness"]["hit_ledger"] = LEDGER if ledger is None else ledger
    return body


def judge_reply(*sides: dict) -> str:
    return json.dumps({"sides": list(sides)})


def debated(run_dir: Path, phases=("opening", "rebuttal")):
    config = configure(run_dir, phases)
    return config, asyncio.run(run_debate(config, fakes()))


def judged(transcript, text: str, *, budget: int = 4000, completion_tokens: int = 400):
    backend = FakeBackend(reply(text, completion_tokens=completion_tokens))
    sheet = asyncio.run(
        score_debate(transcript, backend, model="judge-model", budget=budget)
    )
    return sheet, backend


# --- the one call, and what it carries ---------------------------------------


def test_the_judge_is_asked_once_for_both_sides(run_dir: Path):
    # ADR-013 §2: one call, whole transcript, both sides scored from one read.
    _, transcript = debated(run_dir)
    _, backend = judged(transcript, judge_reply(side(0), side(1)))

    assert len(backend.requests) == 1
    assert backend.requests[0].max_completion_tokens == 4000


def test_the_call_carries_the_transcripts_seed(run_dir: Path):
    # Re-judging one transcript is reproducible (ADR-015 §6).
    _, transcript = debated(run_dir)
    _, backend = judged(transcript, judge_reply(side(0), side(1)))

    assert backend.requests[0].seed == transcript.run.seed == 42


def test_the_judge_sees_both_sides_prep_evidence(run_dir: Path, prepared_sources):
    # Prep privacy binds debaters, not the judge (ADR-015 §5).
    _, transcript, _ = prep_debate(run_dir)
    rendered = render(transcript)

    assert "Brindlewick" in rendered  # pro's evidence
    assert "Ferncastle" in rendered  # con's evidence


def test_the_prompt_says_which_grounding_mode_applies(run_dir: Path, prepared_sources):
    _, with_prep, _ = prep_debate(run_dir)
    _, without_prep = debated(run_dir)

    grounded = build_request(with_prep, 4000).messages[0].content
    ungrounded = build_request(without_prep, 4000).messages[0].content

    assert "that side's own prep evidence" in grounded
    assert "no prep phase" in ungrounded


def test_a_cut_off_turn_is_flagged_to_the_judge(run_dir: Path):
    # B5 reads hit_budget when judging a turn that may have been truncated (ADR-010).
    config = configure(run_dir, ("opening",))
    backends = [FakeBackend(reply("Cut off here", completion_tokens=2000)), FakeBackend(auto="con")]
    transcript = asyncio.run(run_debate(config, backends))

    assert "reached its budget" in render(transcript)


# --- aggregation and the winner (ADR-013 §3) ---------------------------------


def test_the_winner_is_the_higher_total(run_dir: Path):
    _, transcript = debated(run_dir)
    sheet, _ = judged(transcript, judge_reply(side(0), side(1, argument_quality=10)))

    assert [s.total for s in sheet.sides] == [76, 62]
    assert (sheet.winner, sheet.winner_reason) == ("pro", "total")


def test_steelman_fidelity_breaks_a_tie(run_dir: Path):
    # Equal totals, and the side that steelmanned better wins (ADR-002's tiebreaker).
    _, transcript = debated(run_dir)
    sheet, _ = judged(
        transcript,
        judge_reply(side(0), side(1, steelman_fidelity=18, clarity=5)),
    )

    assert [s.total for s in sheet.sides] == [76, 76]
    assert (sheet.winner, sheet.winner_reason) == ("con", "steelman_tiebreak")


def test_an_exact_tie_is_a_draw_not_a_coin_flip(run_dir: Path):
    _, transcript = debated(run_dir)
    sheet, _ = judged(transcript, judge_reply(side(0), side(1)))

    assert (sheet.winner, sheet.winner_reason) == ("draw", "tied_after_steelman_tiebreak")


def test_the_winner_follows_the_side_label_not_the_list_position(run_dir: Path):
    # teams[0] is con here, so a con win must say "con" (ADR-007 §7).
    config = configure(run_dir, ("opening",), swap_sides=True)
    transcript = asyncio.run(run_debate(config, fakes()))
    sheet, _ = judged(transcript, judge_reply(side(0), side(1, argument_quality=5)))

    assert sheet.sides[0].side == "con"
    assert sheet.winner == "con"


def test_no_blended_score_is_asked_of_the_model(run_dir: Path):
    # Hard Rule 3: the model returns five numbers; the total is computed here.
    _, transcript = debated(run_dir)
    system = build_request(transcript, 4000).messages[0].content
    sheet, _ = judged(transcript, judge_reply(side(0), side(1)))

    assert "Never combine them into one number" in system
    assert '"total"' not in system
    assert sheet.sides[0].total == sum(d.score for d in sheet.sides[0].dimensions)


# --- prep_grounded is a fact about the transcript (ADR-015 §5) ---------------


def test_prep_grounded_is_true_when_the_debate_prepped(run_dir: Path, prepared_sources):
    _, transcript, _ = prep_debate(run_dir)
    sheet, _ = judged(transcript, judge_reply(side(0), side(1)))

    grounding = [d for d in sheet.sides[0].dimensions if d.name == "evidence_grounding"]
    assert [d.prep_grounded for d in grounding] == [True]


def test_prep_grounded_comes_from_the_transcript_not_the_reply(run_dir: Path):
    # A reply claiming a verified score on a debate with no prep must not be believed.
    _, transcript = debated(run_dir)
    claimed = side(0)
    claimed["evidence_grounding"]["prep_grounded"] = True
    sheet, _ = judged(transcript, judge_reply(claimed, side(1)))

    grounding = next(d for d in sheet.sides[0].dimensions if d.name == "evidence_grounding")
    assert grounding.prep_grounded is False


# --- a malformed reply is an error, never a zero (Hard Rule 3) ---------------


BROKEN = [
    ("a missing dimension", lambda: judge_reply(_without(side(0), "clarity"), side(1)),
     "side 0's clarity is missing"),
    ("a score above the maximum", lambda: judge_reply(side(0, clarity=11), side(1)),
     "score is 11, outside 0-10"),
    ("a negative score", lambda: judge_reply(side(0, clarity=-1), side(1)),
     "score is -1, outside 0-10"),
    ("a score that isn't a number", lambda: judge_reply(_set_score(side(0), "clarity", "eight"), side(1)),
     "score is 'eight', not a whole number"),
    ("a boolean score", lambda: judge_reply(_set_score(side(0), "clarity", True), side(1)),
     "score is True, not a whole number"),
    ("an empty justification", lambda: judge_reply(_blank_justification(side(0)), side(1)),
     "has no justification"),
    ("an unknown hit status", lambda: judge_reply(side(0, ledger=[{"point": "x", "status": "ignored"}]), side(1)),
     "status is 'ignored', not one of open, conceded, rebutted, dodged"),
    ("a hit ledger that isn't a list", lambda: judge_reply(side(0, ledger="two points"), side(1)),
     "hit_ledger is 'two points', not a list"),
    ("a ledger entry with no point", lambda: judge_reply(side(0, ledger=[{"status": "dodged"}]), side(1)),
     "hit_ledger\\[0\\] has no point"),
    ("one side only", lambda: judge_reply(side(0)), "scores 1 sides, and this debate has 2"),
    ("the same side twice", lambda: judge_reply(side(0), side(0)), "side 0 is scored twice"),
    ("an unknown side index", lambda: judge_reply(side(0), side(7)), "side_index is 7, not one of"),
    ("prose instead of JSON", lambda: "Side 0 argued better, I'd give it 76.",
     "holds no JSON object"),
    ("a reply cut off before any closing brace", lambda: '{"sides": [{"side_index": 0, "argument_qual',
     "holds no JSON object"),
    ("JSON that doesn't parse", lambda: '{"sides": [{"side_index": 0 "clarity": {}}]}',
     "JSON is malformed"),
]


def _without(body: dict, name: str) -> dict:
    body.pop(name)
    return body


def _set_score(body: dict, name: str, value) -> dict:
    body[name]["score"] = value
    return body


def _blank_justification(body: dict) -> dict:
    body["clarity"]["justification"] = "   "
    return body


def _without_ledger(body: dict) -> dict:
    body["rebuttal_effectiveness"].pop("hit_ledger")
    return body


@pytest.mark.parametrize("make, expected", [case[1:] for case in BROKEN],
                         ids=[case[0] for case in BROKEN])
def test_a_malformed_reply_fails_the_run(run_dir: Path, make, expected):
    _, transcript = debated(run_dir)
    with pytest.raises(JudgeError, match=expected):
        judged(transcript, make())


def test_an_absent_ledger_reads_as_empty_and_says_so(run_dir: Path):
    # ADR-015 §8: the score and its justification are there, so no dimension failed to
    # parse. Measured behaviour — Qwen3-8B scores well and omits the ledger.
    _, transcript = debated(run_dir, ("opening", "rebuttal"))
    sheet, _ = judged(transcript, judge_reply(_without_ledger(side(0)), side(1)))

    without = next(d for d in sheet.sides[0].dimensions if d.name == "rebuttal_effectiveness")
    given = next(d for d in sheet.sides[1].dimensions if d.name == "rebuttal_effectiveness")
    assert (without.hit_ledger, without.hit_ledger_reported) == ((), False)
    assert given.hit_ledger_reported is True
    assert without.score == 11  # the dimension is still scored, not zeroed


def test_an_empty_ledger_is_not_the_same_as_no_ledger(run_dir: Path):
    _, transcript = debated(run_dir)
    sheet, _ = judged(transcript, judge_reply(side(0, ledger=[]), side(1)))
    output = run_dir / "score.json"
    write_scores(sheet, output)
    document = json.loads(output.read_text(encoding="utf-8"))

    ledger = document["sides"][0]["dimensions"]["rebuttal_effectiveness"]
    assert ledger["hit_ledger"] == [] and ledger["hit_ledger_reported"] is True


def test_nothing_is_written_when_judging_fails(run_dir: Path):
    _, transcript = debated(run_dir)
    output = run_dir / "score.json"
    with pytest.raises(JudgeError):
        judged(transcript, "not JSON at all")

    assert not output.exists()


def test_a_reply_over_its_budget_fails(run_dir: Path):
    # Hard Rule 5 applies to the judge's one call as to any turn.
    _, transcript = debated(run_dir)
    with pytest.raises(JudgeError, match="over the 16-token tolerance"):
        judged(transcript, judge_reply(side(0), side(1)), budget=100,
               completion_tokens=100 + BUDGET_TOLERANCE + 1)


def test_a_reply_cut_off_by_the_budget_says_so(run_dir: Path):
    _, transcript = debated(run_dir)
    with pytest.raises(JudgeError, match="raise --budget"):
        judged(transcript, '{"sides": [{"side_ind', budget=100, completion_tokens=100)


# --- the tolerated shapes (ADR-015 §4) ---------------------------------------


def test_a_fenced_reply_is_read(run_dir: Path):
    _, transcript = debated(run_dir)
    fenced = f"```json\n{judge_reply(side(0), side(1))}\n```"
    sheet, _ = judged(transcript, fenced)

    assert sheet.sides[0].total == 76


def test_a_preamble_before_the_json_is_read(run_dir: Path):
    _, transcript = debated(run_dir)
    chatty = f"Here is my scoring of the debate:\n\n{judge_reply(side(0), side(1))}\n\nI hope this helps."
    sheet, _ = judged(transcript, chatty)

    assert sheet.sides[0].total == 76


# --- the score file (ADR-013 §5) ---------------------------------------------


def test_the_score_file_is_the_adr_013_document(run_dir: Path, prepared_sources):
    _, transcript, _ = prep_debate(run_dir)
    sheet, _ = judged(transcript, judge_reply(side(0), side(1, clarity=3)))
    output = run_dir / "score.json"

    assert write_scores(sheet, output) is None  # nothing to rotate
    document = json.loads(output.read_text(encoding="utf-8"))

    assert document["schema_version"] == 1
    assert document["debatebench_version"]
    assert document["judged_at"].endswith("Z")
    assert document["judge_model"] == "judge-model"
    assert document["judge_budget"] == 4000
    assert document["fact_check_enabled"] is False  # nothing checked, so it says so
    assert document["winner"] == "pro" and document["winner_reason"] == "total"

    pro = document["sides"][0]
    assert (pro["side_index"], pro["side"], pro["total"]) == (0, "pro", 76)
    assert set(pro["dimensions"]) == {name for name, _ in DIMENSIONS}
    assert pro["dimensions"]["argument_quality"] == {
        "score": 24, "max": 30, "justification": "scored argument_quality this way because…",
    }
    assert pro["dimensions"]["evidence_grounding"]["prep_grounded"] is True
    assert pro["dimensions"]["rebuttal_effectiveness"]["hit_ledger"] == LEDGER
    assert pro["dimensions"]["rebuttal_effectiveness"]["hit_ledger_reported"] is True


def test_every_dimension_is_written_beside_the_total(run_dir: Path):
    # Hard Rule 3: a total never appears without the scores it came from.
    _, transcript = debated(run_dir)
    sheet, _ = judged(transcript, judge_reply(side(0), side(1)))
    output = run_dir / "score.json"
    write_scores(sheet, output)
    document = json.loads(output.read_text(encoding="utf-8"))

    for entry in document["sides"]:
        assert entry["total"] == sum(d["score"] for d in entry["dimensions"].values())
        assert len(entry["dimensions"]) == 5


def test_an_existing_score_file_is_rotated(run_dir: Path):
    # Re-judging with a different model is the normal use, so the old verdict survives.
    _, transcript = debated(run_dir)
    output = run_dir / "score.json"
    first, _ = judged(transcript, judge_reply(side(0), side(1)))
    write_scores(first, output)

    second, _ = judged(transcript, judge_reply(side(0, clarity=2), side(1)))
    backup = write_scores(second, output)

    assert backup == output.with_name("score.json.1")
    assert json.loads(backup.read_text())["sides"][0]["total"] == 76
    assert json.loads(output.read_text())["sides"][0]["total"] == 70


def test_parse_reply_keeps_the_ledger_points(run_dir: Path):
    _, transcript = debated(run_dir)
    ledger = [{"point": "border adjustments", "status": "dodged"},
              {"point": "rural drivers", "status": "conceded"}]
    scored = parse_reply(judge_reply(side(0, ledger=ledger), side(1)), transcript)

    rebuttal = next(d for d in scored[0] if d.name == "rebuttal_effectiveness")
    assert [(hit.point, hit.status) for hit in rebuttal.hit_ledger] == [
        ("border adjustments", "dodged"), ("rural drivers", "conceded"),
    ]
