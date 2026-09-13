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

| # | `vllm-mlx` (Qwen3-8B) | `mlx_lm.server` (Qwen3-8B) | Ollama (phi4-mini) |
|---|---|---|---|
| A1 `max_tokens` | **honoured** — exactly 20 | **honoured** — exactly 20 | **honoured** — 20, `finish_reason: length` |
| A1 `max_completion_tokens` | **ignored** — 305 tokens | **honoured** — exactly 20 | **ignored** — 633 tokens, `stop` |
| A2 `json_object` | honoured, content parses | *not measured* | honoured, content parses |
| A3 `json_schema` | **honoured, conforms** | *not measured* | **honoured, conforms** |
| A4 `stream: false` | one JSON object | one JSON object | one JSON object |
| A5 seed 42 + temp 0, twice | **identical** | *not measured* | **identical** |
| A6 usage | present, non-zero | present, non-zero (+`prompt_tokens_details`) | present, non-zero (+`prompt_tokens_details`) |
| A7 tiny budget, `finish_reason` | `stop` at **713** tokens (cap ignored, truncation unsignalled) | **`length`** at exactly 10 | `stop` at **444** (cap ignored) |
| A8 over-context | **no rejection**; still generating at 260 s, engine wedged, abandoned | **no rejection**; ballooned to **23 GB**, client timeout at 180 s | client timeout at 180 s; post-disconnect behaviour not measured |
| A9 reasoning field | *not measured* | *not measured* | content only, no separate field — **not comparable** (phi4-mini isn't a reasoning model) |
| A10 bind address | `127.0.0.1` | `127.0.0.1` | **`*:11434` — wildcard, reachable off-box** |
| A11 offline start | *not verified to standard* | *not verified to standard* | not applicable (already running) |

### Why the gaps

- **mlx_lm A2/A3/A5:** instrument failure, not a server finding. The probe's
  content extraction returned nothing and fell back to printing the response
  envelope, so "does it honour `json_object`" was never actually tested. Must
  be re-run before anything is concluded.
- **vllm-mlx A9:** blocked. A8's prompt wedged the generation route; two
  attempts returned HTTP 503 `text_generation_busy`, and ~20 minutes later the
  route still had not cleared.
- **mlx_lm A9:** the run died at A8 and never reached it.
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
| B2 | `vllm-mlx`, Qwen3-8B-4bit resident | **12 GB** `phys_footprint` |
| B2 | `mlx_lm`, same model, during a ~160k-token prompt | **23 GB**, peak 23 GB |
| B6 | `vllm-mlx` concurrency | **serialized** — rejects with `SimpleEngine serialized route is busy … blocking_serialized … waiters=0` |
| B1, B3, B4, B5 | — | **not measured** |

Two observations that bear on the rows above:

- **vllm-mlx's 12 GB is roughly double B0's figure for the same model** under
  `mlx_lm` (4.8 GiB after load, 6.6 GiB peak). Same weights, same machine.
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
2. **No single budget field works everywhere.** `max_tokens` is honoured by all
   three servers here and ignored by AFM (ADR-003). `max_completion_tokens` —
   **which is what the adapter currently sends** (ADR-003, ADR-009) — is
   honoured by `mlx_lm` and AFM and **ignored by `vllm-mlx` and Ollama**. On
   those two the orchestrator's budget is not being applied server-side at all;
   Hard Rule 5 catches the overshoot after the fact, which is how the 646-token
   overshoot earlier today was caught.
3. **`json_schema` is honoured by both servers that could be tested.** This is
   the row ADR-013's open question needed. Structured output would remove the
   malformed-JSON failures that cost most of this session, rather than
   validating around them.
4. **Ollama binds a wildcard address by default.** `*:11434`, reachable from
   the network, where both Python servers bind loopback.

---

## What would finish this

- Restart `vllm-mlx` (its engine is still wedged), then run A8, A9 and Part B
  on it.
- Re-run mlx_lm's A2/A3/A5 with the content-extraction bug fixed.
- Decide whether Ollama is compared on `phi4-mini` (not like-for-like) or a
  Qwen3-8B is pulled, which needs network.
- B5 (`Qwen3-8B` + `Mistral-Small-24B` co-resident) was not attempted. On this
  evidence it should be attempted last and deliberately: two 8B-class models
  plus a large prompt already drove free memory from 91% to 6% in this session.
