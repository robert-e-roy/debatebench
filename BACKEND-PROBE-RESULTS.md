# Backend Probe — Results (session 1, **partial**)

**Status:** partial. Part A is complete for Ollama, complete-bar-four-rows for
`mlx_lm.server`, and A1–A7 only for `vllm-mlx`. Part B has two rows. The exit
gate in `BACKEND-PROBE.md` ("every row in A and B filled in for all three
servers") is **not met**, and this file says which rows are missing and why.
**No recommendation is made here** — the data doesn't yet support one.

**Not** written to `RESULTS.md`: that file is B0's and would have been
destroyed.

**Date:** 2026-09-13. **Machine:** Mac14,12 (M2 Pro), 32 GiB unified memory,
macOS 27.0. At baseline: load ~2.2, 91% memory free, Claude Code + Terminal +
a chat app running. B0's own caveat applies — a busier or quieter machine
gives different numbers.

---

## Part Zero — what was tested

| | Identity | Version | Licence |
|---|---|---|---|
| `vllm-mlx` | **`github.com/vllm-mlx/vllm-mlx`** | 0.4.1 (wheel) | Apache-2.0 |
| `mlx_lm.server` | `github.com/ml-explore/mlx-lm` | mlx-lm 0.31.3, mlx 0.32.2 | MIT |
| Ollama | Ollama.app | 0.34.0 | **not verified locally** |

**Finding for ADR-003's amendment:** the installed `vllm-mlx` is a **fourth**
project, not one of the three that amendment lists (`vllm-project/vllm-metal`,
`waybarrios/vllm-mlx`, `vllm-swift`). It is its own org, `vllm-mlx/vllm-mlx`,
Apache-2.0. Anyone reproducing this must pin that, not "vllm-mlx".

Ollama's licence row is honest about its limits: the only licence file found
in the bundle was `MLX_C_LICENSE` (MIT), which covers a **bundled dependency**,
not Ollama itself. Not checked further.

Models: `mlx-community/Qwen3-8B-4bit` on both Python servers. **Ollama could
not serve it** — it has only `phi4-mini` and `ornith-coder` locally, and
pulling would need network, which contradicts the offline posture A11 tests.
Ollama's rows therefore ran on **`phi4-mini`** and are *not* like-for-like.

---

## Part A — API compatibility

All three columns are **Qwen3-8B 4-bit**: `mlx-community/Qwen3-8B-4bit` on both
Python servers, `qwen3:8b` on Ollama (Q4_K_M GGUF — same family and bit-width
class, not byte-identical weights). Ollama's earlier `phi4-mini` pass is kept in
`probe/backend/probe-a-ollama.json`; it is not comparable and is not used here.

| # | `vllm-mlx` | `mlx_lm.server` | Ollama |
|---|---|---|---|
| A1 `max_tokens` | **honoured** — exactly 20 | **honoured** — exactly 20 | **honoured** — 20, `length` |
| A1 `max_completion_tokens` | **ignored** — 305 tokens | **honoured** — exactly 20 | **ignored** — 1287 tokens, `stop` |
| A2 `json_object` | honoured, parses | **honoured**, parses | honoured, parses |
| A3 `json_schema` | **honoured, conforms** | **NOT honoured** — returned prose, "Two plus two is **4**." | **honoured, conforms** |
| A4 `stream: false` | one JSON object | one JSON object | one JSON object |
| A5 seed 42 + temp 0, twice | **identical** | **identical** | **identical** |
| A6 usage | present, non-zero | present, non-zero (+`prompt_tokens_details`) | present, non-zero (+`prompt_tokens_details`) |
| A7 tiny budget, `finish_reason` | `stop` at **713** tokens (cap ignored, truncation unsignalled) | **`length`** at exactly 10 | **`length`** at exactly 10 |
| A8 over-context | **no rejection**; still generating at 260 s, engine wedged, abandoned (~160k-token prompt) | **no rejection**; ballooned to **23 GB**, client timeout at 180 s (~160k-token prompt) | **no rejection**; client timeout at 180 s (~37k-token prompt) |
| A9 reasoning field | **no separate field** — `<think>` inside `content`, despite `--reasoning-parser qwen3` | **separate `reasoning` field**, alongside `content` | **separate `reasoning` field**, alongside `content` |
| A10 bind address | `127.0.0.1` | `127.0.0.1` | **`*:11434` — wildcard, reachable off-box** |
| A11 offline start | *not verified to standard* | *not verified to standard* | not applicable (already running) |

**A3 is the row ADR-013's open question needed, and it divides 2–1 against the
current default.** `vllm-mlx` and Ollama both honour `json_schema` and return
conforming JSON; `mlx_lm.server` — which ADR-003 makes the default — ignores it
and answers in prose. Structured output would retire the malformed-JSON failures
that cost most of 2026-09-12/13 rather than validating around them.

### Why the gaps

- **mlx_lm A2/A3/A5: re-run and now measured** — see the table. The first pass
  failed for two compounding reasons, and only one was a parsing bug. The probe
  fell back to printing the response envelope when extraction failed (fixed),
  but the *reason* extraction found nothing was **budget starvation**: at 60–120
  tokens, Qwen3 through `mlx_lm` spent the whole budget thinking and returned a
  message with a `reasoning` key and no `content` at all. That is
  OPEN-QUESTIONS 13, and it is the same trap the judge hit before its budget
  went to 6000. The rows were re-run at 2000 tokens
  (`probe-a-mlx_lm-budgeted.json`). Calling it "an instrument failure" was half
  right and is corrected here.
- **vllm-mlx A9:** blocked during the first pass — A8's prompt wedged the
  generation route, two attempts returned HTTP 503 `text_generation_busy`, and
  ~20 minutes later it still had not cleared. **Measured after the server was
  restarted**, and the answer is in the table above.
- **mlx_lm A9:** the first run died at A8 and never reached it. **Measured on
  the re-run**, and the answer is in the table above.
- **A11 everywhere:** both Python servers were started with offline flags
  (`HF_HUB_OFFLINE=1`, `--offline`) and started without network errors, but the
  doc requires a packet capture or firewall block. Absence of an error is not
  the evidence asked for, so this is recorded as unverified.

### Method corrections made during the run

- **A1's first Ollama reading was wrong and was redone.** "Name three colours"
  answers in 6–7 tokens, so a 20-token cap never bound and both fields looked
  honoured. Re-run with a 400-word essay prompt, which is what produced the
  table above. The vllm-mlx A1 reading was decisive on the original prompt
  (20 vs 305) and was not affected.
- **`ps -o rss` is the wrong instrument** on Apple Silicon and its readings
  (8 MB for a process holding an 8B model) were discarded. B0 used macOS
  `footprint -p <pid>`, and that is what Part B below uses.

---

## Part B — performance

| # | Measured | Result |
|---|---|---|
| B2 | `vllm-mlx`, Qwen3-8B-4bit, **at rest after a clean start** | **5.0 GB** `phys_footprint` |
| B2 | `vllm-mlx`, same model, **while wedged on a ~160k-token prompt** | 12 GB (see correction below) |
| B2 | `mlx_lm`, same model, during a ~160k-token prompt | **23 GB**, peak 23 GB |
| B6 | `vllm-mlx` concurrency | **serialized** — rejects with `SimpleEngine serialized route is busy … blocking_serialized … waiters=0` |
| B1, B3, B4, B5 | — | **not measured** |

Two observations that bear on the rows above:

- **Correction (same session).** An earlier version of this file said
  "vllm-mlx's 12 GB is roughly double B0's figure for the same model," and that
  was wrong. The 12 GB was measured while the server was wedged holding the KV
  cache for a ~160k-token prompt — my own A8 row — not at rest. Measured again
  after a clean restart, it is **5.0 GB**, against B0's 4.8 GiB after load for
  the same weights on the same machine: **the same, not double.** The claim was
  also asserted in a commit message, which this corrects. It is a good example
  of why a footprint reading has to record what the server was *doing* when it
  was taken.
- **mlx_lm's 23 GB is consistent with B0's KV-cache measurement** of
  144 KiB/token for Qwen3-8B: a ~160k-token prompt is ~23 GB of cache. It does
  not refuse an over-context prompt; it tries to allocate for it.
- **B6 is answered for `vllm-mlx` by its own error text**, not by a timing
  test: the route is explicitly serialized. The vLLM name does not imply
  vLLM's concurrency here. Not yet tested on the other two.

**Part B's timings (B1/B3/B4) must be taken on a recovered machine.** Free
memory was 12–13% at the end of this session with `vllm-mlx` still holding
12 GB, so any latency number taken now would measure swap, not the server.

---

## Operational findings (not rows, but they bind the tool)

1. **A client timeout does not cancel server-side generation.** Confirmed on
   both `vllm-mlx` and `mlx_lm`. On `vllm-mlx` one oversized prompt made the
   server unusable for ~20 minutes — every later request, including a trivial
   one, got 503. On `mlx_lm` the 23 GB was still held after both the client and
   the driving process had exited; only killing the server released it.
   For `debatebench` this means a single bad `budget`/prompt can take a backend
   out of service for the rest of a run.
2. **No single budget field works everywhere**, now confirmed on identical
   weights rather than inferred across different ones. `max_tokens` is honoured
   by all three servers here and ignored by AFM (ADR-003).
   `max_completion_tokens` — **which is what the adapter currently sends**
   (ADR-003, ADR-009) — is honoured by `mlx_lm` and AFM and **ignored by
   `vllm-mlx` and Ollama**: against a cap of 20 they returned 305 and 1287
   completion tokens respectively, both with `finish_reason: "stop"`. On those
   two the orchestrator's budget never reaches the server at all; Hard Rule 5
   catches the overshoot after the fact, which is how the 646-token overshoot
   on 2026-09-12 was caught.
3. **`json_schema` is honoured by both servers that could be tested.** This is
   the row ADR-013's open question needed. Structured output would remove the
   malformed-JSON failures that cost most of this session, rather than
   validating around them.
4. **Ollama binds a wildcard address by default.** `*:11434`, reachable from
   the network, where both Python servers bind loopback.
5. **`vllm-mlx` leaves thinking inside `content`, even with
   `--reasoning-parser qwen3`.** The reply carries only a `content` key — no
   `reasoning` or `reasoning_content` — and it opens with `<think>`.
   `mlx_lm.server` separates it into its own field (OPEN-QUESTIONS 13). Two
   consequences: a reasoning model's thinking is charged to the same budget
   *and* returned inline, and any JSON extraction that scans from the first
   `{` to the last `}` can be misled by a brace inside a thinking block. That
   is a risk this probe surfaces, not a diagnosis of any particular failure.

---

## What would finish this

- **Part A is complete for all three servers on the same model**, except A8 on
  `vllm-mlx` (abandoned after it wedged the engine; worth one more attempt with
  the instrument's corrected ~37k-token prompt) and A11 everywhere, which needs
  a packet capture rather than the absence of an error.
- **Part B is the real gap**: B1, B3, B4 and B5 are unmeasured. The machine is
  now quiet again (~90% free), so these are finally worth taking — one server
  at a time, since two resident 8B models is what produced the Metal OOM.
- B5 (`Qwen3-8B` + `Mistral-Small-24B` co-resident) should still go **last**.
- B5 (`Qwen3-8B` + `Mistral-Small-24B` co-resident) was not attempted. On this
  evidence it should be attempted last and deliberately: two 8B-class models
  plus a large prompt already drove free memory from 91% to 6% in this session.
