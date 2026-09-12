import shutil
from pathlib import Path

import pytest

from helpers import FIXTURES


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    """A copy of tests/fixtures: a valid run.yaml, its two team files and the pools."""
    shutil.copytree(FIXTURES, tmp_path, dirs_exist_ok=True)
    return tmp_path


@pytest.fixture
def prepared_sources(run_dir: Path, monkeypatch) -> Path:
    """Point retrieval at this test's own copy of the pools (ADR-014 §5).

    Every test that runs prep gets its own writable copy, so one can corrupt a row
    without affecting the next, and none of them read the developer's real
    ~/.cache/debatebench/sources.
    """
    sources = run_dir / "sources"
    monkeypatch.setenv("DEBATEBENCH_SOURCES_DIR", str(sources))
    return sources
