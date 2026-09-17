"""ADR-032: the judge may ask the server to constrain its reply to the schema."""

import asyncio
from pathlib import Path

import pytest

from debatebench.judging import (
    DIMENSIONS,
    HIT_STATUSES,
    VERDICTS,
    build_fact_check_request,
    build_request,
    claims_schema,
    score_schema,
)
from fakes import FakeBackend, reply
from test_fact_check import claim, claims_reply
from test_judging import debated, judge_reply, side
from test_prep import prep_debate


def test_off_by_default_the_request_is_unchanged(run_dir: Path):
    """ADR-032 §4: every existing caller keeps the request it had."""
    _, transcript = debated(run_dir)
    assert build_request(transcript, 4000).response_schema is None
    assert build_fact_check_request(transcript, 4000).response_schema is None


def test_a_debate_turn_never_carries_a_schema(run_dir: Path):
    # ADR-032 §2: a speech is prose. Only the judge constrains anything.
    from debatebench.prompts import build_request as turn_request

    config, transcript = debated(run_dir)
    request = turn_request(
        config.topic, config.sides[0], "opening", config.sides, [], config.seed
    )
    assert request.response_schema is None


def test_the_hit_ledger_vocabulary_is_an_enum():
    """The values `mistral-nemo` invented — `partially rebutted` — become unemittable."""
    ledger = score_schema()["properties"]["sides"]["items"]["properties"][
        "rebuttal_effectiveness"]["properties"]["hit_ledger"]
    assert ledger["items"]["properties"]["status"]["enum"] == list(HIT_STATUSES)


def test_every_rubric_dimension_is_named_in_the_schema():
    side_schema = score_schema()["properties"]["sides"]["items"]
    for name, _ in DIMENSIONS:
        assert name in side_schema["properties"]
        assert name in side_schema["required"]


def test_the_verdict_vocabulary_is_an_enum(run_dir: Path):
    _, transcript = debated(run_dir)
    entry = claims_schema(transcript)["properties"]["claims"]["items"]
    assert entry["properties"]["verdict"]["enum"] == list(VERDICTS)


def test_evidence_ids_are_constrained_to_ids_the_transcript_recorded(
    run_dir: Path, prepared_sources
):
    """ADR-032 §3's point: `am-255` stops being a validation error and becomes
    a token the sampler may not emit."""
    _, transcript, _ = prep_debate(run_dir)
    recorded = {item.id for turn in transcript.turns for item in turn.evidence}
    assert recorded, "the fixture should retrieve something"

    ids = claims_schema(transcript)["properties"]["claims"]["items"]["properties"]["evidence_ids"]
    assert set(ids["items"]["enum"]) == recorded
    assert "am-255" not in ids["items"]["enum"]


def test_with_no_evidence_the_schema_forbids_citing_anything(run_dir: Path):
    # An empty enum is not legal JSON Schema, so the array is capped at zero
    # items — which matches ADR-015 §2's degradation path.
    _, transcript = debated(run_dir)          # no prep, so nothing recorded
    ids = claims_schema(transcript)["properties"]["claims"]["items"]["properties"]["evidence_ids"]
    assert ids["maxItems"] == 0
    assert "enum" not in ids["items"]


def test_a_turn_number_outside_the_transcript_is_out_of_range(run_dir: Path):
    _, transcript = debated(run_dir)
    turn = claims_schema(transcript)["properties"]["claims"]["items"]["properties"]["turn"]
    assert turn["minimum"] == 1 and turn["maximum"] == len(transcript.turns)


def test_the_schema_reaches_the_wire_as_response_format(run_dir: Path):
    """ADR-032 §1: the adapter sends OpenAI's shape, and only when asked."""
    import httpx

    from debatebench.openai_compat import OpenAICompatibleBackend

    sent = {}

    def capture(request: httpx.Request) -> httpx.Response:
        import json as _json
        sent.update(_json.loads(request.content))
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        })

    _, transcript = debated(run_dir)
    transport = httpx.MockTransport(capture)
    with httpx.Client(transport=transport):  # keep httpx import honest
        pass

    async def call(strict):
        async with httpx.AsyncClient(transport=transport) as client:
            backend = OpenAICompatibleBackend(client, "http://x/v1", "m")
            await backend.generate(build_request(transcript, 4000, strict_json=strict))

    asyncio.run(call(True))
    assert sent["response_format"]["type"] == "json_schema"
    assert sent["response_format"]["json_schema"]["strict"] is True
    assert "sides" in sent["response_format"]["json_schema"]["schema"]["properties"]

    sent.clear()
    asyncio.run(call(False))
    assert "response_format" not in sent


def test_validation_is_not_weakened_by_the_schema(run_dir: Path, prepared_sources):
    """ADR-032 §6: a backend that ignores response_format must still be caught."""
    from debatebench.judging import JudgeError, fact_check_debate

    _, transcript, _ = prep_debate(run_dir)
    # A backend that ignores the schema and invents an id — exactly phi4-mini.
    backend = FakeBackend(reply(claims_reply(claim(evidence_ids=("am-255",))),
                                completion_tokens=200))
    with pytest.raises(JudgeError, match="which the transcript never recorded"):
        asyncio.run(fact_check_debate(transcript, backend, budget=4000, strict_json=True))
