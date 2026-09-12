"""B4: retrieval, the one prep call, and prep's privacy (ADR-012, ADR-014)."""

import asyncio
import json
from pathlib import Path

import pytest

from debatebench.config import load_run
from debatebench.orchestrator import BUDGET_TOLERANCE, DebateError, run_debate
from debatebench.retrieval import TOP_K, RetrievalError, retrieve, sources_dir
from debatebench.transcript import write_transcript
from fakes import FakeBackend, reply
from helpers import edit_yaml
from test_orchestrator import configure, fakes

TOPIC = "A federal carbon tax would do more good than harm."

# In the fixture pools: pro-side rows, con-side rows, and the liberal team's own corpus.
PRO_IDS = {"am-1", "am-2", "am-3", "ds-1"}
CON_IDS = {"am-4", "am-5", "am-6", "am-7", "ds-2"}
CORPUS_IDS = {"lc-1", "lc-2"}
OFF_TOPIC_IDS = {"am-8", "am-9", "ds-3", "lc-3"}


def corpus_of(run_dir: Path) -> Path:
    return run_dir / "teams" / "liberal-climate-corpus.jsonl"


def ids(evidence):
    return {item.id for item in evidence}


# --- retrieval: two pools, two methods (ADR-012 §2) --------------------------


def test_each_side_retrieves_its_own_side_of_the_shared_pool(run_dir: Path, prepared_sources):
    pro = retrieve(TOPIC, "pro", ("args-me", "debatesum"), None)
    con = retrieve(TOPIC, "con", ("args-me", "debatesum"), None)

    assert ids(pro) == PRO_IDS
    assert ids(con) == CON_IDS
    assert not ids(pro) & ids(con)  # one pool, two disjoint reads


def test_passages_that_do_not_match_the_topic_are_left_behind(run_dir: Path, prepared_sources):
    retrieved = ids(retrieve(TOPIC, "pro", ("args-me", "debatesum"), corpus_of(run_dir)))
    assert not retrieved & OFF_TOPIC_IDS


def test_a_teams_own_corpus_is_layered_on_top(run_dir: Path, prepared_sources):
    # ADR-007 §3: an additional per-side layer, not a replacement.
    without = retrieve(TOPIC, "pro", ("args-me", "debatesum"), None)
    with_corpus = retrieve(TOPIC, "pro", ("args-me", "debatesum"), corpus_of(run_dir))

    assert ids(with_corpus) == ids(without) | CORPUS_IDS


def test_the_corpus_is_not_filtered_by_side(run_dir: Path, prepared_sources):
    # Its rows carry no side at all: everything in it is this side's already (ADR-012 §2).
    assert ids(retrieve(TOPIC, "con", (), corpus_of(run_dir))) == CORPUS_IDS


def test_only_the_corpus_is_still_a_prepared_side(run_dir: Path, prepared_sources):
    # ADR-014 §4: a run with no shared sources but a corpus per team is legitimate.
    assert retrieve(TOPIC, "pro", (), corpus_of(run_dir))


def test_each_pool_is_capped_at_ten_passages(run_dir: Path, prepared_sources):
    many = "\n".join(
        json.dumps({"id": f"x-{n}", "topic": "carbon tax", "side": "pro",
                    "source": "args-me", "text": f"A carbon tax argument, number {n}."})
        for n in range(25)
    )
    (prepared_sources / "args-me.jsonl").write_text(many + "\n", encoding="utf-8")

    assert len(retrieve(TOPIC, "pro", ("args-me",), None)) == TOP_K


def test_the_same_query_retrieves_the_same_passages_in_the_same_order(run_dir: Path, prepared_sources):
    # Retrieval has no model call in it, so a run is reproducible from config alone.
    first = retrieve(TOPIC, "pro", ("args-me", "debatesum"), corpus_of(run_dir))
    second = retrieve(TOPIC, "pro", ("args-me", "debatesum"), corpus_of(run_dir))

    assert [item.id for item in first] == [item.id for item in second]


def test_the_better_topic_match_comes_first(run_dir: Path, prepared_sources):
    (prepared_sources / "args-me.jsonl").write_text(
        json.dumps({"id": "weak", "topic": "municipal recycling", "side": "pro",
                    "source": "args-me", "text": "A passing mention of a carbon tax."}) + "\n"
        + json.dumps({"id": "strong", "topic": "a federal carbon tax", "side": "pro",
                      "source": "args-me", "text": "A federal carbon tax, argued directly."}) + "\n",
        encoding="utf-8",
    )
    assert [item.id for item in retrieve(TOPIC, "pro", ("args-me",), None)] == ["strong", "weak"]


def test_a_passage_keeps_its_id_source_and_text(run_dir: Path, prepared_sources):
    # ADR-005's evidence item shape, and ADR-012 §4's "raw, untouched by the model".
    (item,) = [p for p in retrieve(TOPIC, "pro", ("args-me",), None) if p.id == "am-1"]
    assert item.source == "args-me"
    assert "Brindlewick" in item.text


# --- retrieval: what a broken pool does --------------------------------------


def test_a_missing_source_names_the_dataset_and_the_path(run_dir: Path, monkeypatch):
    monkeypatch.setenv("DEBATEBENCH_SOURCES_DIR", str(run_dir / "nothing-here"))
    with pytest.raises(RetrievalError, match=r"source 'args-me' is not prepared: no file at .*args-me\.jsonl"):
        retrieve(TOPIC, "pro", ("args-me",), None)


def test_a_missing_corpus_file_is_an_error(run_dir: Path, prepared_sources):
    with pytest.raises(RetrievalError, match="corpus file does not exist"):
        retrieve(TOPIC, "pro", (), run_dir / "teams" / "gone.jsonl")


BROKEN_ROWS = [
    ("not JSON", "{oops", "not valid JSON"),
    ("not an object", '["a", "list"]', "each line must be a JSON object"),
    ("missing a field", '{"id": "a", "topic": "carbon tax", "side": "pro"}', "text must be a non-empty string"),
    ("an empty field", '{"id": "", "text": "t", "topic": "carbon tax", "side": "pro", "source": "s"}',
     "id must be a non-empty string"),
    ("a number where a string belongs",
     '{"id": 7, "text": "t", "topic": "carbon tax", "side": "pro", "source": "s"}',
     "id must be a non-empty string, got 7"),
    ("no side in a shared row", '{"id": "a", "text": "t", "topic": "carbon tax", "source": "s"}',
     "side must be a non-empty string"),
]


@pytest.mark.parametrize("row, expected", [case[1:] for case in BROKEN_ROWS],
                         ids=[case[0] for case in BROKEN_ROWS])
def test_a_broken_row_fails_retrieval(run_dir: Path, prepared_sources, row, expected):
    # Checked before anything is retrieved: a pool is either readable or an error.
    path = prepared_sources / "args-me.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + row + "\n", encoding="utf-8")
    with pytest.raises(RetrievalError, match=expected):
        retrieve(TOPIC, "pro", ("args-me",), None)


def test_blank_lines_and_extra_fields_are_tolerated(run_dir: Path, prepared_sources):
    # A pool is data, not config: an extra column is what real datasets look like.
    path = prepared_sources / "args-me.jsonl"
    row = json.dumps({"id": "extra", "text": "A carbon tax argument.", "topic": "carbon tax",
                      "side": "pro", "source": "args-me", "annotator_count": 15})
    path.write_text(path.read_text(encoding="utf-8") + "\n" + row + "\n", encoding="utf-8")

    assert "extra" in ids(retrieve(TOPIC, "pro", ("args-me",), None))


def test_sources_dir_defaults_to_the_documented_cache(monkeypatch):
    monkeypatch.delenv("DEBATEBENCH_SOURCES_DIR", raising=False)
    assert sources_dir() == Path.home() / ".cache" / "debatebench" / "sources"


def test_sources_dir_follows_the_environment(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DEBATEBENCH_SOURCES_DIR", str(tmp_path))
    assert sources_dir() == tmp_path


# --- the prep turn itself (ADR-012 §§3–4, ADR-014 §§3–4) ---------------------


def prep_debate(run_dir: Path, phases=("prep", "opening"), backends=None):
    config = configure(run_dir, phases)
    backends = backends or fakes()
    return config, asyncio.run(run_debate(config, backends)), backends


def test_prep_is_one_call_per_side_capped_by_prep_budget(run_dir: Path, prepared_sources):
    config, transcript, backends = prep_debate(run_dir)
    prep_turns = [turn for turn in transcript.turns if turn.phase == "prep"]

    assert len(prep_turns) == 2
    assert all(turn.budget == 1500 for turn in prep_turns)  # prep_budget, not budget
    assert all(turn.budget == 2000 for turn in transcript.turns if turn.phase != "prep")
    assert all(backend.requests[0].max_completion_tokens == 1500 for backend in backends)


def test_the_prep_call_sees_the_passages_and_nothing_later_does(run_dir: Path, prepared_sources):
    config, transcript, backends = prep_debate(run_dir)
    prep_request, opening_request = backends[0].requests

    assert "Brindlewick" in prep_request.messages[1].content  # the raw passage
    assert "Brindlewick" not in opening_request.messages[1].content  # only the notes travel on


def test_the_prep_turn_records_its_evidence(run_dir: Path, prepared_sources):
    config, transcript, _ = prep_debate(run_dir)
    pro_prep = transcript.turn(0, 0)

    assert ids(pro_prep.evidence) == PRO_IDS | CORPUS_IDS
    assert ids(transcript.turn(0, 1).evidence) == CON_IDS  # the con team has no corpus
    assert all(item.text and item.source for item in pro_prep.evidence)


def test_neither_prep_turn_claims_to_have_gone_first(run_dir: Path, prepared_sources):
    # ADR-014 §3: nothing about prep is sequential, so order is 0 for both.
    _, transcript, _ = prep_debate(run_dir)
    assert [turn.order for turn in transcript.turns if turn.phase == "prep"] == [0, 0]


def test_pro_still_opens_the_first_argument_phase(run_dir: Path, prepared_sources):
    # ADR-010 §1 counts argument phases only, so a prep phase doesn't hand the opening over.
    _, transcript, _ = prep_debate(run_dir, ("prep", "opening", "rebuttal"))
    opening = [turn for turn in transcript.turns if turn.phase == "opening"]

    assert opening[0].side_index == 0  # teams[0] is pro in the fixture


def test_an_over_budget_prep_turn_fails_the_run(run_dir: Path, prepared_sources):
    # Hard Rule 5 applies to prep_budget exactly as to budget (ADR-012 §3).
    over = reply("Too much.", completion_tokens=1500 + BUDGET_TOLERANCE + 1)
    backends = [FakeBackend(over, auto="pro"), FakeBackend(auto="con")]
    with pytest.raises(DebateError, match="for a budget of 1500"):
        prep_debate(run_dir, backends=backends)


def test_a_side_that_retrieves_nothing_fails_the_run(run_dir: Path, prepared_sources):
    # ADR-014 §4: no evidence at all is a failure, not an empty prep turn.
    edit_yaml(run_dir / "run.yaml", lambda data: data.update(topic="Badgers make excellent pets."))
    backends = fakes()
    with pytest.raises(DebateError, match="nothing matched the topic in args-me, debatesum"):
        asyncio.run(run_debate(load_run(run_dir / "run.yaml"), backends))
    assert all(not backend.requests for backend in backends)


# --- prep is private (ADR-014 §2) -------------------------------------------


def test_a_side_never_sees_the_opponents_prep(run_dir: Path, prepared_sources):
    # Asserted on what the backend was actually sent, not on render_debate's output:
    # this is what proves the orchestrator passes the right viewer.
    backends = [
        FakeBackend(reply("PRO-PREP-NOTES"), auto="pro"),
        FakeBackend(reply("CON-PREP-NOTES"), auto="con"),
    ]
    prep_debate(run_dir, backends=backends)
    pro_opening = backends[0].requests[1].messages[1].content
    con_opening = backends[1].requests[1].messages[1].content

    assert "PRO-PREP-NOTES" in pro_opening and "CON-PREP-NOTES" not in pro_opening
    assert "CON-PREP-NOTES" in con_opening and "PRO-PREP-NOTES" not in con_opening


def test_both_sides_still_see_every_argument_turn(run_dir: Path, prepared_sources):
    backends = [
        FakeBackend(reply("PRO-PREP-NOTES"), reply("PRO-OPENING"), auto="pro"),
        FakeBackend(reply("CON-PREP-NOTES"), auto="con"),
    ]
    prep_debate(run_dir, ("prep", "opening", "rebuttal"), backends=backends)
    con_rebuttal = backends[1].requests[2].messages[1].content

    assert "PRO-OPENING" in con_rebuttal  # privacy covers prep, and only prep


def test_prep_notes_are_labelled_as_the_sides_own(run_dir: Path, prepared_sources):
    backends = [FakeBackend(reply("PRO-PREP-NOTES"), auto="pro"), FakeBackend(auto="con")]
    prep_debate(run_dir, backends=backends)

    assert "[1. Your prep notes]" in backends[0].requests[1].messages[1].content


# --- what lands in the written transcript ------------------------------------


def test_evidence_is_written_only_on_prep_turns(run_dir: Path, prepared_sources):
    config, transcript, _ = prep_debate(run_dir)
    write_transcript(transcript, config.output)
    document = json.loads(config.output.read_text(encoding="utf-8"))

    prep, opening = document["turns"][0], document["turns"][2]
    assert prep["phase"] == "prep" and opening["phase"] == "opening"
    assert "evidence" not in opening  # not an empty list: it never had any (ADR-014 §6)
    assert {item["id"] for item in prep["evidence"]} == PRO_IDS | CORPUS_IDS
    assert set(prep["evidence"][0]) == {"id", "source", "text"}
