import shutil
from pathlib import Path

import pytest

from helpers import FIXTURES


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    """A copy of tests/fixtures: a valid run.yaml and its two team files."""
    shutil.copytree(FIXTURES, tmp_path, dirs_exist_ok=True)
    return tmp_path
