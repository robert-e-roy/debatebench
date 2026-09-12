"""Prep retrieval: deterministic, orchestrator-side, no model call (ADR-012).

Two pools, two methods (ADR-012 §2). The shared ``sources`` pool holds both
sides' material mixed together, so it is filtered on topic *and* side; a team's
own ``corpus`` holds only its own side's material, so it is filtered on topic
alone. Both are JSONL files that must already exist on disk — nothing here
downloads anything (ADR-012 §5), and this module is standard library only, so
no dataset library joins ADR-008's two runtime dependencies.

Retrieval is free: no model call, no tokens, no budget. What ``prep_budget``
buys is the one synthesis call that reads what this module returns.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

from .transcript import Evidence

__all__ = ["RetrievalError", "SOURCES", "TOP_K", "retrieve", "sources_dir"]

# The vetted source names (ADR-012 §5). Not an arbitrary string: a name not on
# this list is a config error, because both licences were checked by hand.
SOURCES = ("args-me", "debatesum")

# Per pool, so a side with its own corpus can carry up to 20 (ADR-012 §2).
TOP_K = 10

DEFAULT_SOURCES_DIR = Path.home() / ".cache" / "debatebench" / "sources"
SOURCES_DIR_VARIABLE = "DEBATEBENCH_SOURCES_DIR"

# Words that match everything and so distinguish nothing between two motions.
_STOPWORDS = frozenset(
    """a an and are as at be been but by do does for from had has have how i if in into is it
    its more most no not of on or should so than that the their them then there these they this
    to too was we were what when where which who why will with would you your""".split()
)
_WORD = re.compile(r"[a-z0-9]+")

_SHARED_FIELDS = ("id", "text", "topic", "side", "source")
_CORPUS_FIELDS = ("id", "text", "topic", "source")  # a team's own corpus carries no side


class RetrievalError(Exception):
    """A pool that can't be read as written."""


def sources_dir() -> Path:
    """Where the prepared JSONL files live (ADR-012 §5, ADR-014 §5)."""
    override = os.environ.get(SOURCES_DIR_VARIABLE)
    return Path(override).expanduser() if override else DEFAULT_SOURCES_DIR


def retrieve(
    topic: str, side: str, sources: Sequence[str], corpus: Path | None
) -> tuple[Evidence, ...]:
    """Everything one side has to prepare with: the shared pool, then its own corpus.

    The two pools are searched separately and layered, per ADR-007 §3. Ordering is
    deterministic — score, then the order rows appear in the file — so the same
    config retrieves the same passages every run.
    """
    query = _tokenize(topic)
    passages: list[Evidence] = []
    for name in sources:
        path = sources_dir() / f"{name}.jsonl"
        ranked = _ranked(path, _SHARED_FIELDS, query, _MISSING_SOURCE.format(name=name, path=path))
        passages += _take(ranked, side)
    if corpus is not None:
        ranked = _ranked(corpus, _CORPUS_FIELDS, query, _MISSING_CORPUS.format(path=corpus))
        passages += _take(ranked, None)
    return tuple(passages)


_MISSING_SOURCE = (
    "source {name!r} is not prepared: no file at {path}. Datasets are a one-time "
    "manual setup step (ADR-012 §5) — prepare the JSONL there, or set "
    "DEBATEBENCH_SOURCES_DIR to where it already is."
)
_MISSING_CORPUS = "the team's corpus file does not exist: {path}"


def _ranked(
    path: Path, fields: tuple[str, ...], query: frozenset[str], missing_hint: str
) -> tuple[tuple[int, int, dict], ...]:
    """A pool scored against one query, read and scored once however many sides ask.

    Both sides of a debate share a topic, so they share a query and a ranking —
    only the side filter differs. Scoring args-me twice per run would mean
    tokenizing every row twice for an identical result.
    """
    try:
        stat = path.stat()
    except FileNotFoundError as e:
        raise RetrievalError(missing_hint) from e
    except OSError as e:
        raise RetrievalError(f"{path}: cannot be read: {e}") from e
    # Size and mtime are part of the key, so an edited pool is re-read, not remembered.
    return _ranked_cached(path, stat.st_mtime_ns, stat.st_size, fields, query)


@lru_cache(maxsize=8)
def _ranked_cached(
    path: Path, mtime_ns: int, size: int, fields: tuple[str, ...], query: frozenset[str]
) -> tuple[tuple[int, int, dict], ...]:
    """Rows this query matches at all, best first.

    Scoring is deliberately simple and documented rather than tuned: a row scores
    twice for each query word in its ``topic`` and once for each in its ``text``,
    and a row matching no query word is not retrieved. Ties keep the file's own
    order, which is what makes a run reproducible (ADR-014, open questions).
    """
    ranked = []
    for position, row in enumerate(_read(path, fields)):
        score = 2 * len(query & _tokenize(row["topic"])) + len(query & _tokenize(row["text"]))
        if score:
            ranked.append((-score, position, row))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return tuple(ranked)


def _take(ranked: tuple[tuple[int, int, dict], ...], side: str | None) -> list[Evidence]:
    """The best ``TOP_K`` of one side's rows. ``side`` is None for a team's own corpus,
    whose rows are all its own already (ADR-012 §2)."""
    chosen = [row for _, _, row in ranked if side is None or row["side"] == side]
    return [
        Evidence(id=row["id"], source=row["source"], text=row["text"]) for row in chosen[:TOP_K]
    ]


def _read(path: Path, fields: tuple[str, ...]) -> list[dict]:
    """Every row of a JSONL pool, with each row checked before anything is retrieved."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise RetrievalError(f"{path}: cannot be read: {e}") from e

    rows = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as e:
            raise RetrievalError(f"{path} line {number}: not valid JSON: {e}") from e
        if not isinstance(row, dict):
            raise RetrievalError(f"{path} line {number}: each line must be a JSON object")
        for field in fields:
            value = row.get(field)
            if not isinstance(value, str) or not value.strip():
                raise RetrievalError(
                    f"{path} line {number}: {field} must be a non-empty string, "
                    f"got {value!r}"
                )
        rows.append(row)
    return rows


def _tokenize(text: str) -> frozenset[str]:
    """Words worth matching on: lowercased, stopwords dropped, plurals folded in."""
    words = set()
    for word in _WORD.findall(text.lower()):
        if word in _STOPWORDS:
            continue
        words.add(word[:-1] if len(word) > 3 and word.endswith("s") else word)
    return frozenset(words)
