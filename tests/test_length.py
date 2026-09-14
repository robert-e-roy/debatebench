"""ADR-016: length as a `phase:length` suffix — validation, prompt, transcript.

ADR-022 changed what a bare entry means: it asks for `medium` now, not for
nothing. The tests that pinned the old fallback are the ones that flipped.

Retro-fits to finished B1 and B2, per the BUILD-GUIDE's amended exit gates.
"""

import asyncio
import json
from pathlib import Path

import pytest

from debatebench.config import DEFAULT_LENGTH, ConfigError, load_run
from debatebench.orchestrator import run_debate
from debatebench.prompts import LENGTH_SENTENCES
from debatebench.transcript import load_transcript, write_transcript
from helpers import edit_yaml
from test_orchestrator import configure, fakes
from test_prep import prep_debate


def debate_with(run_dir: Path, phases):
    config = configure(run_dir, phases)
    backends = fakes()
    return config, asyncio.run(run_debate(config, backends)), backends


def load_with_phases(run_dir: Path, phases):
    edit_yaml(run_dir / "run.yaml", lambda data: data["format"].__setitem__("phases", list(phases)))
    return load_run(run_dir / "run.yaml")


# --- B1: the phase-entry grammar (ADR-016 §5) --------------------------------


def test_a_suffixed_list_loads_with_its_lengths(run_dir: Path):
    config = configure(run_dir, ("opening:short", "rebuttal:long"))

    assert config.phases == ("opening", "rebuttal")  # bare names (ADR-016 §6)
    assert config.lengths == ("short", "long")


def test_a_bare_list_asks_for_the_default(run_dir: Path):
    # ADR-022 §1: a bare entry is not "no instruction", it is medium.
    assert configure(run_dir, ("opening", "rebuttal")).lengths == ("medium", "medium")


def test_naming_the_default_changes_nothing(run_dir: Path):
    bare = configure(run_dir, ("opening", "rebuttal")).lengths
    assert bare == configure(run_dir, ("opening:medium", "rebuttal:medium")).lengths


def test_a_mixed_list_is_allowed(run_dir: Path):
    config = configure(run_dir, ("opening:short", "rebuttal"))
    assert config.lengths == ("short", DEFAULT_LENGTH)


def test_prep_is_left_out_of_the_default(run_dir: Path, prepared_sources):
    # ADR-022 §2: the default stops at prep, which ADR-016 §4 keeps lengthless.
    config = configure(run_dir, ("prep", "opening"))
    assert config.lengths == (None, "medium")


def test_the_same_phase_can_repeat_with_different_lengths(run_dir: Path):
    config = configure(run_dir, ("rebuttal:short", "rebuttal:long"))
    assert (config.phases, config.lengths) == (("rebuttal", "rebuttal"), ("short", "long"))


BAD_PHASES = [
    ("an unknown length", ["rebuttal:huge"], "not one of short, medium, long"),
    ("a capitalised length", ["rebuttal:Long"], "not one of short, medium, long"),
    ("a length on prep", ["prep:short", "opening"], "prep takes no length"),
    ("two colons", ["opening:short:long"], "at most one ':'"),
    ("an unknown phase name", ["preamble:short"], "not a known phase"),
    # 'rebuttal: long' is a YAML mapping, not the string the schema wants.
    ("a space after the colon", [{"rebuttal": "long"}], "Remove the space after the colon"),
]


@pytest.mark.parametrize("phases, expected", [case[1:] for case in BAD_PHASES],
                         ids=[case[0] for case in BAD_PHASES])
def test_a_malformed_phase_entry_is_rejected(run_dir: Path, phases, expected):
    with pytest.raises(ConfigError, match=expected):
        load_with_phases(run_dir, phases)


def test_a_length_key_on_a_team_points_at_adr_016(run_dir: Path):
    # ADR-016 §2: one mechanism, not two — the per-team field is gone.
    def mutate(data):
        data["format"]["phases"] = ["opening"]
        data["teams"][0]["length"] = "long"

    edit_yaml(run_dir / "run.yaml", mutate)
    with pytest.raises(ConfigError, match="ADR-016"):
        load_run(run_dir / "run.yaml")


# --- B2: the prompt states the target (ADR-016 §7) ---------------------------


def test_the_prompt_states_the_sentence_target(run_dir: Path):
    _, _, backends = debate_with(run_dir, ("opening:short",))

    asked = backends[0].requests[0].messages[1].content
    assert f"about {LENGTH_SENTENCES['short']} sentences" in asked


def test_both_sides_get_the_same_target(run_dir: Path):
    # A suffix is a property of the phase, not of a team (ADR-016 §1).
    _, _, backends = debate_with(run_dir, ("opening:long",))

    expected = f"about {LENGTH_SENTENCES['long']} sentences"
    assert all(expected in backend.requests[0].messages[1].content for backend in backends)


def test_a_bare_phase_states_the_default_target(run_dir: Path):
    # Before ADR-022 this prompt carried no length sentence at all.
    _, _, backends = debate_with(run_dir, ("opening",))

    asked = backends[0].requests[0].messages[1].content
    assert f"about {LENGTH_SENTENCES[DEFAULT_LENGTH]} sentences" in asked


def test_each_phase_carries_its_own_target(run_dir: Path):
    _, _, backends = debate_with(run_dir, ("opening:short", "rebuttal:long"))

    opening, rebuttal = backends[0].requests
    assert "about 2 sentences" in opening.messages[1].content
    assert "about 10 sentences" in rebuttal.messages[1].content


# --- the transcript (ADR-016 §6) ---------------------------------------------


def test_a_turn_records_the_length_it_was_asked_for(run_dir: Path):
    _, transcript, _ = debate_with(run_dir, ("opening:long", "rebuttal"))

    assert transcript.turn(0, 0).length == "long"
    assert transcript.turn(1, 0).length == "medium"  # resolved before the run (ADR-022 §3)


def test_a_prep_turn_never_carries_a_length(run_dir: Path, prepared_sources):
    _, transcript, _ = prep_debate(run_dir, ("prep", "opening:short"))

    assert transcript.turn(0, 0).phase == "prep" and transcript.turn(0, 0).length is None
    assert transcript.turn(1, 0).length == "short"


def test_every_written_debate_turn_names_its_length(run_dir: Path):
    # ADR-022 §4: the file says what was asked for, so a later change of default
    # cannot re-interpret it. Schema version is untouched — §5.
    config, transcript, _ = debate_with(run_dir, ("opening:short", "rebuttal"))
    write_transcript(transcript, config.output)
    document = json.loads(config.output.read_text(encoding="utf-8"))

    assert document["schema_version"] == 2
    assert document["run"]["phases"] == ["opening", "rebuttal"]  # bare names, still
    written = {t["phase"]: t.get("length") for t in document["turns"]}
    assert written == {"opening": "short", "rebuttal": "medium"}


def test_a_written_prep_turn_has_no_length_key(run_dir: Path, prepared_sources):
    # The one place the field is still absent rather than null (ADR-016 §6).
    config, transcript, _ = prep_debate(run_dir, ("prep", "opening"))
    write_transcript(transcript, config.output)
    document = json.loads(config.output.read_text(encoding="utf-8"))

    prep = next(t for t in document["turns"] if t["phase"] == "prep")
    assert "length" not in prep


def test_a_version_1_transcript_still_loads(run_dir: Path):
    # Migrating a v1 file forward is a no-op: it simply has no length fields.
    # A real v1 predates the field entirely, so the fixture strips it as well as
    # the version — otherwise it is a v2 document wearing a v1 number.
    config, transcript, _ = debate_with(run_dir, ("opening",))
    write_transcript(transcript, config.output)
    document = json.loads(config.output.read_text(encoding="utf-8"))
    document["schema_version"] = 1
    for turn in document["turns"]:
        turn.pop("length", None)
    config.output.write_text(json.dumps(document), encoding="utf-8")

    reread = load_transcript(config.output)
    assert reread.schema_version == 1
    assert all(turn.length is None for turn in reread.turns)


def test_a_length_survives_a_write_and_read(run_dir: Path):
    config, transcript, _ = debate_with(run_dir, ("opening:short",))
    write_transcript(transcript, config.output)

    assert load_transcript(config.output).turn(0, 0).length == "short"
