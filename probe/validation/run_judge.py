"""Score speech-quality speeches with a candidate judge, for OPEN-QUESTIONS item 6.

Usage:
  python3 run_judge.py --base-url URL --model NAME --n 160 [--label NAME]
  python3 run_judge.py ... --n 8 --label timing     # measure cost first

Method is the paper's, not ours (JUDGE-VALIDATION.md): its verbatim prompt, a
single 1-5 Likert score, correlated later with Kendall's Tau-C against the
per-speech mean of 15 human ratings.

Three things this deliberately does:

* **Saves after every speech.** A run of this length that dies at speech 140
  must not lose the first 139 — probe_a.py lost eight measured rows to an
  all-or-nothing write earlier in this project.
* **Records a parse failure as a result**, with the reply that caused it, rather
  than dropping the speech. A silently shorter sample would bias the
  correlation, and an error that discards its own evidence is the failure mode
  CLAUDE.md's working-style rule exists to prevent.
* **Stratifies across all 8 sources** proportionally. The sources span a real
  quality gradient (Human expert 4.19 down to Summit 2.96) and a subset missing
  the ends would flatter any judge.
"""

from __future__ import annotations

import argparse
import ast
import collections
import csv
import json
import random
import re
import statistics
import sys
import time
from pathlib import Path
from urllib import request as urlrequest

HERE = Path(__file__).parent
DEFAULT_DATA = Path.home() / ".cache" / "debatebench" / "validation" / "speech-quality-dataset.csv"
SCORE = re.compile(r"<score>\s*([1-5])\s*</score>", re.IGNORECASE)

# Verbatim from the paper's repo: prompts/zero_shot_good_speech_annotation_guidelines.txt
PROMPT = """Imagine the following scenario. You are in the audience of a competitive debate between two opposing speakers on the specified topic. The first speaker delivers the opening speech, aiming to persuade the audience to support the topic.
Please carefully read the topic and the transcript of this opening speech provided below.

Here is the topic:
<topic>
{TOPIC}
</topic>

Here is the speech to be evaluated:
<speech>
{SPEECH}
</speech>

Your task is to indicate to what extent you agree or disagree with the statement:
"This speech is a good opening speech for supporting the topic."

Please select one of the following options:
1 = Strongly disagree
2 = Disagree
3 = Neither agree nor disagree
4 = Agree
5 = Strongly agree

Provide your score in the following format:
<score>
[Insert a single number between 1 and 5]
</score>"""


def load(path: Path) -> list[dict]:
    rows = []
    for row in csv.DictReader(path.open(encoding="utf-8")):
        row["ratings"] = ast.literal_eval(row["goodopeningspeech"])
        row["human_mean"] = statistics.mean(row["ratings"])
        rows.append(row)
    return rows


def stratify(rows: list[dict], n: int, seed: int) -> list[dict]:
    """Proportional across sources, so the quality gradient survives sampling."""
    by_source = collections.defaultdict(list)
    for row in rows:
        by_source[row["source"]].append(row)
    rng = random.Random(seed)
    chosen: list[dict] = []
    for source, group in sorted(by_source.items()):
        take = max(1, round(n * len(group) / len(rows)))
        chosen += rng.sample(group, min(take, len(group)))
    rng.shuffle(chosen)
    return chosen


def ask(base_url: str, model: str, prompt: str, budget: int, seed: int, timeout: float):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "temperature": 0,
        "seed": seed,
        # Both fields, same value — no single one works across servers (ADR-018 §4).
        "max_tokens": budget,
        "max_completion_tokens": budget,
    }).encode()
    call = urlrequest.Request(base_url.rstrip("/") + "/chat/completions", data=body,
                              headers={"Content-Type": "application/json"})
    started = time.monotonic()
    with urlrequest.urlopen(call, timeout=timeout) as answer:
        payload = json.loads(answer.read())
    elapsed = time.monotonic() - started
    message = payload["choices"][0]["message"]
    usage = payload.get("usage") or {}
    return message.get("content") or "", usage.get("completion_tokens"), elapsed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--n", type=int, required=True)
    parser.add_argument("--label", default=None)
    parser.add_argument("--budget", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    args = parser.parse_args()

    if not args.data.is_file():
        print(f"dataset not found at {args.data} — it is a one-time manual download "
              "(JUDGE-VALIDATION.md); a run never fetches it.", file=sys.stderr)
        raise SystemExit(2)

    rows = load(args.data)
    sample = stratify(rows, args.n, args.seed)
    label = args.label or args.model.replace("/", "-").replace(":", "-")
    out = HERE / f"judge-scores-{label}.json"
    results: list[dict] = []
    started = time.monotonic()

    def save() -> None:
        out.write_text(json.dumps({
            "model": args.model, "base_url": args.base_url, "seed": args.seed,
            "budget": args.budget, "requested_n": args.n, "sampled": len(sample),
            "elapsed_s": round(time.monotonic() - started, 1),
            "results": results,
        }, indent=2))

    print(f"== {label}: {len(sample)} speeches, {args.model} ==", flush=True)
    for position, row in enumerate(sample, start=1):
        prompt = PROMPT.replace("{TOPIC}", row["topic"]).replace("{SPEECH}", row["text"])
        record = {"id": row["id"], "source": row["source"], "human_mean": row["human_mean"]}
        try:
            reply, tokens, elapsed = ask(args.base_url, args.model, prompt,
                                         args.budget, args.seed, args.timeout)
            found = SCORE.search(reply)
            record.update(completion_tokens=tokens, elapsed_s=round(elapsed, 1))
            if found:
                record["score"] = int(found.group(1))
            else:
                # Keep the reply: a parse failure that discards its own evidence
                # is the thing this project keeps having to re-derive by hand.
                record["parse_failure"] = reply[-400:] or "(empty reply)"
        except Exception as e:  # noqa: BLE001 - any failure is a recorded result
            record["error"] = f"{type(e).__name__}: {e}"[:300]
        results.append(record)
        save()
        scored = sum(1 for r in results if "score" in r)
        print(f"  {position:>3}/{len(sample)} {row['source'][:15]:15} "
              f"human={row['human_mean']:.2f} judge={record.get('score', '—')} "
              f"({scored} scored, {round(time.monotonic() - started)}s)", flush=True)

    save()
    scored = [r for r in results if "score" in r]
    print(f"\nscored {len(scored)}/{len(results)}; "
          f"{sum(1 for r in results if 'parse_failure' in r)} parse failures, "
          f"{sum(1 for r in results if 'error' in r)} errors")
    if scored:
        print(f"mean judge score {statistics.mean(r['score'] for r in scored):.2f} "
              f"vs human {statistics.mean(r['human_mean'] for r in scored):.2f}")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
