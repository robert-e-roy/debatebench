#!/usr/bin/env python3
"""Summarize probe/b0/b0_raw.json into the tables RESULTS.md needs. Throwaway."""

import json
import statistics
from pathlib import Path

RAW = json.loads((Path(__file__).resolve().parent / "b0_raw.json").read_text())
STAGES = {s["stage"]: s for s in RAW["stages"]}


def med(values):
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 1) if values else None


def tps(turns):
    return med([t.get("decode_tps") for t in turns])


def ttft(turns):
    return med([t.get("ttft_s") for t in turns])


def toks(turns):
    return med([(t.get("usage") or {}).get("completion_tokens") or t.get("chunks") for t in turns])


def show(label, value):
    print(f"  {label:<46} {value}")


b = RAW["baseline"]
print("BASELINE")
for k in ("used_gib", "compressed_gib", "file_backed_gib", "free_gib", "swap_used_gib", "pressure", "disk_free_gib"):
    show(k, b[k])
print("\nMETHOD", RAW.get("method"))
print("EVENTS", json.dumps(RAW.get("events"), indent=None))
if RAW.get("aborted") or RAW.get("error"):
    print("RUN ENDED EARLY:", RAW.get("aborted") or RAW.get("error"))

print("\nPER-STAGE SYSTEM PEAKS")
for name, s in STAGES.items():
    sy = s.get("system", {})
    print(f"  {name:<20} ok={s.get('ok')} used={sy.get('peak_used_gib')} compressed={sy.get('peak_compressed_gib')} "
          f"swap={sy.get('peak_swap_used_gib')} swapouts={sy.get('swapouts_delta')} pressure_max={sy.get('max_pressure')} "
          f"disk_min={sy.get('min_disk_free_gib')} dur={round(s['ended'] - s['started'])}s")
    if sy.get("peak_footprint_gib"):
        print(f"  {'':<20} footprints={sy['peak_footprint_gib']}")
    if s.get("error") or s.get("aborted"):
        print(f"  {'':<20} !! {s.get('error') or s.get('aborted')}")


def r(stage):
    return (STAGES.get(stage) or {}).get("result") or {}


print("\nLOAD TIMES (s: port ready / first response)")
for label, load in (("qwen3-8b cold", r("S2_qwen_solo").get("load_cold")),
                    ("mistral-small-24b cold", r("S3_mistral_solo").get("load_cold")),
                    ("qwen3-8b warm (2nd start)", r("S4_pair").get("qwen_load_warm")),
                    ("judge stand-in 8b", r("S6_triple").get("load")),
                    ("afm (fm serve)", r("S1_afm_solo").get("load"))):
    if load:
        show(label, f"{load.get('port_ready_s')} / {load.get('first_response_s')}")

print("\nTHROUGHPUT (median decode tok/s | median TTFT s | median completion tokens)")
if r("S1_afm_solo"):
    show("AFM solo (non-streaming, end-to-end)", f"{tps(r('S1_afm_solo')['turns'])} | - | {toks(r('S1_afm_solo')['turns'])}")
for stage, name in (("S2_qwen_solo", "qwen3-8b"), ("S3_mistral_solo", "mistral-small-24b")):
    res = r(stage)
    if res:
        show(f"{name} solo", f"{tps(res['turns'])} | {ttft(res['turns'])} | {toks(res['turns'])}")
        lp = res.get("long_prompt") or {}
        pt = (lp.get("usage") or {}).get("prompt_tokens")
        if lp.get("ttft_s") and pt:
            show(f"{name} long prompt", f"{pt} prompt tokens, TTFT {lp['ttft_s']} s -> ~{round(pt / lp['ttft_s'])} prefill tok/s")
p = r("S4_pair")
if p:
    for n, turns in p["sequential"].items():
        show(f"{n} pair-resident, alone", f"{tps(turns)} | {ttft(turns)} | {toks(turns)}")
    for n, turns in p["concurrent"].items():
        show(f"{n} pair, concurrent", f"{tps(turns)} | {ttft(turns)} | {toks(turns)}")
a = r("S5_afm_under_load")
if a:
    for n, turns in a["concurrent"].items():
        show(f"{n} concurrent (mistral + afm)", f"{tps(turns)} | {ttft(turns)} | {toks(turns)}")
t = r("S6_triple")
if t:
    print("  sharing check:", t.get("sharing_check"))
    if t.get("skipped"):
        print("  S6 skipped:", t["skipped"])
    for key in ("sequential", "debater_plus_judge", "all_three"):
        for n, turns in (t.get(key) or {}).items():
            show(f"{n} triple/{key}", f"{tps(turns)} | {ttft(turns)} | {toks(turns)}")
