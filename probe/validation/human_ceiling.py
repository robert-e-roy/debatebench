"""The human-to-human agreement ceiling on the speech-quality dataset.

Usage: python3 human_ceiling.py [path-to-speech-quality-dataset.csv]

Why this exists: JUDGE-VALIDATION.md's acceptance threshold is anchored on the
number this prints, so the number has to be re-derivable rather than trusted.

Tau-C runs -1..+1, but 1.0 is not the target: on a subjective rating task the
15 annotators do not agree with each other either, so their agreement is the
ceiling a judge is measured against. The procedure is the one a judge faces —
leave one annotator out, correlate their ratings against the mean of the other
14 on the speeches they rated, average over annotators.

Runs on the **system** Python, which has scipy. The package venv deliberately
does not: ADR-008 fixes the shipped runtime at httpx + PyYAML, and a validation
script is no more part of the runtime than probe/backend/ is.
"""

from __future__ import annotations

import ast
import collections
import csv
import statistics
import sys
from pathlib import Path

from scipy.stats import kendalltau

DEFAULT = Path.home() / ".cache" / "debatebench" / "validation" / "speech-quality-dataset.csv"
MINIMUMS = (30, 50)


def load(path: Path):
    """annotator -> [(speech index, their rating, mean of the other annotators)]."""
    per = collections.defaultdict(list)
    for index, row in enumerate(csv.DictReader(path.open(encoding="utf-8"))):
        scores = ast.literal_eval(row["goodopeningspeech"])
        try:
            ids = ast.literal_eval(row["labeler_ids"])
        except (ValueError, SyntaxError):
            ids = [piece.strip() for piece in row["labeler_ids"].strip("[]").split(",")]
        if len(ids) != len(scores):  # malformed row: skip rather than mis-pair
            continue
        for annotator, score in zip(ids, scores):
            others = [v for other, v in zip(ids, scores) if other != annotator]
            per[annotator].append((index, score, statistics.mean(others)))
    return per


def ceiling(per, minimum: int, rounded: bool) -> list[float]:
    taus = []
    for judgements in per.values():
        if len(judgements) < minimum:
            continue
        own = [own for _, own, _ in judgements]
        others = [round(mean) if rounded else mean for _, _, mean in judgements]
        tau = kendalltau(own, others, variant="c")[0]
        if tau == tau:  # kendalltau returns nan when a side has one unique value
            taus.append(tau)
    return taus


def main(path: Path) -> None:
    per = load(path)
    counts = sorted(len(v) for v in per.values())
    print(f"annotators: {len(per)}")
    print(f"speeches/annotator: min={counts[0]} median={counts[len(counts) // 2]} max={counts[-1]}")
    for minimum in MINIMUMS:
        for rounded in (False, True):
            taus = ceiling(per, minimum, rounded)
            if not taus:
                print(f"  >={minimum} speeches: no annotator qualified")
                continue
            # Both aggregators are reported because the repo this method comes
            # from contains both, and the choice moves the ceiling by ~0.09 —
            # a quarter of the ceiling itself, not a presentational detail.
            label = "rounded mean" if rounded else "raw mean"
            print(f"  >={minimum:>2} speeches, {label:12}: n={len(taus):3} "
                  f"mean tau-c={statistics.mean(taus):.3f} "
                  f"median={statistics.median(taus):.3f} "
                  f"min={min(taus):.3f} max={max(taus):.3f}")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    if not target.is_file():
        print(f"dataset not found at {target}. It is a one-time manual download "
              "(JUDGE-VALIDATION.md); a run never fetches it.", file=sys.stderr)
        raise SystemExit(2)
    main(target)
