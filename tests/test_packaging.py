"""ADR-029: the release is one attempt, so what it depends on is checked here.

A version on PyPI can never be re-uploaded. Anything that would fail the release
job should therefore fail on a developer's machine first, on the commit that
breaks it — not on the tag, where the remedy is a yank and a new version.
"""

import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _pyproject() -> dict:
    path = ROOT / "pyproject.toml"
    if not path.is_file():
        pytest.skip("no pyproject.toml: running from an installed package, not the tree")
    return tomllib.loads(path.read_text(encoding="utf-8"))


def test_the_lockfile_records_the_version_pyproject_declares():
    """A version bump must relock in the same commit.

    uv.lock pins this project at its own version, so bumping `version` without
    running `uv lock` leaves `uv sync --locked` failing. Both workflows use
    --locked deliberately — a lock that has drifted should fail rather than be
    re-resolved into something untested — which means an un-relocked bump breaks
    the *release* job, after the tag exists. This test moves that discovery to
    the bump itself, where relocking is free.
    """
    lock = ROOT / "uv.lock"
    if not lock.is_file():
        pytest.skip("no uv.lock in this tree")

    declared = _pyproject()["project"]["version"]
    entries = [
        package
        for package in tomllib.loads(lock.read_text(encoding="utf-8"))["package"]
        if package["name"] == "debatebench"
    ]
    assert entries, "uv.lock has no debatebench entry at all"
    assert entries[0]["version"] == declared, (
        f"pyproject declares {declared} and uv.lock records {entries[0]['version']}. "
        "Run `uv lock` and commit it alongside the version bump — otherwise "
        "`uv sync --locked` fails, which is how the release job would find out."
    )


def test_the_released_version_is_installable_by_a_plain_pip_install():
    """ADR-029 §1: a .dev/.a/.b/.rc version is not selected without --pre.

    The README's install line is `pip install debatebench`. A pre-release
    version string would publish a package that line cannot install.
    """
    version = _pyproject()["project"]["version"]
    marker = next((m for m in (".dev", "a", "b", "rc") if m in version.lower()), None)
    assert marker is None or not any(
        part.startswith(("dev", "a", "b", "rc")) for part in version.split(".")[3:]
    ), f"version {version!r} looks like a pre-release; pip install would skip it (ADR-029 §1)"
    assert ".dev" not in version, f"version {version!r} is a dev release (ADR-029 §1)"


def test_both_console_scripts_are_declared():
    # They are the product. A packaging change that dropped one would otherwise
    # only show up when someone installed the wheel.
    scripts = _pyproject()["project"]["scripts"]
    assert scripts == {
        "debate": "debatebench.cli:main",
        "judge": "debatebench.judge_cli:main",
    }


def test_the_dependencies_are_the_two_adr_008_allows():
    """ADR-008: httpx and PyYAML, nothing else without an ADR.

    This also catches the TOML-shape accident that silently moved `dependencies`
    into a [project.urls] table and built a wheel requiring nothing at all.
    """
    names = {
        dep.split(">")[0].split("=")[0].split("[")[0].strip().lower()
        for dep in _pyproject()["project"]["dependencies"]
    }
    assert names == {"httpx", "pyyaml"}


def test_the_project_urls_resolve_to_the_repository():
    # ADR-029: the pyproject comment that used to sit here said a link that does
    # not resolve is worse than none. These are the links it was waiting for.
    urls = _pyproject()["project"]["urls"]
    assert urls["Repository"] == "https://github.com/robert-e-roy/debatebench"
    assert all(url.startswith("https://github.com/robert-e-roy/debatebench") for url in urls.values())
