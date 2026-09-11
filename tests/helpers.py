from pathlib import Path

import yaml

FIXTURES = Path(__file__).parent / "fixtures"


def edit_yaml(path: Path, mutate) -> Path:
    """Rewrite a YAML file after ``mutate`` changes its parsed data in place."""
    data = yaml.safe_load(path.read_text())
    mutate(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


def edit_text(path: Path, old: str, new: str) -> Path:
    """Rewrite a YAML file with one textual substitution, for cases a dump can't express."""
    text = path.read_text()
    assert old in text, f"{old!r} not in {path.name}"
    path.write_text(text.replace(old, new, 1))
    return path
