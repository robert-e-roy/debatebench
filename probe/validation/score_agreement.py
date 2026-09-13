"""Correlate a judge's scores with human ratings — OPEN-QUESTIONS item 6.

Usage: python3 score_agreement.py judge-scores-<label>.json

Kendall's Tau-C via scipy.stats.kendalltau(variant='c'), matching the reference
implementation in the paper's repo (JUDGE-VALIDATION.md): no rescaling of the
judge's score, matched by speech id.

Both human aggregators are reported, because the paper's repo contains both and
the choice moves the *human ceiling* by ~0.09 — 0.405 raw against 0.316 rounded.
A single figure here would imply a precision the method does not have.

Runs on the system Python for scipy; the package venv is untouched (ADR-008).
"""

from __future__ import annotations

import collections
import json
import statistics
import sys
from pathlib import Path

from scipy.stats import kendalltau

# Measured from this dataset by human_ceiling.py, leave-one-annotator-out.
CEILING = {"raw": 0.405, "rounded": 0.316}
# Set in JUDGE-VALIDATION.md before any judge was run.
CREDIBLE, MARGINAL = 0.38, 0.30


# Below this, tau-c on a 5-point scale swings wildly on one or two speeches.
# The 9-speech timing run scored +0.667 — "165% of the human ceiling" — on a
# sample where five sources had exactly one speech each. Printing a verdict
# there would have been the sixth false headline of this project; the arithmetic
# was right and the conclusion was worthless.
MINIMUM_N = 60


def verdict(tau: float, n: int) -> str:
    if n < MINIMUM_N:
        return (f"NO VERDICT — n={n} is below {MINIMUM_N}; tau-c is not stable on a "
                "sample this small, whatever the number says")
    if tau >= CREDIBLE:
        return "CREDIBLE — matches or beats the median human annotator"
    if tau >= MARGINAL:
        return "MARGINAL — below the median human, above the worst"
    return "NOT TRUSTWORTHY — worse than a typical annotator"


def main(path: Path) -> None:
    run = json.loads(path.read_text())
    results = run["results"]
    scored = [r for r in results if "score" in r]
    failures = [r for r in results if "parse_failure" in r]
    errors = [r for r in results if "error" in r]

    print(f"model: {run['model']}   n requested {run['requested_n']}, "
          f"sampled {run['sampled']}, elapsed {run.get('elapsed_s')}s")
    print(f"scored {len(scored)}  parse failures {len(failures)}  errors {len(errors)}")
    if not scored:
        print("nothing to correlate")
        return
    # A high failure rate biases the correlation toward whatever the model found
    # easy to score, so it is reported as a caveat rather than left implicit.
    dropped = len(results) - len(scored)
    if dropped:
        print(f"!! {dropped}/{len(results)} speeches missing from the correlation "
              "— the sample is no longer the stratified one")

    judge = [r["score"] for r in scored]
    human_raw = [r["human_mean"] for r in scored]
    human_rounded = [round(v) for v in human_raw]

    print(f"\nmean judge {statistics.mean(judge):.2f} vs human {statistics.mean(human_raw):.2f} "
          f"(bias {statistics.mean(judge) - statistics.mean(human_raw):+.2f})")

    print("\nKendall's Tau-C against the human mean:")
    for label, human in (("raw", human_raw), ("rounded", human_rounded)):
        tau = kendalltau(judge, human, variant="c")[0]
        ceiling = CEILING[label]
        print(f"  {label:8} tau-c = {tau:+.3f}   (human ceiling {ceiling:.3f}, "
              f"{tau / ceiling * 100:.0f}% of it)")
        if label == "raw":
            print(f"           -> {verdict(tau, len(scored))}")

    print("\nmean score by source (judge vs human), the gradient a judge must reproduce:")
    by_source = collections.defaultdict(list)
    for r in scored:
        by_source[r["source"]].append((r["score"], r["human_mean"]))
    for source, pairs in sorted(by_source.items(), key=lambda kv: -statistics.mean(p[1] for p in kv[1])):
        j = statistics.mean(p[0] for p in pairs)
        h = statistics.mean(p[1] for p in pairs)
        print(f"  {source:16} n={len(pairs):3}  judge={j:.2f}  human={h:.2f}  diff={j - h:+.2f}")

    if failures:
        print(f"\nfirst parse failure, verbatim tail:\n  {failures[0]['parse_failure'][:200]!r}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: score_agreement.py judge-scores-<label>.json", file=sys.stderr)
        raise SystemExit(2)
    target = Path(sys.argv[1])
    if not target.is_file():
        target = Path(__file__).parent / target.name
    if not target.is_file():
        print(f"no such run file: {sys.argv[1]}", file=sys.stderr)
        raise SystemExit(2)
    main(target)
