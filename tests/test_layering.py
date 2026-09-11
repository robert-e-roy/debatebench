"""ADR-008: httpx only in the adapter, PyYAML only in config loading."""

import subprocess
import sys

import pytest

CASES = [
    ("debatebench.backend", {"httpx", "yaml"}),
    ("debatebench.transcript", {"httpx", "yaml"}),
    ("debatebench.events", {"httpx", "yaml"}),
    ("debatebench.prompts", {"httpx", "yaml"}),
    ("debatebench.orchestrator", {"httpx", "yaml"}),
    ("debatebench.config", {"httpx"}),
    ("debatebench.openai_compat", {"yaml"}),
]


@pytest.mark.parametrize("module, forbidden", CASES, ids=[c[0] for c in CASES])
def test_module_does_not_import(module, forbidden):
    # A fresh interpreter, so modules other tests imported don't count.
    code = (
        f"import sys, {module}\n"
        f"leaked = sorted(set({sorted(forbidden)!r}) & set(sys.modules))\n"
        "assert not leaked, leaked\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
