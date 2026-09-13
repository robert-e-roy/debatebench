"""BACKEND-PROBE.md Part B — performance, one server per invocation.

Usage:  probe_b.py <base_url> <model> <label> [row ...]

Unlike Part A, these rows are only meaningful on a quiet machine: B0's own
caveat was that co-running apps move the numbers as much as the tool does.
The script refuses to record B3/B4 when free memory is low, rather than
publishing a figure that measures contention.

B1 (cold start) is deliberately NOT automated here: it means stopping and
starting a server, which differs per backend and, for a server the user
started, is not this script's decision. Start the server yourself with
`time`, or record the interval from launch to the first successful
/v1/models answer, and note which you did.

Memory is read with footprint(1) — B0's instrument — so figures compare
directly with RESULTS.md. `ps -o rss` reads ~8 MB for a process holding an
8B model on Apple Silicon and must not be used.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).parent
TIMEOUT = httpx.Timeout(connect=5.0, read=600.0, write=60.0, pool=5.0)

# Below this, a latency number measures swap rather than the server.
MIN_FREE_PERCENT = 60

SHORT = [{"role": "user", "content": "Name three colours."}]
# ~4,000 tokens, the size B0 used for its first-token measurement.
LONG_WORDS = 3000


def free_percent() -> float | None:
    try:
        out = subprocess.run(["memory_pressure"], capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return None
    found = re.search(r"free percentage:\s*(\d+)", out)
    return float(found.group(1)) if found else None


def footprint_mb(pid: int) -> float | None:
    try:
        out = subprocess.run(["footprint", "-p", str(pid)], capture_output=True, text=True,
                             timeout=30).stdout
    except Exception:
        return None
    found = re.search(r"phys_footprint:\s+([\d.]+)\s*(KB|MB|GB)", out)
    if not found:
        return None
    value, unit = float(found.group(1)), found.group(2)
    return value * {"KB": 1 / 1024, "MB": 1.0, "GB": 1024.0}[unit]


def generate(client: httpx.Client, url: str, model: str, messages, cap: int):
    """One non-streaming call. Returns (elapsed_s, completion_tokens, prompt_tokens)."""
    elapsed, completion, prompt, _ = timed(client, url, model, messages, cap)
    return elapsed, completion, prompt


def timed(client: httpx.Client, url: str, model: str, messages, cap: int):
    """As generate(), plus the HTTP status — a call that was *rejected* returns in
    milliseconds and must never be mistaken for a fast one (B6)."""
    started = time.monotonic()
    # max_tokens, not max_completion_tokens: Part A found vllm-mlx and Ollama
    # ignore the latter, and an uncapped reply would not be a decode measurement.
    response = client.post(url, json={"model": model, "messages": messages,
                                      "stream": False, "max_tokens": cap})
    elapsed = time.monotonic() - started
    try:
        payload = response.json()
    except ValueError:
        return elapsed, None, None, response.status_code
    usage = payload.get("usage") or {}
    return elapsed, usage.get("completion_tokens"), usage.get("prompt_tokens"), response.status_code


def run(base_url: str, model: str, label: str, wanted: set[str], pid: int | None) -> dict:
    url = base_url.rstrip("/") + "/chat/completions"
    out = HERE / f"probe-b-{label}.json"
    found: dict[str, dict] = {}
    free = free_percent()

    def save() -> None:
        out.write_text(json.dumps({"label": label, "base_url": base_url, "model": model,
                                   "free_percent_at_start": free, "rows": found},
                                  indent=2, default=str))

    def record(row: str, **facts):
        found[row] = facts
        save()
        print(f"  {row}: {json.dumps(facts, default=str)[:300]}", flush=True)

    quiet = free is not None and free >= MIN_FREE_PERCENT
    if not quiet:
        print(f"  ! free memory {free}% < {MIN_FREE_PERCENT}% — B3/B4 will be recorded "
              "as not_measured rather than published as contended numbers", flush=True)

    with httpx.Client(timeout=TIMEOUT) as client:
        if "B2" in wanted:
            record("B2", phys_footprint_mb=footprint_mb(pid) if pid else None,
                   pid=pid, note="at rest unless a generation was in flight")

        if "B3" in wanted:
            if not quiet:
                record("B3", not_measured=f"free memory {free}% < {MIN_FREE_PERCENT}%")
            else:
                # Discard a warm-up call. An idle server's first generation ran at
                # 9.3 tok/s where the next two ran at 35.7 and 36.6 — publishing the
                # cold one would have claimed vllm-mlx was 3.6x slower than B0's
                # 33.9 tok/s for the same weights, which is false.
                generate(client, url, model, SHORT, 200)
                samples = [generate(client, url, model, SHORT, 200) for _ in range(2)]
                rates = [round((completion or 0) / elapsed, 1) for elapsed, completion, _ in samples]
                record("B3", decode_tok_per_s=max(rates), samples_tok_per_s=rates,
                       completion_tokens=[c for _, c, _ in samples],
                       elapsed_s=[round(e, 2) for e, _, _ in samples],
                       note="end-to-end, non-streaming, as B0 measured it; warm-up discarded")

        if "B4" in wanted:
            if not quiet:
                record("B4", not_measured=f"free memory {free}% < {MIN_FREE_PERCENT}%")
            else:
                filler = "The council reviewed the transit budget and scheduled a vote. " * (LONG_WORDS // 10)
                long_prompt = [{"role": "user", "content": filler + "\n\nName three colours."}]
                elapsed, completion, prompt_tokens = generate(client, url, model, long_prompt, 16)
                record("B4", elapsed_s=round(elapsed, 2), prompt_tokens=prompt_tokens,
                       completion_tokens=completion,
                       approx_prefill_tok_per_s=round((prompt_tokens or 0) / elapsed, 1),
                       note="non-streaming, so this is time to LAST token; a true "
                            "time-to-first-token needs a streaming client B0 had and this "
                            "does not. Treat as an upper bound.")

        if "B6" in wanted:
            if not quiet:
                record("B6", not_measured=f"free memory {free}% < {MIN_FREE_PERCENT}%")
            else:
                one, _, _ = generate(client, url, model, SHORT, 120)
                started = time.monotonic()
                with httpx.Client(timeout=TIMEOUT) as second:
                    import threading
                    results = []

                    def fire():
                        try:
                            results.append(timed(second, url, model, SHORT, 120))
                        except Exception as e:
                            results.append((None, None, None, f"raised {type(e).__name__}"))

                    thread = threading.Thread(target=fire)
                    thread.start()
                    timed(client, url, model, SHORT, 120)
                    thread.join()
                both = time.monotonic() - started
                elapsed, completion, _, status = results[0] if results else (None, None, None, None)
                # A rejected call returns in milliseconds. Without checking status and
                # tokens, that reads as "real concurrency" — which is how this row first
                # reported ratio 1.0 against an engine Part A found to be
                # blocking_serialized with waiters=0.
                served = status == 200 and bool(completion)
                record("B6",
                       single_s=round(one, 2), two_together_s=round(both, 2),
                       ratio=round(both / one, 2) if one else None,
                       second_call_status=status, second_call_completion_tokens=completion,
                       second_call_elapsed_s=round(elapsed, 2) if elapsed else elapsed,
                       second_call_actually_served=served,
                       verdict=("concurrent" if served and one and both / one < 1.5
                                else "serialized_or_rejected"),
                       note="a ratio near 1 only means concurrency if the second call was "
                            "actually served; otherwise it was turned away, not run in parallel")

    save()
    print(f"  -> {out}")
    return found


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("usage: probe_b.py <base_url> <model> <label> [row ...]", file=sys.stderr)
        raise SystemExit(2)
    pid = None
    for argument in list(sys.argv[4:]):
        if argument.startswith("pid="):
            pid = int(argument.split("=", 1)[1])
            sys.argv.remove(argument)
    rows = set(sys.argv[4:]) or {"B2", "B3", "B4", "B6"}
    print(f"== Part B: {sys.argv[3]} ({sys.argv[2]}) ==", flush=True)
    run(sys.argv[1], sys.argv[2], sys.argv[3], rows, pid)
