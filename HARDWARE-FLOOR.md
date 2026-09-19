# Hardware floor for the Mac app — what memory `DebateKit` actually needs

ADR-002 asks for "its own M0-style hardware probe" before the Swift app trusts
any sizing. This is the answer that can be given from measurements already taken,
with the parts that are still extrapolation marked as such.

## The caveat that shapes everything below

**The Mac app will not use Ollama.** Most of this project's day-to-day numbers
are Ollama numbers, and they do **not** transfer as figures. What transfers is
arithmetic and what does not is defaults.

| measured on | transfers to a Swift/MLX app? |
|---|---|
| **`mlx_lm.server` 0.31.3 / mlx 0.32.0** (B0, `RESULTS.md`) | **Yes, directly.** Same framework family the app will use. |
| **AFM via `fm serve`** | **Yes.** AFM is a system process; the runtime around it is irrelevant. |
| **Ollama** (everything since ADR-018) | **Only as arithmetic.** The footprints are real but the *context defaults* that produced them are Ollama's model metadata, not a property of the weights. |

The single most transferable number is the **KV cache growth rate**, because it
is a property of the architecture rather than the runtime:

- **Qwen3-8B-4bit: 144 KiB per token**
- **Mistral-24B-4bit: 160 KiB per token**

At 16k context that is **2.25 GiB and 2.5 GiB of cache** on top of the weights.
A Swift app that sets its own context length controls this directly, which is an
advantage over what was measured here — Ollama chose 40,960 for `qwen3:14b` and
262,144 for `qwen3:4b`, and the second turned a 2.5 GB file into ~43 GB resident.

## Measured footprints — the MLX rows are the load-bearing ones

Machine: **Apple M2 Pro, 32.0 GiB unified memory**, macOS 27.

| model | runtime | weights resident | peak | throughput |
|---|---|---|---|---|
| **AFM** | `fm serve` | system process | **+1.8 GiB** while in use | 38.6 tok/s |
| **Qwen3-8B-4bit** | **`mlx_lm`** | 4.8 GiB after load | **6.6 GiB** after a 4k prompt | 33.9 tok/s |
| **Mistral-Small-24B-4bit** | **`mlx_lm`** | 0.3 → **13.0 GiB in ~5 s** | critical pressure, **aborted** | never produced a token |
| `qwen3:14b` capped 16k | Ollama | — | 12.2 GB | — |
| `phi4:14b` at 16k | Ollama | — | 12.7 GB | — |

## The floor, by Mac configuration

Assume a desktop baseline. B0 measured **14.8 GiB** on this machine in ordinary
use (browser ~5 GiB, an IDE, a chat app, the window server) and estimated ~8 GiB
for a quiet machine. An app cannot assume quiet.

| Mac | usable after baseline | what fits | verdict |
|---|---|---|---|
| **M1 / M2, 8 GB** | ~4 GiB | **AFM** (+1.8 GiB, system-managed) | **Debates yes, judging no.** AFM's ~4,096-token session cannot hold a transcript — the request fails with HTTP 500, which is a hard limit, not a quality one. A 4B judge at ~3.7 GiB *might* fit and is unvalidated. |
| **M1 / M2, 16 GB** | ~11 GiB | **Qwen3-8B at ~7 GiB** (4.8 weights + 2.25 KiB cache at 16k) | **The floor for a self-contained app.** One model debates and judges, and it is the only judge here with validated ordering (Tau-C +0.547). |
| **M1 Pro/Max, M2 Pro, 32 GB** | ~17 GiB in real use | a 14B-class debater **or** a 14B judge, **one at a time** | Works. Co-residence does not — see below. |
| **any size tested** | — | **no 24B+ model** | Mistral-24B aborted at load on MLX; every Ollama-side 24B+ either could not emit the format or declined to judge. |

## Two architectural constraints, not preferences

**1. Models load sequentially, never co-resident.** B0: the 8B + 24B pair is
about 19.6 GiB of weights, comfortably under Metal's recommended working set on
this machine (24.96 GiB) — **total RAM binds, not the GPU.** 14.8 baseline + 19.6
= 34.4 GiB against 32 GiB installed. And B0's own line: *"adding a judge rules
co-residence out at either size."*

So `DebateKit` must load one model, finish a phase, release it, and load the
next. Holding a debater and a judge in memory together is not a 32 GB feature; it
is a feature of a machine nobody in the target audience has.

**2. The app owns the context length, and must.** Every memory incident in this
project came from a runtime default, not from weights. The app should set context
from what the work needs, which is measurable: **the largest prompt any turn has
ever needed here is 2,241 tokens.** A debate turn needs ~4k; a judge call with a
12,000-token reply budget needs ~16k. Capping is free — verified output-neutral,
8 of 8 turns byte-identical capped against uncapped.

## What this costs the product

**A 16 GB floor for judging is a product decision, not just a spec one.** 8 GB
Macs are a large share of the installed base. That leaves three options and they
should be chosen deliberately:

1. **Require 16 GB for judging**, ship debating on 8 GB. Honest, and halves the
   addressable machines for the headline feature.
2. **Ship an 8 GB judge** — a 4B model at ~3.7 GiB. Possible; **unvalidated**,
   and `MODEL-COVERAGE` records that the small class produces score sheets whose
   quality is not established.
3. **Judge in the cloud.** Collides with ADR-002's privacy-first framing and
   should not be adopted quietly.

## What is not measured, and needs a real machine

- **No M1 of any size has been tested.** Every number here is M2 Pro. M1 has
  lower memory bandwidth, so throughput will differ; footprints should not.
- **8 GB and 16 GB rows are extrapolated** from 32 GiB measurements plus the KV
  arithmetic. They are arithmetic, not observations.
- **No MLX measurement exists for a 14B model** — the 12.2/12.7 GB figures are
  Ollama's.
- **Swift/MLX (`MLXLLM`) has never been run here at all.** Every MLX number is
  from `mlx_lm.server`, the Python implementation.

The probe that would close this: one M1 8 GB and one M1 16 GB, running
`MLXLLM` from Swift, recording footprint after load, peak after a 4k prompt, and
tokens/second — the same three columns B0 used, so the rows line up.

## Related, for when the app is built

Model files are large and their location interacts with the App Sandbox, and
shipping them interacts with notarization and update size. Those are app-shape
questions rather than sizing ones — see Axiom `axiom-macos`
(`skills/sandbox-and-file-access.md` for where a downloaded model may live,
`skills/direct-distribution.md` for Developer ID and Sparkle).
