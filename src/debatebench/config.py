"""Load and validate run.yaml and the team files it names (ADR-002, ADR-007).

Every problem is a ConfigError naming the file and the key, and nothing the
user didn't write gets a default. The one generated value is ``seed``, which
ADR-007 §5 makes optional: when it's absent, one is generated here and flagged
so the caller logs it and records it.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import yaml

from .retrieval import SOURCES
from .yaml_loader import load_yaml

PHASES = ("prep", "opening", "rebuttal", "retort", "conclusion")
MOTION_SIDES = ("pro", "con")  # for and against the motion (ADR-007 §7)
LENGTHS = ("short", "medium", "long")  # a phase entry's :suffix (ADR-016 §1)

_RUN_KEYS = {"topic", "format", "teams", "sources", "seed", "output", "judge"}
_FORMAT_KEYS = {"phases"}
_JUDGE_KEYS = {"transcript", "model", "base_url", "budget", "output", "fact_check"}
_SIDE_KEYS = {"team", "side", "model", "base_url", "budget", "prep_budget"}
_TEAM_KEYS = {"id", "name", "voice", "stance", "values", "corpus"}

# Keys ADR-007 removed, with what replaced them. ADR-020 gave judge: back a
# meaning, so it is no longer listed here.
_REMOVED_RUN_KEYS: dict[str, str] = {}
_REMOVED_FORMAT_KEYS = {
    "prep": "format.prep was removed (ADR-007); list 'prep' in format.phases to run Prep",
    "rounds": "format.rounds was removed (ADR-007); repeat phase names in format.phases instead",
}
# Keys ADR-016 removed from a teams: entry, with what replaced them.
_REMOVED_SIDE_KEYS = {
    "length": "a per-team length was superseded by ADR-016; put it on the phase instead, "
    "as a suffix like 'rebuttal:long' in format.phases",
}
# Run-time settings, which belong in run.yaml and never in a team file (ADR-002).
_RUNTIME_KEYS = {"side", "model", "base_url", "budget", "prep_budget"}

# Generated seeds stay below 2**31 so servers with 32-bit seeds accept them.
_GENERATED_SEED_BOUND = 2**31


class ConfigError(Exception):
    """A run.yaml or team file that can't be used as written."""


@dataclass(frozen=True)
class Team:
    """A team file: the side's identity (ADR-002). No model or budget, ever."""

    path: Path
    id: str
    name: str
    voice: str
    stance: str
    values: tuple[str, ...]
    corpus: str | None  # as written, which is what a transcript records (ADR-007 §6)
    corpus_path: Path | None  # resolved from the team file's own directory (ADR-014 §1)


@dataclass(frozen=True)
class Side:
    """One entry in run.yaml's teams list, with its team file loaded."""

    index: int
    team: Team
    team_file: str  # the path as written in run.yaml, which is what a transcript records
    side: Literal["pro", "con"]  # for or against the motion (ADR-007 §7)
    model: str
    base_url: str
    budget: int
    prep_budget: int | None  # set exactly when phases include prep (ADR-007 §2)


@dataclass(frozen=True)
class JudgeConfig:
    """run.yaml's optional judge: block (ADR-020 §1). Flags override every field."""

    transcript: Path  # what judge reads; defaults to the run's own output: (ADR-020 §7)
    model: str
    base_url: str
    budget: int
    output: Path
    fact_check: bool


@dataclass(frozen=True)
class RunConfig:
    path: Path
    topic: str
    phases: tuple[str, ...]  # bare names; a transcript records these (ADR-016 §6)
    lengths: tuple[str | None, ...]  # each phase's :suffix, or None (ADR-016 §1)
    sides: tuple[Side, Side]
    sources: tuple[str, ...]  # as written; resolving them is B4's (ADR-007 §6)
    seed: int
    seed_generated: bool  # run.yaml had no seed: log this one and record it (ADR-007 §5)
    output: Path
    judge: JudgeConfig | None  # ADR-020 §1; absent is valid and is the pre-ADR-020 shape


def load_run(path: str | Path) -> RunConfig:
    run_path = Path(path).expanduser().resolve()
    data = _load_mapping(run_path, "run config")
    _check_keys(run_path, data, _RUN_KEYS, "", _REMOVED_RUN_KEYS)

    topic = _str(run_path, data, "topic", "topic")
    phases, lengths = _phases(run_path, data)
    has_prep = "prep" in phases

    if "teams" not in data:
        raise _fail(run_path, "teams is required")
    teams = data["teams"]
    if not isinstance(teams, list):
        raise _fail(run_path, f"teams must be a list of two team entries, got {_describe(teams)}")
    if len(teams) != 2:
        raise _fail(run_path, f"teams must list exactly two teams (ADR-007), found {len(teams)}")
    first, second = (_side(run_path, entry, index, has_prep) for index, entry in enumerate(teams))
    if first.side == second.side:
        raise _fail(
            run_path,
            f"teams[0] and teams[1] are both {first.side!r}; "
            "one team must be pro and the other con (ADR-007)",
        )

    sources = _sources(run_path, data)
    seed = _opt_int(run_path, data, "seed", "seed", minimum=0)
    seed_generated = seed is None
    if seed is None:
        seed = secrets.randbelow(_GENERATED_SEED_BOUND)
    output = _resolve(run_path, _str(run_path, data, "output", "output"))
    judge = _judge(run_path, data, output)

    return RunConfig(
        path=run_path,
        topic=topic,
        phases=phases,
        lengths=lengths,
        sides=(first, second),
        sources=sources,
        seed=seed,
        seed_generated=seed_generated,
        output=output,
        judge=judge,
    )


def load_team(path: Path) -> Team:
    data = _load_mapping(path, "team file")
    for key in data:
        if key in _RUNTIME_KEYS:
            raise _fail(
                path,
                f"{key} is a run-time setting; set it on this team's entry in run.yaml, "
                "not in the team file (ADR-002)",
            )
    _check_keys(path, data, _TEAM_KEYS, "")
    corpus = _opt_str(path, data, "corpus", "corpus")
    return Team(
        path=path,
        id=_str(path, data, "id", "id"),
        name=_str(path, data, "name", "name"),
        voice=_str(path, data, "voice", "voice"),
        stance=_str(path, data, "stance", "stance"),
        values=_str_list(path, data, "values", "values"),
        corpus=corpus,
        # A team file is reused across runs, so its corpus travels with it rather
        # than with whichever run.yaml names it that day (ADR-014 §1).
        corpus_path=_resolve(path, corpus) if corpus is not None else None,
    )


def _sources(run_path: Path, data: dict[str, Any]) -> tuple[str, ...]:
    """The shared pool names, which must be ones whose licence was checked (ADR-012 §5)."""
    sources = _opt_str_list(run_path, data, "sources", "sources") or ()
    for index, name in enumerate(sources):
        if name not in SOURCES:
            raise _fail(
                run_path,
                f"sources[{index}] is {name!r}, which is not a vetted source "
                f"({', '.join(SOURCES)}). Each one's licence is checked by hand before "
                "it's allowed here (ADR-012 §5)",
            )
    if len(set(sources)) != len(sources):
        raise _fail(run_path, "sources lists the same source twice")
    return sources


def _judge(run_path: Path, data: dict[str, Any], transcript: Path) -> JudgeConfig | None:
    """run.yaml's optional judge: block (ADR-020 §1). Absent is valid."""
    if "judge" not in data:
        return None
    block = data["judge"]
    if not isinstance(block, dict):
        raise _fail(
            run_path,
            f"judge must be a mapping with model, base_url, budget and output, "
            f"got {_describe(block)}",
        )
    _check_keys(run_path, block, _JUDGE_KEYS, "judge")

    # Named explicitly, or the run's own transcript. Stating it beats a comment
    # explaining that judge's input is the key called output: (ADR-020 §7).
    named = _opt_str(run_path, block, "transcript", "judge.transcript")
    reads = _resolve(run_path, named) if named is not None else transcript

    output = _resolve(run_path, _str(run_path, block, "output", "judge.output"))
    # Name the key the reader actually wrote: blaming judge.transcript for a
    # collision with a default they never typed sends them to the wrong line.
    collisions = [(reads, "judge.transcript")] if named is not None else []
    collisions.append((transcript, "output"))
    for other, key in collisions:
        if output == other:
            raise _fail(
                run_path,
                f"judge.output and {key} are the same file ({output}); judge would rotate "
                "the transcript away and write the score file over it (ADR-020 §6). Give "
                "the score file its own path, such as scores.json",
            )
    return JudgeConfig(
        transcript=reads,
        model=_str(run_path, block, "model", "judge.model"),
        base_url=_base_url(run_path, block, "judge.base_url"),
        budget=_int(run_path, block, "budget", "judge.budget", minimum=1),
        output=output,
        fact_check=_opt_bool(run_path, block, "fact_check", "judge.fact_check", default=True),
    )


def _opt_bool(path: Path, data: dict[str, Any], key: str, where: str, *, default: bool) -> bool:
    if key not in data:
        return default
    value = data[key]
    if not isinstance(value, bool):
        raise _fail(path, f"{where} must be true or false, got {_describe(value)}")
    return value


def _phases(path: Path, data: dict[str, Any]) -> tuple[tuple[str, ...], tuple[str | None, ...]]:
    """The phase list as bare names, plus each entry's length suffix (ADR-016 §5)."""
    if "format" not in data:
        raise _fail(path, "format is required (it holds format.phases)")
    fmt = data["format"]
    if not isinstance(fmt, dict):
        raise _fail(path, f"format must be a mapping, got {_describe(fmt)}")
    _check_keys(path, fmt, _FORMAT_KEYS, "format", _REMOVED_FORMAT_KEYS)
    if "phases" not in fmt:
        raise _fail(path, "format.phases is required")
    entries = fmt["phases"]
    if not isinstance(entries, list):
        raise _fail(path, f"format.phases must be a list of phase names, got {_describe(entries)}")
    if not entries:
        raise _fail(path, "format.phases must list at least one phase")

    names: list[str] = []
    lengths: list[str | None] = []
    for index, entry in enumerate(entries):
        where = f"format.phases[{index}]"
        if isinstance(entry, dict) and len(entry) == 1:
            # 'rebuttal: long' is a YAML mapping; the string wanted is 'rebuttal:long'.
            (key, value), = entry.items()
            raise _fail(
                path,
                f"{where} is a mapping, not a phase name: YAML read '{key}: {value}' as a "
                f"key and value. Remove the space after the colon to write '{key}:{value}' "
                "(ADR-016 §5)",
            )
        if not isinstance(entry, str):
            raise _fail(
                path,
                f"{where} is {_describe(entry)}, not a known phase ({', '.join(PHASES)})",
            )
        if entry.count(":") > 1:
            raise _fail(path, f"{where} is {entry!r}: a phase entry has at most one ':' (ADR-016)")
        name, colon, length = entry.partition(":")
        if name not in PHASES:
            raise _fail(
                path,
                f"{where} is {_describe(entry)}, not a known phase ({', '.join(PHASES)})",
            )
        if colon and length not in LENGTHS:
            raise _fail(
                path,
                f"{where} asks for length {length!r}, which is not one of "
                f"{', '.join(LENGTHS)} (ADR-016 §5)",
            )
        if colon and name == "prep":
            raise _fail(
                path,
                f"{where}: prep takes no length — it is bounded by prep_budget alone "
                "(ADR-016 §4)",
            )
        names.append(name)
        lengths.append(length if colon else None)

    if names.count("prep") > 1:
        raise _fail(path, "format.phases: 'prep' can appear only once")
    if "prep" in names and names[0] != "prep":
        raise _fail(path, "format.phases: 'prep' must come first")
    return tuple(names), tuple(lengths)


def _side(run_path: Path, entry: Any, index: int, has_prep: bool) -> Side:
    where = f"teams[{index}]"
    if not isinstance(entry, dict):
        raise _fail(
            run_path,
            f"{where} must be a mapping with team, model, base_url and budget, got {_describe(entry)}",
        )
    _check_keys(run_path, entry, _SIDE_KEYS, where, _REMOVED_SIDE_KEYS)

    team_text = _str(run_path, entry, "team", f"{where}.team")
    side = _motion_side(run_path, entry, f"{where}.side")
    model = _str(run_path, entry, "model", f"{where}.model")
    base_url = _base_url(run_path, entry, f"{where}.base_url")
    budget = _int(run_path, entry, "budget", f"{where}.budget", minimum=1)
    prep_budget = _opt_int(run_path, entry, "prep_budget", f"{where}.prep_budget", minimum=1)
    if has_prep and prep_budget is None:
        raise _fail(
            run_path, f"{where}.prep_budget is required because format.phases includes 'prep' (ADR-007)"
        )
    if not has_prep and prep_budget is not None:
        raise _fail(
            run_path,
            f"{where}.prep_budget is set but format.phases has no 'prep'; "
            "remove it, or add 'prep' (ADR-007)",
        )

    team_path = _resolve(run_path, team_text)
    if not team_path.is_file():
        raise _fail(run_path, f"{where}.team: team file not found: {team_path}")
    return Side(
        index=index,
        team=load_team(team_path),
        team_file=team_text,
        side=side,
        model=model,
        base_url=base_url,
        budget=budget,
        prep_budget=prep_budget,
    )


def _motion_side(path: Path, data: dict[str, Any], where: str) -> Literal["pro", "con"]:
    if "side" not in data:
        raise _fail(path, f"{where} is required: 'pro' argues for the motion, 'con' against it (ADR-007)")
    value = data["side"]
    if value not in MOTION_SIDES:
        raise _fail(path, f"{where} must be 'pro' or 'con', got {_describe(value)}")
    return value


def _base_url(path: Path, data: dict[str, Any], where: str) -> str:
    if "base_url" not in data:
        raise _fail(
            path,
            f"{where} is required; there's no default, because nothing else says "
            "which server this team talks to (ADR-007)",
        )
    value = data["base_url"]
    if isinstance(value, str):
        parts = urlsplit(value)
        try:
            parts.port  # raises on a malformed port
        except ValueError:
            pass
        else:
            if parts.scheme in ("http", "https") and parts.hostname:
                return value
    raise _fail(
        path,
        f"{where} must be an http:// or https:// URL such as http://127.0.0.1:8080/v1, "
        f"got {_describe(value)}",
    )


def _load_mapping(path: Path, what: str) -> dict[str, Any]:
    try:
        data = load_yaml(path)
    except FileNotFoundError as e:
        raise ConfigError(f"{what} not found: {path}") from e
    except OSError as e:
        raise ConfigError(f"{path}: can't read {what}: {e.strerror or e}") from e
    except yaml.YAMLError as e:
        raise _fail(path, f"YAML error: {e}") from e
    if data is None:
        raise _fail(path, f"{what} is empty")
    if not isinstance(data, dict):
        raise _fail(path, f"{what} must be a mapping of keys to values, got {_describe(data)}")
    return data


def _check_keys(
    path: Path,
    data: dict[Any, Any],
    allowed: set[str],
    where: str,
    removed: dict[str, str] | None = None,
) -> None:
    for key in data:
        if key in allowed:
            continue
        if removed and key in removed:
            raise _fail(path, removed[key])
        location = f" in {where}" if where else ""
        raise _fail(path, f"unknown key {key!r}{location} (allowed: {', '.join(sorted(allowed))})")


def _str(path: Path, data: dict[str, Any], key: str, where: str) -> str:
    if key not in data:
        raise _fail(path, f"{where} is required")
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise _fail(path, f"{where} must be a non-empty string, got {_describe(value)}")
    return value


def _opt_str(path: Path, data: dict[str, Any], key: str, where: str) -> str | None:
    return _str(path, data, key, where) if key in data else None


def _int(path: Path, data: dict[str, Any], key: str, where: str, *, minimum: int) -> int:
    if key not in data:
        raise _fail(path, f"{where} is required")
    value = data[key]
    # bool is a subclass of int, so a plain isinstance check would accept True (ADR-008).
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise _fail(path, f"{where} must be an integer of at least {minimum}, got {_describe(value)}")
    return value


def _opt_int(path: Path, data: dict[str, Any], key: str, where: str, *, minimum: int) -> int | None:
    return _int(path, data, key, where, minimum=minimum) if key in data else None


def _str_list(path: Path, data: dict[str, Any], key: str, where: str) -> tuple[str, ...]:
    if key not in data:
        raise _fail(path, f"{where} is required")
    value = data[key]
    if not isinstance(value, list):
        raise _fail(path, f"{where} must be a list of strings, got {_describe(value)}")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise _fail(path, f"{where}[{index}] must be a non-empty string, got {_describe(item)}")
    return tuple(value)


def _opt_str_list(path: Path, data: dict[str, Any], key: str, where: str) -> tuple[str, ...] | None:
    return _str_list(path, data, key, where) if key in data else None


def _resolve(run_path: Path, text: str) -> Path:
    """A path from a config file, relative to that file's directory (ADR-007 §6)."""
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = run_path.parent / path
    return path.resolve()


def _fail(path: Path, message: str) -> ConfigError:
    return ConfigError(f"{path}: {message}")


def _describe(value: Any) -> str:
    """A wrong value as an error shows it: the value and its YAML type."""
    if value is None:
        return "nothing (null)"
    if isinstance(value, dict):
        return "a mapping"
    if isinstance(value, list):
        return "a list"
    if value == "":
        return "an empty string"
    kinds = {bool: "a boolean", int: "an integer", float: "a number", str: "a string"}
    return f"{value!r} ({kinds.get(type(value), type(value).__name__)})"
