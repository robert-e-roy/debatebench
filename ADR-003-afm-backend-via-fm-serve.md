# ADR-003: AFM Dev Backend via `fm serve`

**Status:** Accepted (2026-09-11)
**Date:** 2026-09-11
**Depends on:** ADR-001 (single `openai-compatible` adapter), ADR-002 (AFM as dev default)

## Decision

Reach Apple Foundation Models (AFM), the dev-default model in ADR-002, through
`fm serve`: the Chat Completions server built into macOS 27's `fm` CLI
(`/usr/bin/fm`). It uses **the same `openai-compatible` adapter** that serves
`mlx_lm.server`, Ollama and LM Studio. There is no AFM-specific backend class; AFM
is one more `base_url` (`http://127.0.0.1:<port>/v1`, model `system`).

The probe below shows `fm serve` departs from OpenAI's behavior in ways that bear
directly on the hard rules. So the adapter must:

1. Always send `"stream": false` explicitly. `fm serve` streams when `stream` is
   omitted; OpenAI doesn't.
2. Send the per-phase budget as **`max_completion_tokens`**, never `max_tokens`,
   which `fm serve` ignores.
3. Treat the backend's cap as advisory. After every turn the orchestrator checks
   `usage.completion_tokens` against the phase budget itself (Hard Rule 5).
   `finish_reason` is not a usable truncation signal here.
4. Treat any non-2xx response as a failed turn (Hard Rule 1). That includes
   context overflow, which arrives as HTTP 500, not a 4xx.

## Why

- ADR-002 names AFM as the dev default but never says how a Python process reaches
  a Swift framework. `fm serve` answers that with no custom bridge.
- It keeps ADR-001's "one adapter, configurable `base_url`" intact. B1's "one
  backend, AFM" and B3's "wire in the openai-compatible adapter" become the same
  piece of work.
- The probe shows exactly where the "OpenAI-compatible" label can't be trusted.
  A budget passed as `max_tokens` would silently not hold — the same failure
  ADR-001 found in aragora's `vote()`.

## Probe results

Measured 2026-09-11 on the dev Mac (macOS 27, Xcode 27.0), `fm serve --port 19760`,
model `system`:

| Behavior | Observed |
|---|---|
| `stream` omitted | Response streamed as SSE chunks |
| `max_tokens: 12` | **Ignored** — 481 completion tokens, `finish_reason: "stop"` |
| `max_completion_tokens: 12` / `20` | Honored with a small overshoot — 14 / 21 completion tokens, `finish_reason: "stop"` |
| `usage` (non-streaming) | Present: `prompt_tokens`, `completion_tokens`, `total_tokens` |
| `temperature: 0`, run twice | Identical output |
| `temperature: 0.9`, no seed, run twice | Different output |
| `temperature: 0.9, seed: 42`, run twice | Identical; `seed: 7` differs |
| 3,843 total tokens in context | OK |
| ~4,359 prompt tokens | HTTP 500, `type: "server_error"`, message "The session's transcript exceeded the model's context size." |
| `fm count-tokens` vs server `prompt_tokens` | 3,767 vs 3,822 — the server adds ~55 tokens of template overhead |
| Opening statements for and against a federal carbon tax | Both answered normally. A two-sample spot check, not evidence the guardrails won't refuse other debate content |

The context ceiling is consistent with the 4,096 tokens per session stated in Xcode
27's bundled Foundation Models guide.

## Consequences

- **AFM is a plumbing model only.** At ~4,096 tokens per session (instructions,
  prompt and output combined), a full six-phase debate with ADR-002's example
  `budget: 2000` cannot run on it. The limit is a measured fact, not a
  decision, so BUILD-GUIDE was updated on 2026-09-11 to match: B2's AFM dummy
  debate now requires budgets small enough to fit, and B7 no longer uses AFM as
  the judge.
- **B3's reproducibility gate is achievable on AFM.** Both `seed` and
  `temperature: 0` gave identical output across runs (same machine, same OS build).
- **"Did the model finish or hit its cap" can't be read from `finish_reason`.** A
  capped reply still says `"stop"`, so only the orchestrator comparing
  `usage.completion_tokens` to the budget can tell. This feeds the still-open
  question of what counts as a valid response.
- **Errors are distinguishable only by message string.** Context overflow and
  genuine server faults share HTTP 500 / `server_error`. Both abort the run either
  way; the message only changes what gets reported on stderr.
- **Pre-flight token checks need headroom.** `fm count-tokens` undercounts what the
  server bills by ~55 tokens.
- **Per-side endpoints are settled by ADR-007.** With several servers in play
  (`fm serve`, `mlx_lm.server`, Ollama), each team in `run.yaml` carries a
  `base_url`, and `judge` takes an optional `--base-url`.
- **Dev platform floor:** macOS 27 on Apple-Intelligence-capable hardware. The tool
  itself stays general-purpose; only the dev default needs this.
- **AFM doesn't reliably argue the side it's assigned.** Observed during B1
  (2026-09-11), one sample per case at temperature 0. The system prompt said "you
  argue FOR [or AGAINST] the motion, whatever your own view".
  - "We should ban AI.": it argued against in all four persona/side combinations,
    including both where it was told to argue for.
  - "Cities should ban cars from their centers.": it complied three times out of
    four, failing when the conservative persona was told to argue for.

  That's a signal, not a measurement. AFM is still fine for plumbing, but a dummy
  debate on it may show two sides that agree. Holding an assigned side is worth
  measuring for real candidate models (ADR-002's stance-consistency check).
- **AFM runs one request at a time.** Measured 2026-09-11, over three trials of two
  replies of about 165 tokens each:
  - one after the other took about 8 s in total;
  - sent at the same time, to one `fm serve` or to two on different ports, they
    also took about 8 s. One reply finished at about 4 s and the other waited
    until about 8 s.

  Every `fm serve` reaches the same system model, so extra servers add no
  throughput. Running both sides at once on AFM gains nothing, and an AFM
  fact-checker would queue behind AFM debaters. Whether AFM runs in parallel with
  an MLX model is unmeasured.
- **Manual setup:** `fm serve` must already be running, like `mlx_lm.server`.
  B7's gate now allows for that. Having the tool start and stop servers itself
  would need a new ADR.

## Open questions (not settled by acceptance)

1. **Budget overshoot policy — resolved by ADR-010:** a cap with a stated
   tolerance. A turn fails if it exceeds its budget by more than 16 tokens.
2. **HTTP client — resolved by ADR-008:** `httpx`, with explicit timeouts.
3. **Transport.** TCP on `127.0.0.1`, the same shape as every other provider, or
   `fm serve --socket`, which its help text recommends for local Python bindings
   but which no other provider uses.
4. **Guardrail refusals.** Partly observed during B1 (2026-09-11). A prompt of
   "word " repeated 6,000 times got HTTP 500 with the message "The model's safety
   guardrails were triggered.", before any context-size check. So a guardrail
   refusal of the input arrives the same way as context overflow and genuine
   server faults: status 500, `type: "server_error"`, distinguishable only by
   message. The adapter treats it as a failed turn (ADR-009). Still unobserved:
   how a refusal of the model's own output surfaces. Still open: whether a
   refusal should count as a response, which belongs to the same question as
   truncation.
