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
    # No dataset library either: retrieval reads plain JSONL (ADR-012 §5).
    ("debatebench.retrieval", {"httpx", "yaml", "datasets", "huggingface_hub", "pandas"}),
    ("debatebench.judging", {"httpx", "yaml"}),  # scoring is pure; only the CLI talks HTTP
    ("debatebench.config", {"httpx"}),
    ("debatebench.openai_compat", {"yaml"}),
    # ADR-027: the stream is stdlib json, and a consumer importing it must not
    # drag in HTTP or YAML.
    ("debatebench.event_stream", {"httpx", "yaml"}),
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
