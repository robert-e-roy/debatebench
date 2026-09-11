# B0 Results — Hardware Reality Check

**Date:** 2026-09-11
**Machine:** Apple M2 Pro, 32 GiB unified memory, macOS 27. This is the dev
machine, and it's also the host ADR-002 names as the offload target (see "The
offload host is this machine" below).
**Stack:** `mlx_lm.server` 0.31.3 (mlx 0.32.0), Python 3.14; `fm serve` for AFM
**Status:** exit gate answered **for the machine as it's actually used**. The run
was stopped by its own safety cut-off while loading Mistral-Small-24B. A
quiet-machine run (heavy apps closed) hasn't been done.

## Answer

**As this Mac is actually used, it can't run the intended pairing.**
Mistral-Small-24B on its own, with no other model of ours loaded, drove the
machine to critical memory pressure and into swap within about 8 seconds of
starting to load. Three co-resident models are ruled out. What does run:
Qwen3-8B (6.6 GiB, 34 tok/s) and AFM.

**No concurrency was measured.** The pair and three-model stages were never
reached. Per the exit gate, later sessions must not assume the pair can be
co-resident.

### Recommendation, ranked

1. **Take the judge out of the co-residency problem.** This follows from ADR-002's
   design; it isn't a probe result. ADR-002 has the judge run once, over the
   finished transcript. So it can load after the debaters unload instead of
   alongside them. Its load cost — tens of seconds, see "Load and swap costs" — is
   paid once per run. The three-model scenario only exists if the judge must be
   resident during the debate, and it doesn't have to be.
2. **The per-turn fact-checker has no offload target yet.** It's the only role
   that has to run during the debate. ADR-002's option was to put it on its
   named offload host, but that host is this machine, so it isn't an offload.
   What's left:
   - AFM for small per-claim checks. It ran at 38.6 tok/s and is capped at about
     4,096 tokens per request (ADR-003). Its model runs in a system process;
     system memory peaked about 1.8 GiB above baseline during that stage.
   - A genuinely separate host, if one exists. None has been identified.
3. **Debaters: co-residing the pair is unproven and doubtful.** The pair needs
   about 19.6 GiB of model memory (below). That's plausible only with heavy apps
   closed, and it's unmeasured. The fallback is to benchmark smaller pairs
   locally (two 8B models ≈ 13 GiB).
4. **Load/unload per turn looks expensive at long contexts, but this is inferred,
   not measured.** Loading the weights themselves is fast (below). But a model
   swap would likely lose the prompt cache and force the whole transcript to be
   re-processed. A cold 4,000-token prompt took about 25 s on the 8B model. A
   full swap cycle wasn't measured, so later sessions shouldn't treat this as
   settled.

## Measurements

| Model | Memory (process footprint) | Decode | First token | Load |
|---|---|---|---|---|
| AFM via `fm serve` | model runs in a system process (system memory peaked +1.8 GiB during this stage); `fm serve` itself 0.01 GiB | 38.6 tok/s (end-to-end, non-streaming) | — | server ready in 0.04 s |
| Qwen3-8B 4-bit | 4.8 GiB after load; 6.6 GiB peak after a 4k-token prompt | **33.9 tok/s** | 0.4 s (short prompt) | 37.6 s until the port opened; 39.2 s to the first response |
| Mistral-Small-24B 4-bit | 13.0 GiB when stopped | not reached | — | weights went from 0.3 to 13.0 GiB in ~5 s, then aborted |

- **Long prompt:** Qwen3-8B took 24.9 s to the first token for a 4,025-token
  prompt, about **162 prompt tok/s**. A debate turn that carries a few thousand
  tokens of transcript spends tens of seconds processing it before generating
  anything. A 24B model would be slower; that's an estimate, not measured. This
  makes per-side prompt caching (keep each side's prefix warm between turns)
  essential rather than an optimization. It also bears on ADR-002's question
  about prefill-heavy prep.
- **Turn settings:** 256-token turns at temperature 0, 3 turns per measurement.
  Token counts come from the server's streamed `usage`, which matched
  non-streaming counts exactly (64 = 64).
- **AFM overshoot:** it produced 262 tokens against a 256 cap, consistent with
  ADR-003.

## What happened when Mistral loaded

Sampled every 0.5 s (full trace in `probe/b0/b0_raw.json`):

| | Used | Free | Compressed | Swap | Pressure |
|---|---|---|---|---|---|
| Before loading (Qwen stopped) | 15.1 GiB | 7.4 GiB | 7.0 GiB | 0 | normal |
| Peak, ~8 s later | 24.6 GiB | 0.0 GiB | 18.4 GiB | 1.8 GiB | **critical** |
| Right after the abort | 10.8 GiB | 14.2 GiB | 5.9 GiB | 1.9 GiB (stays allocated) | normal |

Free memory hit zero while Mistral's footprint climbed to 13.0 GiB. macOS
compressed other apps' memory hard, then began swapping (~124k pages). The swap
cut-off (+1 GiB) and critical pressure fired in the same sample, so this wasn't a
conservative threshold firing early. The machine was genuinely at critical. The
server was killed and memory recovered within a second.

## Why the pair doesn't fit

- **The GPU limit isn't what binds.** The pair's footprint is about 6.6 + 13.0 =
  19.6 GiB, below Metal's recommended GPU working set on this machine (24.96 GiB).
- **Total RAM is what binds.** At baseline the machine used 14.8 GiB (7.4 GiB of
  it compressed). Most of that was ordinary desktop use: a web browser (about
  5 GiB across its processes), an IDE, a chat app and the window server.
  14.8 + 19.6 = 34.4 GiB, more than the 32 GiB installed.
- **A quiet machine might fit, just barely.** With a baseline around 8 GiB, the
  pair comes to about 27.6 GiB, leaving about 4 GiB for context. Transcript
  memory grows with context: 144 KiB/token for Qwen3-8B and 160 KiB/token for
  Mistral-24B, about 1.1 and 1.25 GiB each at 8k tokens. Unmeasured.
- **Adding a judge rules co-residence out** at either size:
  - an 8B judge brings model memory to about 26.2 GiB, above the recommended GPU
    working set and, with any normal baseline, above physical RAM;
  - a 24B judge brings it to about 32.6 GiB.

## Load and swap costs

- **Weights load quickly.** Qwen3-8B's weights were in memory about 4 s after
  launch. Mistral's went from 0.3 to 13.0 GiB in about 5 s.
- **Most of Qwen's 38 s cold start came after the weights were loaded.** The log
  shows a Hugging Face revision check at +3 s, then the server listening at
  +38 s. The cause of that gap wasn't identified. Swapping models inside one
  long-running server might avoid it; unmeasured.
- **Every `mlx_lm.server` start contacts huggingface.co** to check the model
  revision (visible in the log). For a privacy-first, offline-capable tool, that's
  not acceptable. `HF_HUB_OFFLINE=1` is now a requirement (ADR-002, "Backend
  abstraction"), and cached models resolve fine with it.

## Caveats

- **These numbers are for the machine as actually used**, with a web browser, an
  IDE and a chat app open. A quiet machine would give different memory results. That
  difference is part of the finding, not a hedge.
- **"Same-tier" was ambiguous** for the third model, because the pairing spans
  8B and 24B. The probe planned an 8B-tier stand-in, a second, independent
  Qwen3-8B process, but never reached that stage. The 24B-tier case is ruled out
  by the arithmetic above.
- **Which Mistral:** `mlx-community/Mistral-Small-24B-Instruct-2501-4bit`, chosen
  because it's text-only and loads in `mlx_lm`. Other 24B 4-bit variants are
  equivalent for memory and bandwidth (the 3.2 build's weights are the same
  13.3 GB).
- **The offload host is this machine.** The host ADR-002 names as the offload
  target is this Mac's own local hostname, so it resolves to the loopback
  address. The Ollama instance answering there is local, with nothing loaded
  during the run.

  ADR-002's "offload the judge/fact-checker" option therefore offloads to the
  same 32 GiB machine that hit critical pressure. It only works if there's a
  different host.

  Two earlier reachability checks during B0 got this wrong. The first reported
  the host as unreachable. The second reported it as a live remote host.
- **Stages not reached:**
  - Mistral throughput alone;
  - the pair, one at a time and concurrently;
  - AFM under load;
  - the three-model case.

## What a follow-up run would add

- **The same probe with heavy apps closed**, keeping the same cut-offs. That
  answers whether the pair is viable on a quiet machine, and gives Mistral's
  throughput and the pair's concurrent throughput.
- **A genuinely separate inference host, if one exists,** plus a short throughput
  and round-trip test on it. That makes recommendation 2 concrete.
- **A measured model-swap cycle** — unload, load, re-process the context — to
  confirm or overturn recommendation 4.

## Files

- `probe/b0/b0_probe.py` — the throwaway probe. It samples memory every 0.5 s,
  with cut-offs at +1 GiB swap, less than 15 GiB free disk, or critical pressure.
- `probe/b0/summarize.py` — prints the tables above from the raw data.
- `probe/b0/b0_raw.json`, `run.log`, `logs/` — the raw samples, per-stage
  results and server logs.
