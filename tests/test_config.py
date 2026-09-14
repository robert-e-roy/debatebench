"""B1's exit gate: every config failure mode from ADR-007, plus the valid cases."""

from pathlib import Path

import pytest

from debatebench.config import ConfigError, load_run
from helpers import edit_text, edit_yaml


def _set(*keys, value):
    """A mutation that sets data[k1][k2]... = value."""

    def mutate(data):
        target = data
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = value

    return mutate


def _drop(*keys):
    def mutate(data):
        target = data
        for key in keys[:-1]:
            target = target[key]
        del target[keys[-1]]

    return mutate


_JUDGE_BLOCK = {
    "model": "qwen3:8b",
    "base_url": "http://127.0.0.1:11434/v1",
    "budget": 6000,
    "output": "scores.json",
}


def _no_prep(data):
    data["format"]["phases"] = ["opening", "rebuttal", "conclusion"]
    for side in data["teams"]:
        del side["prep_budget"]


# --- valid files -----------------------------------------------------------


def test_valid_file_loads(run_dir: Path):
    config = load_run(run_dir / "run.yaml")

    assert config.topic == "A federal carbon tax would do more good than harm."
    assert config.phases == ("prep", "opening", "rebuttal", "retort", "rebuttal", "conclusion")
    assert config.sources == ("args-me", "debatesum")
    assert config.seed == 42 and not config.seed_generated
    assert config.output == (run_dir / "transcript.json").resolve()

    first, second = config.sides
    assert (first.index, second.index) == (0, 1)
    assert (first.side, second.side) == ("pro", "con")
    assert first.model == "qwen3-8b"
    assert first.base_url == "http://127.0.0.1:8080/v1"
    assert (first.budget, first.prep_budget) == (2000, 1500)
    assert first.team.path == (run_dir / "teams" / "liberal.yaml").resolve()
    assert first.team.name == "Progressive Climate Advocate"
    assert first.team.values == ("collective-action", "precaution", "equity")
    assert second.team.corpus is None  # optional


def test_absent_judge_block_is_allowed(run_dir: Path):
    # Every run.yaml written before ADR-020 has no judge: block and stays valid.
    assert load_run(run_dir / "run.yaml").judge is None


def test_judge_block_loads(run_dir: Path):
    edit_yaml(run_dir / "run.yaml", _set("judge", value=_JUDGE_BLOCK))
    judge = load_run(run_dir / "run.yaml").judge

    assert judge is not None
    assert judge.model == "qwen3:8b"
    assert judge.base_url == "http://127.0.0.1:11434/v1"
    assert judge.budget == 6000
    assert judge.output == (run_dir / "scores.json").resolve()
    assert judge.fact_check is True  # ADR-015 §3's default, not written in the file


def test_judge_fact_check_can_be_turned_off_in_the_file(run_dir: Path):
    edit_yaml(run_dir / "run.yaml", _set("judge", value=_JUDGE_BLOCK | {"fact_check": False}))
    judge = load_run(run_dir / "run.yaml").judge
    assert judge is not None and judge.fact_check is False


def test_without_prep_no_prep_budget_needed(run_dir: Path):
    edit_yaml(run_dir / "run.yaml", _no_prep)
    config = load_run(run_dir / "run.yaml")
    assert "prep" not in config.phases
    assert all(side.prep_budget is None for side in config.sides)


def test_absent_seed_is_generated_and_flagged(run_dir: Path):
    # Not a failure case (ADR-007 §5): the loader generates one, ready to be recorded.
    edit_yaml(run_dir / "run.yaml", _drop("seed"))
    config = load_run(run_dir / "run.yaml")
    assert config.seed_generated
    assert isinstance(config.seed, int) and 0 <= config.seed < 2**31


def test_absent_sources_is_allowed(run_dir: Path):
    edit_yaml(run_dir / "run.yaml", _drop("sources"))
    assert load_run(run_dir / "run.yaml").sources == ()


def test_con_may_be_listed_first(run_dir: Path):
    # List order doesn't imply a side (ADR-007 §7).
    def swap(data):
        data["teams"][0]["side"], data["teams"][1]["side"] = "con", "pro"

    edit_yaml(run_dir / "run.yaml", swap)
    assert [side.side for side in load_run(run_dir / "run.yaml").sides] == ["con", "pro"]


def test_repeated_phases_are_allowed(run_dir: Path):
    edit_yaml(run_dir / "run.yaml", _set("format", "phases", value=["prep", "rebuttal", "rebuttal"]))
    assert load_run(run_dir / "run.yaml").phases == ("prep", "rebuttal", "rebuttal")


def test_paths_resolve_from_run_yaml_not_cwd(run_dir: Path, monkeypatch):
    elsewhere = run_dir / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    config = load_run("../run.yaml")
    assert config.sides[0].team.path == (run_dir / "teams" / "liberal.yaml").resolve()
    assert config.output == (run_dir / "transcript.json").resolve()


def test_tilde_expands_to_home(run_dir: Path, monkeypatch):
    home = run_dir / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    edit_yaml(run_dir / "run.yaml", _set("output", value="~/out.json"))
    assert load_run(run_dir / "run.yaml").output == (home / "out.json").resolve()


def test_sources_and_corpus_are_kept_as_written(run_dir: Path):
    # The transcript records what was authored; the resolved path is separate (ADR-014 §1).
    config = load_run(run_dir / "run.yaml")
    assert config.sources == ("args-me", "debatesum")
    assert config.sides[0].team.corpus == "liberal-climate-corpus.jsonl"


def test_corpus_resolves_from_the_team_files_own_directory(run_dir: Path):
    # A team file is reused across runs, so its corpus travels with it (ADR-014 §1).
    config = load_run(run_dir / "run.yaml")
    assert config.sides[0].team.corpus_path == run_dir / "teams" / "liberal-climate-corpus.jsonl"
    assert config.sides[1].team.corpus_path is None  # this team has none


def test_an_unvetted_source_is_an_error(run_dir: Path):
    # Each source's licence is checked by hand before it's allowed (ADR-012 §5).
    edit_yaml(run_dir / "run.yaml", _set("sources", value=["args-me", "kaggle-debates"]))
    with pytest.raises(ConfigError, match=r"sources\[1\] is 'kaggle-debates', which is not a vetted"):
        load_run(run_dir / "run.yaml")


def test_the_same_source_twice_is_an_error(run_dir: Path):
    edit_yaml(run_dir / "run.yaml", _set("sources", value=["args-me", "args-me"]))
    with pytest.raises(ConfigError, match="sources lists the same source twice"):
        load_run(run_dir / "run.yaml")


def test_yes_and_no_stay_strings(run_dir: Path):
    # YAML 1.1 would load this model name as False (ADR-008).
    edit_text(run_dir / "run.yaml", "model: qwen3-8b", "model: no")
    assert load_run(run_dir / "run.yaml").sides[0].model == "no"


# --- run.yaml failures -----------------------------------------------------

RUN_FAILURES = [
    # ADR-007's named cases
    ("missing output", _drop("output"), "output is required"),
    ("missing base_url", _drop("teams", 1, "base_url"), "teams[1].base_url is required"),
    ("prep_budget without prep", _set("format", "phases", value=["opening", "conclusion"]),
     "teams[0].prep_budget is set but format.phases has no 'prep'"),
    ("prep without prep_budget", _drop("teams", 1, "prep_budget"),
     "teams[1].prep_budget is required because format.phases includes 'prep'"),
    ("one team", lambda d: d["teams"].pop(), "exactly two teams (ADR-007), found 1"),
    ("three teams", lambda d: d["teams"].append(dict(d["teams"][0])), "exactly two teams (ADR-007), found 3"),
    # side of the motion (ADR-007 §7)
    ("missing side", _drop("teams", 0, "side"), "teams[0].side is required: 'pro' argues for the motion"),
    ("side is 'for'", _set("teams", 0, "side", value="for"), "teams[0].side must be 'pro' or 'con', got 'for'"),
    ("side is capitalized", _set("teams", 1, "side", value="Con"), "teams[1].side must be 'pro' or 'con', got 'Con'"),
    ("both pro", _set("teams", 1, "side", value="pro"), "teams[0] and teams[1] are both 'pro'"),
    ("both con", _set("teams", 0, "side", value="con"), "teams[0] and teams[1] are both 'con'"),
    # missing required fields
    ("missing topic", _drop("topic"), "topic is required"),
    ("missing format", _drop("format"), "format is required"),
    ("missing phases", _drop("format", "phases"), "format.phases is required"),
    ("missing teams", _drop("teams"), "teams is required"),
    ("missing team", _drop("teams", 0, "team"), "teams[0].team is required"),
    ("missing model", _drop("teams", 0, "model"), "teams[0].model is required"),
    ("missing budget", _drop("teams", 0, "budget"), "teams[0].budget is required"),
    ("missing team file", _set("teams", 0, "team", value="teams/nobody.yaml"), "team file not found"),
    # phases (ADR-007 §6)
    ("no phases listed", _set("format", "phases", value=[]), "at least one phase"),
    ("unknown phase", _set("format", "phases", value=["opening", "crossfire"]),
     "format.phases[1] is 'crossfire' (a string), not a known phase"),
    ("prep not first", _set("format", "phases", value=["opening", "prep"]), "'prep' must come first"),
    ("prep twice", _set("format", "phases", value=["prep", "prep", "opening"]), "'prep' can appear only once"),
    # unknown and removed keys
    ("unknown top-level key", _set("seeed", value=42), "unknown key 'seeed'"),
    ("unknown team entry key", _set("teams", 0, "temperature", value=0.7), "unknown key 'temperature' in teams[0]"),
    ("removed format.rounds", _set("format", "rounds", value=3), "format.rounds was removed"),
    ("removed format.prep", _set("format", "prep", value=True), "format.prep was removed"),
    # judge: is a real block again (ADR-020 §1), so its own validation replaces
    # the removed-key case that used to live here.
    ("judge not a mapping", _set("judge", value="qwen3:8b"), "judge must be a mapping"),
    ("judge missing output", _set("judge", value={k: v for k, v in _JUDGE_BLOCK.items() if k != "output"}),
     "judge.output is required"),
    ("judge unknown key", _set("judge", value=_JUDGE_BLOCK | {"temperature": 0.7}),
     "unknown key 'temperature' in judge"),
    ("judge base_url without scheme", _set("judge", value=_JUDGE_BLOCK | {"base_url": "127.0.0.1:9/v1"}),
     "judge.base_url must be an http:// or https:// URL"),
    ("judge budget is a boolean", _set("judge", value=_JUDGE_BLOCK | {"budget": True}),
     "judge.budget must be an integer of at least 1"),
    ("judge fact_check is not a boolean", _set("judge", value=_JUDGE_BLOCK | {"fact_check": "yes"}),
     "judge.fact_check must be true or false"),
    # ADR-020 §6: the same path would rotate the transcript away and write over it.
    ("judge.output is the transcript", _set("judge", value=_JUDGE_BLOCK | {"output": "transcript.json"}),
     "judge.output and output are the same file"),
    # types
    ("teams not a list", _set("teams", value="teams/liberal.yaml"), "teams must be a list"),
    ("team entry not a mapping", _set("teams", 0, value="teams/liberal.yaml"), "teams[0] must be a mapping"),
    ("base_url without scheme", _set("teams", 0, "base_url", value="127.0.0.1:8080/v1"),
     "teams[0].base_url must be an http:// or https:// URL"),
    ("budget is a boolean", _set("teams", 0, "budget", value=True), "got True (a boolean)"),
    ("budget is a float", _set("teams", 0, "budget", value=2000.0), "got 2000.0 (a number)"),
    ("budget is a string", _set("teams", 0, "budget", value="2000"), "got '2000' (a string)"),
    ("budget is zero", _set("teams", 0, "budget", value=0), "teams[0].budget must be an integer of at least 1"),
    ("negative seed", _set("seed", value=-1), "seed must be an integer of at least 0"),
    ("seed is a boolean", _set("seed", value=True), "got True (a boolean)"),
    ("topic is empty", _set("topic", value=""), "topic must be a non-empty string, got an empty string"),
    ("sources not a list", _set("sources", value="args-me"), "sources must be a list of strings"),
    ("output is null", _set("output", value=None), "output must be a non-empty string, got nothing (null)"),
]


@pytest.mark.parametrize("mutate, expected", [c[1:] for c in RUN_FAILURES], ids=[c[0] for c in RUN_FAILURES])
def test_run_yaml_failure(run_dir: Path, mutate, expected):
    edit_yaml(run_dir / "run.yaml", mutate)
    with pytest.raises(ConfigError) as e:
        load_run(run_dir / "run.yaml")
    assert expected in str(e.value)
    assert str(run_dir.resolve()) in str(e.value)  # names the file


# --- failures only raw YAML can express (the strict loader, ADR-008) -------

YAML_FAILURES = [
    ("malformed YAML", ("teams:", "teams: [unclosed"), "YAML error"),
    ("octal seed", ("seed: 42", "seed: 042"), "'042' is not a plain decimal integer (YAML 1.1 would read it as 34)"),
    ("hex budget", ("budget: 2000", "budget: 0x7D0"), "'0x7D0' is not a plain decimal integer"),
    ("base-60 seed", ("seed: 42", "seed: 1:30"), "YAML 1.1 would read it as 90"),
    ("underscored budget", ("budget: 2000", "budget: 2_000"), "'2_000' is not a plain decimal integer"),
    ("duplicate key", ("seed: 42", "seed: 42\nseed: 7"), "found duplicate key 'seed'"),
    ("yes where an integer belongs", ("budget: 2000", "budget: yes"), "got 'yes' (a string)"),
]


@pytest.mark.parametrize("old_new, expected", [c[1:] for c in YAML_FAILURES], ids=[c[0] for c in YAML_FAILURES])
def test_yaml_failure(run_dir: Path, old_new, expected):
    edit_text(run_dir / "run.yaml", *old_new)
    with pytest.raises(ConfigError) as e:
        load_run(run_dir / "run.yaml")
    assert expected in str(e.value)


def test_missing_run_yaml(tmp_path: Path):
    with pytest.raises(ConfigError, match="run config not found"):
        load_run(tmp_path / "run.yaml")


def test_empty_run_yaml(tmp_path: Path):
    (tmp_path / "run.yaml").write_text("")
    with pytest.raises(ConfigError, match="run config is empty"):
        load_run(tmp_path / "run.yaml")


def test_run_yaml_that_is_a_list(tmp_path: Path):
    (tmp_path / "run.yaml").write_text("- topic\n- teams\n")
    with pytest.raises(ConfigError, match="must be a mapping of keys to values"):
        load_run(tmp_path / "run.yaml")


# --- team file failures ----------------------------------------------------

TEAM_FAILURES = [
    ("model in team file", _set("model", value="qwen3-8b"), "model is a run-time setting"),
    ("budget in team file", _set("budget", value=2000), "budget is a run-time setting"),
    ("side in team file", _set("side", value="pro"), "side is a run-time setting"),
    ("missing voice", _drop("voice"), "voice is required"),
    ("missing values", _drop("values"), "values is required"),
    ("unknown key", _set("tone", value="calm"), "unknown key 'tone'"),
    ("values not a list", _set("values", value="equity"), "values must be a list of strings"),
    ("corpus not a string", _set("corpus", value=["a"]), "corpus must be a non-empty string"),
]


@pytest.mark.parametrize("mutate, expected", [c[1:] for c in TEAM_FAILURES], ids=[c[0] for c in TEAM_FAILURES])
def test_team_file_failure(run_dir: Path, mutate, expected):
    team_file = run_dir / "teams" / "liberal.yaml"
    edit_yaml(team_file, mutate)
    with pytest.raises(ConfigError) as e:
        load_run(run_dir / "run.yaml")
    assert expected in str(e.value)
    assert str(team_file.resolve()) in str(e.value)


def test_malformed_team_file(run_dir: Path):
    (run_dir / "teams" / "liberal.yaml").write_text("id: [unclosed\n")
    with pytest.raises(ConfigError, match="YAML error"):
        load_run(run_dir / "run.yaml")
