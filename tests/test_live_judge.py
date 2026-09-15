"""B5's live gate: a real model scoring real transcripts (ADR-013, ADR-017).

Opt in with DEBATEBENCH_LIVE_TESTS=1, and point DEBATEBENCH_MLX_BASE_URL at a
running server. Unlike the AFM tests, nothing here starts the server: an 8B
model takes too long to load per test run, and the tool never starts servers
anyway (ADR-003). AFM can't judge — a full transcript overruns its ~4,096-token
session limit (BUILD-GUIDE B7) — so this needs mlx_lm.server or equivalent.
"""

import json
import os
import urllib.request
from pathlib import Path

import pytest

from debatebench.judge_cli import main
from debatebench.judging import VERDICTS
from debatebench.orchestrator import run_debate
from debatebench.transcript import write_transcript
from fakes import FakeBackend, reply
from test_orchestrator import configure
from test_prep import prep_debate

pytestmark = pytest.mark.skipif(
    os.environ.get("DEBATEBENCH_LIVE_TESTS") != "1",
    reason="live model tests are opt-in: set DEBATEBENCH_LIVE_TESTS=1",
)

BASE_URL = os.environ.get("DEBATEBENCH_MLX_BASE_URL", "http://127.0.0.1:8080/v1")
# Must be exactly the repo id the server loaded (CLAUDE.md, "Backend").
MODEL = os.environ.get("DEBATEBENCH_MLX_MODEL", "mlx-community/Qwen3-8B-4bit")
# Generous: Qwen3 is a reasoning model and the adapter can't turn thinking off,
# since ADR-009 fixes the request body (OPEN-QUESTIONS item 13). Measured: 3000
# is enough for a four-turn transcript but is entirely consumed by thinking on a
# prepped one, whose evidence passages make the prompt much longer.
BUDGET = int(os.environ.get("DEBATEBENCH_JUDGE_BUDGET", "6000"))

STRONG = [
    "A carbon tax prices the harm at its source, so every firm finds its own cheapest "
    "abatement rather than waiting for a regulator to guess. Revenue returned as a flat "
    "dividend more than covers higher bills for the poorest households, which is what "
    "turns a regressive price into a progressive transfer.",
    "The other side's strongest point is leakage: a price at home while partners have none "
    "moves the factory rather than the emissions. That is real, and it is why border "
    "adjustment exists; it is an argument for pairing the tax with one, not for having no "
    "price at all. Their exemption point cuts the other way too, since exemptions are a "
    "reason to write the law tightly, not to abandon it.",
]
WEAK = [
    "Taxes are bad and this one is no different. People do not like paying more.",
    "I disagree with what they said. It still seems like a bad idea to me.",
]


def _reachable() -> None:
    # Something answering on the port isn't enough: a stray web server on 8080 will
    # answer too, and then every request fails as an HTTP 404 two minutes later.
    try:
        with urllib.request.urlopen(f"{BASE_URL.rstrip('/v1')}/v1/models", timeout=5) as answer:
            listed = answer.read().decode("utf-8", "replace")
        if MODEL not in listed:
            pytest.fail(
                f"something is listening at {BASE_URL} but it does not serve {MODEL}; "
                f"it answered: {listed[:200]}"
            )
        return
    except OSError as e:
        # Opted in but can't run: fail, never skip (ADR-004).
        pytest.fail(
            f"DEBATEBENCH_LIVE_TESTS=1 but no model server at {BASE_URL}: {e}. "
            "Start one, e.g. HF_HUB_OFFLINE=1 python3 -m mlx_lm.server "
            f"--model {MODEL} --port 8080"
        )


@pytest.fixture(scope="module", autouse=True)
def server():
    _reachable()


def _judge(transcript_path: Path, output: Path, *, fact_check: bool = False) -> int:
    # The scoring tests skip the audit, so each exercises one call (ADR-015 §3).
    return main([
        str(transcript_path), "--model", MODEL, "--base-url", BASE_URL,
        "--budget", str(BUDGET), "--output", str(output),
        "--fact-check" if fact_check else "--no-fact-check",
    ])


def _write(run_dir: Path, pro_turns, con_turns, phases=("opening", "rebuttal")) -> Path:
    config = configure(run_dir, phases)
    backends = [
        FakeBackend(*[reply(text, completion_tokens=120) for text in pro_turns]),
        FakeBackend(*[reply(text, completion_tokens=120) for text in con_turns]),
    ]
    import asyncio

    transcript = asyncio.run(run_debate(config, backends))
    write_transcript(transcript, config.output)
    return config.output


def _show(document: dict) -> None:
    for entry in document["sides"]:
        print(f"\nside {entry['side_index']} ({entry['side']}): {entry['total']} of 100")
        for name, body in entry["dimensions"].items():
            print(f"  {name}: {body['score']}/{body['max']} — {body['justification'][:120]}")
        ledger = entry["dimensions"]["rebuttal_effectiveness"].get("hit_ledger", [])
        print(f"  hit ledger: {[(h['point'][:40], h['status']) for h in ledger]}")
    print(f"winner: {document['winner']} ({document['winner_reason']})")


def test_a_lopsided_debate_is_scored_and_explained(run_dir: Path, capfd):
    # The first of B5's three transcripts: one side clearly weaker.
    transcript = _write(run_dir, STRONG, WEAK)
    output = run_dir / "score.json"

    assert _judge(transcript, output) == 0, capfd.readouterr().err
    document = json.loads(output.read_text(encoding="utf-8"))
    with capfd.disabled():
        _show(document)

    pro, con = document["sides"]
    assert pro["total"] > con["total"], "the stronger side did not score higher"
    assert document["winner"] == "pro"
    # The diagnostic value is the point: every score carries its reason.
    assert all(body["justification"].strip() for body in pro["dimensions"].values())
    assert all(0 <= body["score"] <= body["max"] for body in pro["dimensions"].values())


def test_an_evenly_matched_debate_is_scored(run_dir: Path, capfd):
    # The second: both sides argue well, so the totals should land close together.
    transcript = _write(run_dir, STRONG, [
        "A carbon tax is regressive before any rebate arrives: the household spending most "
        "of its income on fuel pays first and is reimbursed last. Rural drivers have no "
        "substitute for the trip to work, so the price changes nothing but their budget.",
        "Their strongest argument is that a price lets each firm find its own abatement, and "
        "that is true where a substitute exists. It does not answer leakage: taxing at home "
        "while partners do not simply moves the plant and the jobs, and the emissions with them.",
    ])
    output = run_dir / "score.json"

    assert _judge(transcript, output) == 0, capfd.readouterr().err
    document = json.loads(output.read_text(encoding="utf-8"))
    with capfd.disabled():
        _show(document)

    assert document["winner"] in {"pro", "con", "draw"}
    assert document["winner_reason"] in {"total", "steelman_tiebreak", "coin_toss"}
    totals = [entry["total"] for entry in document["sides"]]
    print(f"\ntotals {totals}, margin {abs(totals[0] - totals[1])}")


def test_a_debate_without_prep_is_scored_as_ungrounded(run_dir: Path, capfd):
    # The third: no prep in the phase list, so evidence grounding is the weaker guarantee.
    transcript = _write(run_dir, STRONG, WEAK, phases=("opening",))
    output = run_dir / "score.json"

    assert _judge(transcript, output) == 0, capfd.readouterr().err
    document = json.loads(output.read_text(encoding="utf-8"))

    for entry in document["sides"]:
        assert entry["dimensions"]["evidence_grounding"]["prep_grounded"] is False


def test_a_prepped_debate_is_scored_as_grounded(run_dir: Path, prepared_sources, capfd):
    # And with prep, the same field says the score was checked against real evidence.
    config, transcript, _ = prep_debate(run_dir, ("prep", "opening"))
    write_transcript(transcript, config.output)
    output = run_dir / "score.json"

    assert _judge(config.output, output) == 0, capfd.readouterr().err
    document = json.loads(output.read_text(encoding="utf-8"))

    for entry in document["sides"]:
        assert entry["dimensions"]["evidence_grounding"]["prep_grounded"] is True


# --- B6's gate: the fact-check pass against a real model (ADR-015) -----------

# Three claims chosen against the fixture pool: am-1 records Brindlewick's 14%
# on the pro side, am-7 records that rural drivers have no substitute on the con
# side, and the third is an opinion no passage can bear on.
PRO_OPENING = (
    "Brindlewick cut household emissions by 14 percent in two years after adopting a "
    "carbon tax. Rural drivers have plenty of alternatives to driving, so the price "
    "signal reaches them too. This is the most important moral question of our time."
)
CON_OPENING = (
    "A carbon tax is regressive before any rebate arrives, and the households least able "
    "to absorb it pay first."
)


def test_the_fact_check_audits_claims_against_the_record(
    run_dir: Path, prepared_sources, capfd
):
    config, transcript, _ = prep_debate(
        run_dir,
        ("prep", "opening"),
        backends=[
            FakeBackend(reply("Pro prep notes.", completion_tokens=40),
                        reply(PRO_OPENING, completion_tokens=90)),
            FakeBackend(reply("Con prep notes.", completion_tokens=40),
                        reply(CON_OPENING, completion_tokens=60)),
        ],
    )
    write_transcript(transcript, config.output)
    output = run_dir / "score.json"

    assert _judge(config.output, output, fact_check=True) == 0, capfd.readouterr().err
    document = json.loads(output.read_text(encoding="utf-8"))
    audit = document["fact_check"]
    recorded = {item["id"] for turn in document.get("turns", []) for item in turn.get("evidence", [])}

    with capfd.disabled():
        print(f"\nchecked against: {audit['checked_against']}")
        for entry in audit["claims"]:
            print(f"  [{entry['verdict']:>14}] {entry['claim'][:80]} {entry['evidence_ids']}")

    assert audit["checked_against"] == "recorded_evidence"
    assert audit["claims"], "the audit found no claims at all"
    assert all(entry["verdict"] in VERDICTS for entry in audit["claims"])

    verdicts = {entry["verdict"] for entry in audit["claims"]}
    cited = {i for entry in audit["claims"] for i in entry["evidence_ids"]}
    # Every id survived parsing, so none was invented; this pins that in the gate too.
    assert not cited - _transcript_evidence_ids(config.output)
    assert "supported" in verdicts, "nothing was traced to a passage that backs it"
    # BUILD-GUIDE B6's second check: the finding prep_grounded can never produce.
    assert "contradicted" in verdicts, "the opponent's evidence never contradicted anything"
    assert "not_checkable" in verdicts, "the opinion was not recognised as one"


def _transcript_evidence_ids(path: Path) -> set[str]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return {item["id"] for turn in document["turns"] for item in turn.get("evidence", [])}
