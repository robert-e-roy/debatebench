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


---

# The audience table: every Apple Silicon Mac, and what it can run

Apple Silicon only — Intel Macs cannot run any of this usefully and are out of
scope. **The minimum column is what matters**, because it is the machine a buyer
gets without choosing an upgrade, and therefore the machine the app must assume.

## Minimum unified memory, by generation

| chip | year | **Mac minimum** | Pro min | Max min | Ultra min |
|---|---|---|---|---|---|
| **M1** | 2020 | **8 GB** | 16 GB | 32 GB | 64 GB |
| **M2** | 2022 | **8 GB** | 16 GB | 32 GB | 64 GB |
| **M3** | 2023 | **8 GB** | 18 GB | 36 GB | 96 GB |
| **M4** | 2024 | **16 GB** | 24 GB | 36 GB | — |
| **M5** | 2025 | **16 GB** | — | — | — |
| **M6** | 2026 | **16 GB** | — | — | — |

**M4 is the inflection.** Apple raised the Mac floor from 8 GB to 16 GB with the
M4 generation — the 8 GB and 12 GB M4 configurations exist only on iPad. Every
Mac from M4 onward ships with at least 16 GB.

*Confidence: M1–M4 are settled. M5 and M6 base configurations were checked
against Apple's newsroom and tech-specs pages in September 2026 — the M6 Mac mini
starts at $899 with 16 GB, and both M5 and M6 top out at 32 GB on the base chip.
The Pro/Max/Ultra minimums for M5 and M6 are left blank rather than guessed;
their maximums are 64 GB, 128 GB and 512 GB respectively.*

## What each memory size can hold

Weights plus KV cache at a 16k context, from the measured rates:

| model | weights | KiB/token | at 16k | measured? |
|---|---|---|---|---|
| **AFM** | system process | — | **+1.8 GiB** | **yes** — B0, `fm serve` |
| 4B 4-bit | 2.5 GiB | ~72 | **3.6 GiB** | weights only; KV scaled |
| **Qwen3-8B 4-bit** | 4.8 GiB | **144** | **7.0 GiB** | **yes, both** — B0, `mlx_lm` |
| 14B 4-bit | 9.3 GiB | ~185 | **12.2 GiB** | KV back-computed from Ollama |
| **Mistral-24B 4-bit** | 13.0 GiB | **160** | **15.5 GiB** | **yes, both** — B0, `mlx_lm` |

## The recommendation

| Mac | model | debate | judge | note |
|---|---|---|---|---|
| **8 GB** — M1/M2/M3 base | **AFM** | ✅ | ❌ | AFM's ~4,096-token session cannot hold a transcript. A 4B judge fits at 3.6 GiB but is **unvalidated**. |
| **16 GB** — M4/M5/M6 base, M1/M2 Pro | **Qwen3-8B** | ✅ | ✅ | 7.0 GiB leaves ~3 GiB of headroom. The full pipeline, one model, both roles. |
| **18–24 GB** — M3 Pro, M4 Pro | **Qwen3-8B**, or 14B on a quiet machine | ✅ | ✅ | 14B at 12.2 GiB fits the arithmetic; it has not been measured on MLX. |
| **32 GB+** — Max, Ultra | 14B comfortably; **24B unproven** | ✅ | ⚠️ | See the warning below. |

### Where arithmetic and measurement disagree, believe the measurement

Naive sizing says a 24B model at 15.5 GiB fits in 24 GB. **B0 measured that it
does not, on a 32 GB machine**, because the real baseline was **14.8 GiB** — a
browser at ~5 GiB, an IDE, a chat app, the window server. 14.8 + 15.5 = 30.3 GiB
against 32 installed, with nothing left for a second model or for growth.

So the honest rule is **installed − 15 GiB** for a machine in ordinary use, not
installed − 6. On that basis:

| installed | usable in real use | largest model |
|---|---|---|
| 8 GB | ~0 | AFM only |
| 16 GB | ~4 GiB | 4B, or AFM |
| 24 GB | ~9 GiB | **8B** |
| 32 GB | ~17 GiB | 14B |
| 48 GB+ | ~33 GiB | 24B — **and it has never produced a token here** |

**Both tables are true and they answer different questions.** The first is "what
fits if the app is what the machine is doing"; the second is "what fits while
someone works". A shipping app should size for the second and let the user opt
into the first.

## What this means for the product

1. **From M4 onward, every Mac can judge.** That is the single most useful line
   here: the 16 GB floor and the 7.0 GiB judge line up, so the whole pipeline
   runs on the base configuration of every current Mac.
2. **Before M4, base Macs debate but cannot judge locally.** M1, M2 and M3 base
   machines are a large installed base and they are stuck at AFM, whose session
   ceiling is a hard limit rather than a quality one.
3. **No configuration at any price has been shown to run a 24B model here.**
   Buying more memory does not currently buy a better judge — it buys headroom.
   The best judge measured is 8B-class, and the only one with validated ordering
   is `qwen3:8b`.

**Sources for the M5/M6 rows:** [Apple Newsroom — M6 and M5 Ultra](https://www.apple.com/newsroom/2026/08/apple-introduces-m6-and-m5-ultra-for-a-big-leap-in-performance-and-ai-compute/),
[MacBook Air (13-inch, M5) Tech Specs](https://support.apple.com/en-us/126320),
[Apple M5 — Wikipedia](https://en.wikipedia.org/wiki/Apple_M5),
[Apple M6 — Wikipedia](https://en.wikipedia.org/wiki/Apple_M6),
[Apple M4 — Wikipedia](https://en.wikipedia.org/wiki/Apple_M4).
