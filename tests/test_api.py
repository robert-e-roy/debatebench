"""ADR-028: the one public module, and the promise that the CLIs go through it."""

import asyncio
import inspect
from pathlib import Path

import pytest

import debatebench
from debatebench import api
from debatebench.cli import main as debate_main
from fakes import FakeBackend, reply
from test_fact_check import claim, claims_reply
from test_judging import debated, judge_reply, side
from test_orchestrator import configure, fakes


# --- §1: what the surface is, and what it is not -----------------------------


def test_every_exported_name_exists():
    missing = [name for name in api.__all__ if not hasattr(api, name)]
    assert missing == []


def test_all_lists_every_public_name_the_module_has():
    # Otherwise a name is importable, undocumented, and accidentally supported.
    # Implementation-only imports are aliased to _names in api.py for this reason;
    # `annotations` is the __future__ directive every module in the package carries.
    public = {
        name
        for name in vars(api)
        if not name.startswith("_") and not inspect.ismodule(getattr(api, name))
    }
    assert public - set(api.__all__) == {"annotations"}


def test_all_has_no_duplicates():
    assert len(api.__all__) == len(set(api.__all__))


def test_the_package_root_still_exports_nothing(*, names=("debate", "judge", "load_run")):
    # ADR-028 §1 keeps the surface out of __init__.py so ADR-008's layering holds
    # and the root docstring stays true.
    assert [name for name in names if hasattr(debatebench, name)] == []


# ADR-028 §8: reachable, deliberately not promised. A name arriving here should
# mean someone decided to promise it, not that an import was tidied.
@pytest.mark.parametrize(
    "name", ["build_request", "build_fact_check_request", "render", "main", "decide",
             "speaking_order", "load_team", "retrieve", "system_prompt"]
)
def test_the_excluded_names_are_not_exported(name):
    assert name not in api.__all__


@pytest.mark.parametrize(
    "name", ["transcript_json", "scores_json", "TRANSCRIPT_SCHEMA_VERSION",
             "SCORE_SCHEMA_VERSION", "EVENT_SCHEMA_VERSION"]
)
def test_the_renamed_collisions_are_exported_under_one_name_each(name):
    assert name in api.__all__


def test_the_renames_point_at_what_they_say():
    from debatebench import event_stream, judging, transcript

    assert api.transcript_json is transcript.as_json_dict
    assert api.scores_json is judging.as_json_dict
    assert api.TRANSCRIPT_SCHEMA_VERSION == transcript.SCHEMA_VERSION
    assert api.SCORE_SCHEMA_VERSION == judging.SCORE_SCHEMA_VERSION
    assert api.EVENT_SCHEMA_VERSION == event_stream.SCHEMA_VERSION


# --- §2, §3: running a debate in process -------------------------------------


def test_a_debate_runs_on_an_injected_backend_with_no_server(run_dir: Path):
    # ADR-009's Protocol is the point of the API: no HTTP, no model, no ports.
    config = configure(run_dir, ("opening", "rebuttal"))
    transcript = asyncio.run(api.debate(config, backends=fakes()))

    assert len(transcript.turns) == 4
    assert transcript.run.topic == config.topic


def test_it_writes_nothing(run_dir: Path):
    # ADR-028 §5: config.output is required by ADR-007 and ignored here.
    config = configure(run_dir, ("opening",))
    asyncio.run(api.debate(config, backends=fakes()))
    assert not config.output.exists()


def test_the_caller_writes_it_themselves(run_dir: Path):
    config = configure(run_dir, ("opening",))
    transcript = asyncio.run(api.debate(config, backends=fakes()))

    assert api.write_transcript(transcript, config.output) is None  # nothing to rotate
    assert config.output.exists()
    assert api.load_transcript(config.output).turns[0].text == transcript.turns[0].text


def test_events_reach_a_subscriber(run_dir: Path):
    config = configure(run_dir, ("opening",))
    seen = []
    bus = api.EventBus()
    bus.subscribe(lambda event: seen.append(event.type))

    asyncio.run(api.debate(config, backends=fakes(), events=bus))
    assert api.EventType.RUN_COMPLETED in seen
    assert seen.count(api.EventType.TURN_COMPLETED) == 2


def test_a_failing_phase_raises_and_returns_nothing(run_dir: Path):
    # Hard Rule 1 reaches the API unchanged: no partial transcript comes back.
    config = configure(run_dir, ("opening",))
    backends = [FakeBackend(api.BackendError("the server refused")), FakeBackend(auto="con")]
    with pytest.raises(api.DebateError):
        asyncio.run(api.debate(config, backends=backends))
    assert not config.output.exists()


def test_the_wrong_number_of_backends_says_so(run_dir: Path):
    # "A failure must carry what's needed to fix it" — not an IndexError mid-run.
    config = configure(run_dir, ("opening",))
    with pytest.raises(ValueError) as e:
        asyncio.run(api.debate(config, backends=[FakeBackend(auto="pro")]))
    assert "1 backend(s) for 2 sides" in str(e.value)


# --- §2, §3: judging in process ----------------------------------------------


def test_judging_runs_on_an_injected_backend(run_dir: Path):
    _, transcript = debated(run_dir)
    backend = FakeBackend(reply(judge_reply(side(0), side(1)), completion_tokens=400))

    sheet = asyncio.run(
        api.judge(transcript, model="judge-model", budget=4000, backend=backend, fact_check=False)
    )
    assert [s.total for s in sheet.sides] == [sum(d.score for d in s.dimensions) for s in sheet.sides]
    assert sheet.judge_model == "judge-model"
    assert sheet.fact_check is None
    assert len(backend.requests) == 1  # scoring only


def test_the_fact_check_is_a_second_call_and_is_on_by_default(run_dir: Path):
    # ADR-015 §3, and --fact-check's default reaches the API the same way.
    _, transcript = debated(run_dir)
    backend = FakeBackend(
        reply(judge_reply(side(0), side(1)), completion_tokens=400),
        reply(claims_reply(claim(verdict="not_checkable", evidence_ids=())), completion_tokens=300),
    )

    sheet = asyncio.run(api.judge(transcript, model="judge-model", budget=4000, backend=backend))
    assert len(backend.requests) == 2
    assert sheet.fact_check is not None and sheet.fact_check_enabled is True


def test_a_budget_below_one_is_refused_before_the_call(run_dir: Path):
    """Hard Rule 5 reaches the API. The command checks --budget; nothing checked this.

    A budget of 0 would otherwise reach score_debate, which only fails a reply
    over ``budget + 16`` — so a 16-token reply would pass against a cap of none.
    """
    _, transcript = debated(run_dir)
    backend = FakeBackend(reply(judge_reply(side(0), side(1)), completion_tokens=400))

    with pytest.raises(ValueError) as e:
        asyncio.run(api.judge(transcript, model="m", budget=0, backend=backend))
    assert "at least 1 completion token" in str(e.value)
    assert backend.requests == []  # refused before anything was sent


def test_an_empty_model_name_is_refused(run_dir: Path):
    # It is recorded in the score file, so a blank one makes the sheet unreadable.
    _, transcript = debated(run_dir)
    with pytest.raises(ValueError) as e:
        asyncio.run(api.judge(transcript, model="  ", budget=4000, backend=FakeBackend()))
    assert "non-empty model name" in str(e.value)


def test_a_timeout_beside_your_own_backend_says_it_would_do_nothing(run_dir: Path):
    # An argument that silently does nothing is the wart ADR-028 §5 records for
    # config.output; here it is avoidable, so it is refused instead.
    _, transcript = debated(run_dir)
    with pytest.raises(ValueError) as e:
        asyncio.run(
            api.judge(transcript, model="m", budget=4000, backend=FakeBackend(), timeout=30)
        )
    assert "timeout=30" in str(e.value) and "brings its own" in str(e.value)


def test_judge_with_nowhere_to_send_the_call_names_both_ways_to_fix_it(run_dir: Path):
    _, transcript = debated(run_dir)
    with pytest.raises(ValueError) as e:
        asyncio.run(api.judge(transcript, model="m", budget=4000))
    assert "base_url=" in str(e.value) and "backend=" in str(e.value)


def test_scoring_writes_nothing_either(run_dir: Path, tmp_path: Path):
    _, transcript = debated(run_dir)
    backend = FakeBackend(reply(judge_reply(side(0), side(1)), completion_tokens=400))
    sheet = asyncio.run(
        api.judge(transcript, model="m", budget=4000, backend=backend, fact_check=False)
    )

    target = tmp_path / "scores.json"
    assert not target.exists()
    api.write_scores(sheet, target)
    assert target.exists()


# --- §4: one composition, not two --------------------------------------------


def test_the_debate_command_goes_through_the_api(run_dir: Path, monkeypatch):
    """The command's own run, with the adapter faked where api builds it.

    If `debate` ever grew a second composition, this would reach a real socket
    and fail — which is the drift ADR-028 §4 exists to prevent.
    """
    configure(run_dir, ("opening",))
    built = []

    def build(client, base_url, model):
        built.append((base_url, model))
        return FakeBackend(auto=f"side {len(built) - 1}")

    monkeypatch.setattr(api, "OpenAICompatibleBackend", build)
    assert debate_main([str(run_dir / "run.yaml")]) == 0

    assert len(built) == 2
    assert (run_dir / "transcript.json").exists()
