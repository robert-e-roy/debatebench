"""BACKEND-PROBE.md B5 — can an 8B and a 24B be co-resident?

Usage: probe_b5.py <base_url> <small_model> <large_model> <label> [pid=N]

This is the row that re-tests B0's headline finding, and it is the one that can
take the machine down: B0 measured Mistral-Small-24B alone at 13.0 GiB and the
pair at about 19.6 GiB, which drove that machine to critical pressure and into
swap. This session has already produced a host-level Metal OOM
(kIOGPUCommandBufferCallbackErrorOutOfMemory) with far less resident.

So it follows B0's discipline rather than finding the limit by crashing into
it: memory is sampled continuously, and if free memory falls under FLOOR the
run stops issuing requests and reports what it saw. A recorded "stopped at the
floor" is a result; an OOM-killed server belonging to someone else is not.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx

HERE = Path(__file__).parent
FLOOR_PERCENT = 10.0          # stop issuing work below this
SAMPLE_SECONDS = 0.5


def free_percent() -> float | None:
    try:
        out = subprocess.run(["memory_pressure"], capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return None
    found = re.search(r"free percentage:\s*(\d+)", out)
    return float(found.group(1)) if found else None


def footprint_gib(pid: int) -> float | None:
    try:
        out = subprocess.run(["footprint", "-p", str(pid)], capture_output=True, text=True,
                             timeout=30).stdout
    except Exception:
        return None
    found = re.search(r"phys_footprint:\s+([\d.]+)\s*(KB|MB|GB)", out)
    if not found:
        return None
    value, unit = float(found.group(1)), found.group(2)
    return round(value * {"KB": 1 / 1024 / 1024, "MB": 1 / 1024, "GB": 1.0}[unit], 2)


class Watch(threading.Thread):
    """Samples free memory and the server's footprint, like B0's 0.5 s sampler."""

    def __init__(self, pid: int | None):
        super().__init__(daemon=True)
        self.pid = pid
        self.samples: list[dict] = []
        self.stop = threading.Event()
        self.floor_hit = False

    def run(self) -> None:
        while not self.stop.is_set():
            free = free_percent()
            sample = {"t": round(time.time(), 1), "free_percent": free,
                      "footprint_gib": footprint_gib(self.pid) if self.pid else None}
            self.samples.append(sample)
            if free is not None and free < FLOOR_PERCENT:
                self.floor_hit = True
            self.stop.wait(SAMPLE_SECONDS)

    def peak(self) -> dict:
        prints = [s["footprint_gib"] for s in self.samples if s["footprint_gib"] is not None]
        frees = [s["free_percent"] for s in self.samples if s["free_percent"] is not None]
        return {"peak_footprint_gib": max(prints) if prints else None,
                "min_free_percent": min(frees) if frees else None,
                "samples": len(self.samples)}


def load(client: httpx.Client, url: str, model: str) -> dict:
    """A tiny generation, purely to force the model resident."""
    started = time.monotonic()
    try:
        response = client.post(url, json={"model": model, "stream": False, "max_tokens": 8,
                                          "messages": [{"role": "user", "content": "hi"}]})
    except httpx.HTTPError as e:
        return {"model": model, "ok": False, "error": f"{type(e).__name__}: {e}"}
    return {"model": model, "ok": response.status_code == 200, "status": response.status_code,
            "elapsed_s": round(time.monotonic() - started, 1),
            "body": None if response.status_code == 200 else response.text[:200]}


def main(base_url: str, small: str, large: str, label: str, pid: int | None) -> None:
    url = base_url.rstrip("/") + "/chat/completions"
    out = HERE / f"probe-b5-{label}.json"
    result: dict = {"label": label, "base_url": base_url, "small_model": small,
                    "large_model": large, "floor_percent": FLOOR_PERCENT,
                    "baseline_free_percent": free_percent(), "steps": []}

    def save() -> None:
        out.write_text(json.dumps(result, indent=2, default=str))

    watch = Watch(pid)
    watch.start()
    try:
        with httpx.Client(timeout=httpx.Timeout(connect=5.0, read=900.0, write=60.0, pool=5.0)) as client:
            for stage, model in (("small", small), ("large", large)):
                free = free_percent()
                if free is not None and free < FLOOR_PERCENT:
                    result["steps"].append({"stage": stage, "model": model,
                                            "skipped": f"free {free}% below floor {FLOOR_PERCENT}%"})
                    save()
                    print(f"  {stage}: SKIPPED, free {free}% below floor", flush=True)
                    break
                step = load(client, url, model)
                step["stage"] = stage
                step["free_percent_after"] = free_percent()
                step["footprint_gib_after"] = footprint_gib(pid) if pid else None
                result["steps"].append(step)
                save()
                print(f"  {stage}: {json.dumps(step, default=str)[:240]}", flush=True)
    finally:
        watch.stop.set()
        watch.join(timeout=5)
        result["watch"] = watch.peak()
        result["floor_hit_during_run"] = watch.floor_hit
        result["final_free_percent"] = free_percent()
        save()

    print(f"  watch: {json.dumps(result['watch'])}", flush=True)
    print(f"  floor hit during run: {watch.floor_hit}", flush=True)
    print(f"  -> {out}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("usage: probe_b5.py <base_url> <small_model> <large_model> <label> [pid=N]",
              file=sys.stderr)
        raise SystemExit(2)
    server_pid = None
    for argument in sys.argv[5:]:
        if argument.startswith("pid="):
            server_pid = int(argument.split("=", 1)[1])
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], server_pid)
