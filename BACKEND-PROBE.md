# Backend Comparison Probe — `mlx_lm.server` vs `vllm-mlx` vs Ollama

**Status:** probe, not a decision. Gathers data; doesn't choose a default.
**Depends on:** ADR-003 (fm serve's own probe, same discipline: measure, don't
infer from "OpenAI-compatible" branding), ADR-013's open question (does any
candidate honor `response_format`/`json_schema`), the "seems to work better"
report this probe exists to actually verify.

## Zero: name the thing you're testing

**Before anything else, pin exactly which project "vllm-mlx" refers to.**
Three unrelated codebases share the name (ADR-003's amendment):
`vllm-project/vllm-metal` (real upstream vLLM + an Apple Silicon plugin),
`waybarrios/vllm-mlx` (an independent, from-scratch reimplementation, not a
vLLM fork), `vllm-swift` (a third, separate Swift/Metal reimplementation).
Record the exact repo, and the exact commit or release tag installed. A
result reported as "vllm-mlx" without this is not reproducible and doesn't
belong in the results table.

Record the same for the other two: `mlx_lm.server`'s version (from `pip show
mlx-lm`), and Ollama's version (`ollama --version`).

## Part A — API compatibility (does it do what it claims to)

Same model (`mlx-community/Qwen3-8B-4bit`, or the closest equivalent each
server can actually load), same machine, same session, run against all
three:

| # | Test | What to record |
|---|---|---|
| A1 | Send `max_tokens: 20` and separately `max_completion_tokens: 20` | Which one is honored? (`fm serve` ignores `max_tokens` entirely — ADR-003 — confirm this isn't universal) |
| A2 | Send `response_format: {"type": "json_object"}` with a prompt asking for JSON | Honored, ignored, or HTTP error? |
| A3 | Send `response_format: {"type": "json_schema", "json_schema": {...}}` with a real schema | Honored, ignored, or HTTP error? (This is the one ADR-013's open question actually needs answered.) |
| A4 | Send `"stream": false` explicitly | Response arrives as one JSON object, not SSE chunks? |
| A5 | Send `seed: 42, temperature: 0` twice | Identical output both times? |
| A6 | Non-streaming response | `usage.prompt_tokens` and `usage.completion_tokens` present and non-zero? |
| A7 | Deliberately tiny budget (e.g. 10 tokens) against a prompt that needs more | `finish_reason` value — `"stop"` (like `fm serve`, which doesn't distinguish truncation) or `"length"` (a real, honest signal)? |
| A8 | Prompt that exceeds the model's context window | HTTP status and error shape — same as `fm serve`'s HTTP 500 `server_error`, or something more specific? |
| A9 | A reasoning model (Qwen3 family) at a small budget | Does thinking leak into `content`, or arrive separately (as `mlx_lm.server` does via a `reasoning` field — OPEN-QUESTIONS item 13)? |
| A10 | Start with minimal/default flags, no explicit host | Binds to `127.0.0.1` or `0.0.0.0`? (Security-relevant per ADR-003's amendment.) |
| A11 | Start with `HF_HUB_OFFLINE=1` set | Zero network calls at startup — confirm via a packet capture or a firewall block, not just absence of an error. |

## Part B — Performance (numbers, not impression)

Same model, same machine, same session as Part A, **document what else is
running** (Safari, Xcode, etc. — B0's own finding was that this changes the
result as much as the tool does).

| # | Test | What to record |
|---|---|---|
| B1 | Cold start to first successful response | Load time |
| B2 | Single model resident, idle | Peak memory (process footprint, same measurement B0 used) |
| B3 | Single request, short prompt | Decode tok/s |
| B4 | Single request, ~4,000-token prompt | Time to first token, prefill tok/s (bears directly on ADR-002's still-open prefill-engine question) |
| B5 | Attempt to load `Qwen3-8B` + `Mistral-Small-24B` together | Peak memory, and whether it hits critical pressure/swap the way B0 measured for `mlx_lm.server` — this directly re-tests B0's headline finding under each backend |
| B6 | Two simultaneous requests to one already-loaded model | Total wall time ≈ 1× a single request (real concurrency) or ≈ 2× (serialized)? Only vLLM-flavored servers claim to do better than serialize here — confirm rather than assume the claim holds on Apple Silicon specifically |

## Part C — Provenance and operational cost

- Exact license of whichever `vllm-mlx` variant was tested (unlike
  `mlx_lm.server`'s and Ollama's, this hasn't been checked at all yet, per
  ADR-003's amendment — required before it could become a documented choice)
- Any setup step beyond "already running," e.g. a required virtual
  environment, a config file, a model-conversion step — these are real
  friction for anyone following the eventual setup docs, not just for this
  probe

## Deliverable

A `RESULTS.md`, same shape as B0's: real numbers in a table, not
"seemed faster" or "worked" — plus an explicit recommendation, or an
explicit "insufficient signal, here's what would resolve it" if the numbers
don't clearly favor one option. If a server can't be gotten to run some
test at all, that's a real finding, "could not test A9 because X," not a
silently skipped row.

## Exit gate

Every row in A and B filled in for all three servers, in the same session,
on the same machine state, with Part Zero's naming pinned precisely enough
that someone else could reproduce the exact setup. A recommendation that
changes ADR-003's current default (`mlx_lm.server`) needs its own ADR
amendment citing this file, not a silent switch.
