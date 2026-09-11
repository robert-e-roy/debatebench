#!/usr/bin/env python3
"""B0 hardware reality check — throwaway probe (BUILD-GUIDE B0). Not package code.

Measures, on the dev Mac, for the intended debater pairing plus a judge stand-in,
with AFM as a contrast:
  - server load time (cold and warm) and per-process memory footprint;
  - system memory, swap and pressure, sampled every 0.5 s throughout;
  - decode throughput solo vs. concurrent, and one long-prompt turn per model.

Safety: a sampler thread aborts the run and kills every model server the moment
swap use grows past 1 GiB, free disk drops below 15 GiB, or memory pressure goes
critical. Pressure "warn" is recorded but doesn't abort — this machine already
sits near it at baseline, and swap is the direct signal of harm. Servers are also
killed on every exit path, including Ctrl-C.

Raw results: probe/b0/b0_raw.json (rewritten after every stage, so an abort still
leaves data). Server logs: probe/b0/logs/.
"""

import atexit
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOGS = HERE / "logs"
RAW = HERE / "b0_raw.json"
GIB = 1024**3

QWEN = "mlx-community/Qwen3-8B-4bit"
MISTRAL = "mlx-community/Mistral-Small-24B-Instruct-2501-4bit"
NO_THINK = {"enable_thinking": False}  # Qwen3 thinks by default (MLXProbe M0 finding)

SERVERS = {
    "qwen3-8b": {"repo": QWEN, "port": 8081, "template_args": NO_THINK},
    "mistral-small-24b": {"repo": MISTRAL, "port": 8082, "template_args": None},
    # Judge stand-in: a second, independent Qwen3-8B process (8B tier). The 24B-tier
    # case is answered arithmetically in RESULTS.md, not attempted.
    "judge-standin-8b": {"repo": QWEN, "port": 8083, "template_args": NO_THINK},
}
AFM_PORT = 19761

SWAP_GROWTH_LIMIT_GIB = 1.0
DISK_FLOOR_GIB = 15.0
MAX_TOKENS = 256
TURNS = 3
SAMPLE_EVERY_S = 0.5

RUNNING: dict[str, subprocess.Popen] = {}
RESULT: dict = {"stages": [], "events": []}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=15).stdout


# ---------- system measurements ----------

def vm_snapshot():
    out = sh(["vm_stat"])
    page = int(re.search(r"page size of (\d+) bytes", out).group(1))
    vals = {}
    for line in out.splitlines()[1:]:
        m = re.match(r'"?([^":]+)"?:\s+(\d+)\.', line)
        if m:
            vals[m.group(1).strip()] = int(m.group(2))

    def gib(key):
        return vals.get(key, 0) * page / GIB

    # Activity Monitor's "Memory Used": app memory + wired + compressed.
    used = gib("Anonymous pages") - gib("Pages purgeable") + gib("Pages wired down") + gib("Pages occupied by compressor")
    return {
        "used_gib": round(used, 3),
        "free_gib": round(gib("Pages free"), 3),
        "file_backed_gib": round(gib("File-backed pages"), 3),
        "compressed_gib": round(gib("Pages occupied by compressor"), 3),
        "wired_gib": round(gib("Pages wired down"), 3),
        "swapins": vals.get("Swapins", 0),
        "swapouts": vals.get("Swapouts", 0),
    }


def swap_used_gib():
    m = re.search(r"used = ([\d.]+)([MG])", sh(["sysctl", "-n", "vm.swapusage"]))
    value = float(m.group(1))
    return value / 1024 if m.group(2) == "M" else value


def pressure_level():
    # 1 = normal, 2 = warn, 4 = critical
    return int(sh(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"]).strip() or 0)


def disk_free_gib():
    st = os.statvfs(str(Path.home()))
    return st.f_bavail * st.f_frsize / GIB


def footprint_gib(pid):
    m = re.search(r"Footprint:\s+([\d.]+)\s+(KB|MB|GB)", sh(["footprint", "-p", str(pid)]))
    if not m:
        return None
    return round(float(m.group(1)) / {"KB": 1024**2, "MB": 1024, "GB": 1}[m.group(2)], 3)


class Sampler(threading.Thread):
    def __init__(self, baseline_swap):
        super().__init__(daemon=True)
        self.baseline_swap = baseline_swap
        self.samples = []
        self.stage = "init"
        self.abort_reason = None
        self.stopping = threading.Event()
        self.tick = 0

    def run(self):
        while not self.stopping.is_set():
            try:
                s = {"t": round(time.time(), 2), "stage": self.stage, **vm_snapshot(),
                     "swap_used_gib": round(swap_used_gib(), 3), "pressure": pressure_level(),
                     "disk_free_gib": round(disk_free_gib(), 2)}
                if self.tick % 4 == 0:  # per-process footprint every 2 s
                    s["footprint_gib"] = {n: footprint_gib(p.pid) for n, p in list(RUNNING.items()) if p.poll() is None}
                self.tick += 1
                self.samples.append(s)
                self.check_guardrails(s)
            except Exception as e:  # noqa: BLE001 - a probe sampler must keep running
                RESULT["events"].append({"t": time.time(), "sampler_error": repr(e)})
            time.sleep(SAMPLE_EVERY_S)

    def check_guardrails(self, s):
        reason = None
        if s["swap_used_gib"] - self.baseline_swap > SWAP_GROWTH_LIMIT_GIB:
            reason = f"swap grew to {s['swap_used_gib']:.2f} GiB (limit +{SWAP_GROWTH_LIMIT_GIB} GiB over baseline)"
        elif s["disk_free_gib"] < DISK_FLOOR_GIB:
            reason = f"free disk {s['disk_free_gib']:.1f} GiB < {DISK_FLOOR_GIB} GiB"
        elif s["pressure"] >= 4:
            reason = "memory pressure critical"
        if s["pressure"] == 2 and not any(e.get("pressure_warn_stage") == s["stage"] for e in RESULT["events"]):
            RESULT["events"].append({"t": s["t"], "pressure_warn_stage": s["stage"]})
            log(f"note: memory pressure WARN during stage {s['stage']}")
        if reason and not self.abort_reason:
            self.abort_reason = reason
            RESULT["events"].append({"t": s["t"], "abort": reason, "stage": s["stage"]})
            log(f"ABORT: {reason} — killing all model servers")
            kill_all()

    def summary(self, stage):
        rows = [s for s in self.samples if s["stage"] == stage]
        if not rows:
            return {}
        peaks = {}
        for r in rows:
            for n, v in (r.get("footprint_gib") or {}).items():
                if v is not None:
                    peaks[n] = max(peaks.get(n, 0), v)
        return {
            "samples": len(rows),
            "peak_used_gib": max(r["used_gib"] for r in rows),
            "peak_compressed_gib": max(r["compressed_gib"] for r in rows),
            "min_free_gib": min(r["free_gib"] for r in rows),
            "peak_swap_used_gib": max(r["swap_used_gib"] for r in rows),
            "swapouts_delta": rows[-1]["swapouts"] - rows[0]["swapouts"],
            "max_pressure": max(r["pressure"] for r in rows),
            "min_disk_free_gib": min(r["disk_free_gib"] for r in rows),
            "peak_footprint_gib": peaks,
        }


SAMPLER: Sampler | None = None


class Aborted(Exception):
    pass


def check_abort():
    if SAMPLER and SAMPLER.abort_reason:
        raise Aborted(SAMPLER.abort_reason)


# ---------- server management ----------

def kill_all():
    for proc in list(RUNNING.values()):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def http_ok(url):
    try:
        with urllib.request.urlopen(url, timeout=2):
            return True
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
        return False


def launch(name, cmd, ready_url, timeout_s=900):
    LOGS.mkdir(parents=True, exist_ok=True)
    logf = open(LOGS / f"{name}.log", "ab")
    t0 = time.time()
    proc = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT, start_new_session=True)
    RUNNING[name] = proc
    while not http_ok(ready_url):
        check_abort()
        if proc.poll() is not None:
            raise RuntimeError(f"{name} exited during startup (code {proc.returncode}); see logs/{name}.log")
        if time.time() - t0 > timeout_s:
            raise RuntimeError(f"{name} not ready after {timeout_s}s")
        time.sleep(0.25)
    return time.time() - t0


def start_mlx(name):
    cfg = SERVERS[name]
    cmd = [sys.executable, "-m", "mlx_lm.server", "--model", cfg["repo"],
           "--host", "127.0.0.1", "--port", str(cfg["port"])]
    if cfg["template_args"]:
        cmd += ["--chat-template-args", json.dumps(cfg["template_args"])]
    log(f"starting {name} on :{cfg['port']}")
    port_ready_s = launch(name, cmd, f"http://127.0.0.1:{cfg['port']}/v1/models")
    # First request: covers any lazy load plus kernel warm-up.
    t = time.time()
    chat(cfg["port"], [{"role": "user", "content": "Say OK."}], 4)
    first_response_s = port_ready_s + (time.time() - t)
    log(f"{name} ready: port {port_ready_s:.1f}s, first response {first_response_s:.1f}s")
    return {"port_ready_s": round(port_ready_s, 2), "first_response_s": round(first_response_s, 2)}


def start_afm():
    log("starting fm serve")
    s = launch("afm", ["fm", "serve", "--port", str(AFM_PORT)], f"http://127.0.0.1:{AFM_PORT}/health", 60)
    return {"port_ready_s": round(s, 2)}


def stop(name, baseline_used=None):
    proc = RUNNING.pop(name, None)
    if proc and proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(20)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(10)
        except ProcessLookupError:
            pass
    log(f"stopped {name}")
    if baseline_used is None:
        return None
    # Isolation: wait for system memory to come back before the next solo measurement.
    deadline = time.time() + 60
    used = vm_snapshot()["used_gib"]
    while used > baseline_used + 1.5 and time.time() < deadline:
        time.sleep(1)
        used = vm_snapshot()["used_gib"]
    return round(used, 2)


# ---------- requests ----------

def chat(port, messages, max_tokens, *, afm=False, stream=True, temperature=0.0):
    body = {"messages": messages, "temperature": temperature, "stream": stream}
    if afm:
        body.update(model="system", max_completion_tokens=max_tokens)  # fm serve ignores max_tokens (ADR-003)
    else:
        body["max_tokens"] = max_tokens  # no "model" field: use the server's loaded default model
    if stream:
        body["stream_options"] = {"include_usage": True}
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions",
                                 data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    t0 = time.time()
    first = None
    chunks = 0
    parts = []
    usage = None
    with urllib.request.urlopen(req, timeout=900) as r:
        if stream:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                j = json.loads(data)
                if j.get("usage"):
                    usage = j["usage"]
                for ch in j.get("choices") or []:
                    piece = (ch.get("delta") or {}).get("content")
                    if piece:
                        first = first or time.time()
                        chunks += 1
                        parts.append(piece)
        else:
            j = json.loads(r.read())
            usage = j.get("usage")
            parts.append(j["choices"][0]["message"].get("content") or "")
    t1 = time.time()
    return {"t_start": round(t0, 2), "ttft_s": round(first - t0, 3) if first else None,
            "total_s": round(t1 - t0, 3), "chunks": chunks, "usage": usage,
            "text_head": "".join(parts)[:160]}


def debate_messages(side, turn):
    return [
        {"role": "system", "content": "You are a debater in a formal policy debate. Argue your assigned side persuasively and stay on it."},
        {"role": "user", "content": f"Turn {turn}. Give a 300-word statement for the {side} position on a federal carbon tax."},
    ]


LONG_UNIT = ("The committee reviewed the carbon pricing proposal line by line, weighing revenue "
             "recycling, border adjustments, and effects on household energy costs. ")


def long_messages():
    return [{"role": "user", "content": "Notes:\n" + LONG_UNIT * 160 + "\nSummarize the strongest argument in two sentences."}]


def completion_tokens(res):
    u = res.get("usage") or {}
    return u.get("completion_tokens") or res.get("chunks") or 0


def decode_tps(res):
    """Decode rate: tokens after the first, over time after the first token."""
    toks = completion_tokens(res)
    if res.get("ttft_s") is None or toks < 2:
        return round(toks / res["total_s"], 2) if res["total_s"] else None  # end-to-end fallback (non-streaming)
    span = res["total_s"] - res["ttft_s"]
    return round((toks - 1) / span, 2) if span > 0 else None


def run_turns(port, n=TURNS, afm=False):
    out = []
    for i in range(n):
        side = "affirmative" if i % 2 == 0 else "negative"
        r = chat(port, debate_messages(side, i), MAX_TOKENS, afm=afm, stream=not afm)
        r["decode_tps"] = decode_tps(r)
        out.append(r)
        check_abort()
    return out


def run_concurrent(targets, rounds=TURNS):
    """targets: list of (name, port, afm). All start each round together."""
    out = {name: [] for name, _, _ in targets}
    for i in range(rounds):
        barrier = threading.Barrier(len(targets))
        errors = []

        def work(name, port, afm, i=i):
            try:
                barrier.wait()
                side = "affirmative" if i % 2 == 0 else "negative"
                r = chat(port, debate_messages(side, i), MAX_TOKENS, afm=afm, stream=not afm)
                r["decode_tps"] = decode_tps(r)
                out[name].append(r)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{name}: {e!r}")

        threads = [threading.Thread(target=work, args=t) for t in targets]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        if errors:
            raise RuntimeError("; ".join(errors))
        check_abort()
    return out


# ---------- stages ----------

def save():
    RESULT["samples"] = SAMPLER.samples if SAMPLER else []
    RAW.write_text(json.dumps(RESULT, indent=1))


def stage(name, fn):
    SAMPLER.stage = name
    log(f"=== stage {name} ===")
    entry = {"stage": name, "started": time.time()}
    try:
        entry["result"] = fn()
        entry["ok"] = True
    except Aborted as e:
        entry["ok"] = False
        entry["aborted"] = str(e)
        raise
    except Exception as e:
        entry["ok"] = False
        entry["error"] = repr(e)
        log(f"stage {name} failed: {e!r}")
        raise
    finally:
        entry["ended"] = time.time()
        time.sleep(1)  # let one more sample land in this stage
        entry["system"] = SAMPLER.summary(name)
        RESULT["stages"].append(entry)
        save()
    return entry["result"]


def method_probe(port):
    """Decide how token counts are taken: does streaming carry usage, and do chunks equal tokens?"""
    msgs = debate_messages("affirmative", 99)
    s = chat(port, msgs, 64, stream=True)
    n = chat(port, msgs, 64, stream=False)
    return {"stream_usage_present": bool(s["usage"]), "stream_chunks": s["chunks"],
            "nonstream_completion_tokens": (n["usage"] or {}).get("completion_tokens"),
            "stream_completion_tokens": (s["usage"] or {}).get("completion_tokens")}


def main():
    global SAMPLER
    RESULT["env"] = {
        "sw_vers": sh(["sw_vers"]).strip(),
        "chip": sh(["sysctl", "-n", "machdep.cpu.brand_string"]).strip(),
        "ram_gib": int(sh(["sysctl", "-n", "hw.memsize"])) / GIB,
        "python": sys.version.split()[0],
        "mlx_versions": sh([sys.executable, "-c", "import mlx_lm, mlx.core as mx; print(mlx_lm.__version__, mx.__version__)"]).strip(),
        "models": {n: c["repo"] for n, c in SERVERS.items()},
        "max_tokens": MAX_TOKENS, "turns": TURNS, "temperature": 0.0,
    }
    RESULT["baseline"] = {
        **vm_snapshot(), "swap_used_gib": swap_used_gib(), "pressure": pressure_level(),
        "disk_free_gib": round(disk_free_gib(), 2),
        # No per-process list: it records the user's running apps. Describe the
        # baseline workload in RESULTS.md instead.
    }
    base_used = RESULT["baseline"]["used_gib"]
    log(f"baseline: used {base_used:.1f} GiB, compressed {RESULT['baseline']['compressed_gib']:.1f} GiB, "
        f"swap {RESULT['baseline']['swap_used_gib']:.2f} GiB, disk free {RESULT['baseline']['disk_free_gib']:.1f} GiB")
    SAMPLER = Sampler(RESULT["baseline"]["swap_used_gib"])
    SAMPLER.start()
    time.sleep(3)
    q, m, j = SERVERS["qwen3-8b"], SERVERS["mistral-small-24b"], SERVERS["judge-standin-8b"]

    try:
        stage("S1_afm_solo", lambda: {"load": start_afm(), "turns": run_turns(AFM_PORT, afm=True)})
        stop("afm")

        def s2():
            load = start_mlx("qwen3-8b")
            method = method_probe(q["port"])
            RESULT["method"] = method
            log(f"token-count method probe: {method}")
            turns = run_turns(q["port"])
            longr = chat(q["port"], long_messages(), 64)
            return {"load_cold": load, "turns": turns, "long_prompt": longr}
        stage("S2_qwen_solo", s2)
        RESULT["events"].append({"memory_after_qwen_stop_gib": stop("qwen3-8b", base_used)})

        def s3():
            load = start_mlx("mistral-small-24b")
            turns = run_turns(m["port"])
            longr = chat(m["port"], long_messages(), 64)
            return {"load_cold": load, "turns": turns, "long_prompt": longr}
        stage("S3_mistral_solo", s3)

        def s4():
            load = start_mlx("qwen3-8b")  # second start: warm-cache load time
            seq = {"qwen3-8b": run_turns(q["port"]), "mistral-small-24b": run_turns(m["port"])}
            conc = run_concurrent([("qwen3-8b", q["port"], False), ("mistral-small-24b", m["port"], False)])
            return {"qwen_load_warm": load, "sequential": seq, "concurrent": conc}
        stage("S4_pair", s4)

        def s5():
            load = start_afm()
            conc = run_concurrent([("mistral-small-24b", m["port"], False), ("afm", AFM_PORT, True)], rounds=2)
            return {"afm_load": load, "concurrent": conc}
        stage("S5_afm_under_load", s5)
        stop("afm")

        def s6():
            before = SAMPLER.samples[-1]["used_gib"]
            load = start_mlx("judge-standin-8b")
            time.sleep(2.5)  # let a footprint sample land
            fp = footprint_gib(RUNNING["judge-standin-8b"].pid)
            fp_q = footprint_gib(RUNNING["qwen3-8b"].pid)
            sharing = {"used_before_gib": before, "used_after_gib": SAMPLER.samples[-1]["used_gib"],
                       "standin_footprint_gib": fp, "qwen_footprint_gib": fp_q,
                       "independent_copy": bool(fp and fp > 3.5)}
            log(f"weight-sharing check: {sharing}")
            if not sharing["independent_copy"]:
                return {"load": load, "sharing_check": sharing,
                        "skipped": "stand-in footprint too small — weights may be shared between processes; not a valid stand-in"}
            seq = {n: run_turns(SERVERS[n]["port"], n=2) for n in ("qwen3-8b", "mistral-small-24b", "judge-standin-8b")}
            debater_plus_judge = run_concurrent([("mistral-small-24b", m["port"], False), ("judge-standin-8b", j["port"], False)], rounds=2)
            all_three = run_concurrent([(n, SERVERS[n]["port"], False) for n in SERVERS], rounds=2)
            return {"load": load, "sharing_check": sharing, "sequential": seq,
                    "debater_plus_judge": debater_plus_judge, "all_three": all_three}
        if SAMPLER.samples[-1]["pressure"] >= 4 or SAMPLER.samples[-1]["swap_used_gib"] > 0.5:
            RESULT["events"].append({"skipped": "S6_triple", "reason": "pressure critical or swap > 0.5 GiB before escalation"})
            log("skipping S6: memory already strained")
        else:
            stage("S6_triple", s6)
    except Aborted as e:
        RESULT["aborted"] = str(e)
    except Exception as e:  # noqa: BLE001
        RESULT["error"] = repr(e)
    finally:
        for name in list(RUNNING):
            stop(name)
        SAMPLER.stage = "cooldown"
        time.sleep(3)
        SAMPLER.stopping.set()
        RESULT["finished"] = time.time()
        save()
        log(f"done — raw results in probe/b0/{RAW.name}")


def _on_signal(signum, _frame):
    log(f"signal {signum}: killing model servers")
    kill_all()
    sys.exit(1)


atexit.register(kill_all)
signal.signal(signal.SIGINT, _on_signal)
signal.signal(signal.SIGTERM, _on_signal)

if __name__ == "__main__":
    main()
