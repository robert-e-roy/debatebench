# ADR-032: The Judge May Ask the Server to Constrain Its Reply to the Schema

**Status:** Accepted. §5 measured 2026-09-17; **the default flipped ON on
2026-09-18** after the backend probe named below came back clean.
**Date:** 2026-09-17
**Depends on:** ADR-009 (the backend request type), ADR-017 §3 (the hit-ledger
vocabulary), ADR-015 §2 (the four verdicts), ADR-018 (Ollama honours
`response_format`), ADR-026 (a malformed reply names its repair)
**Amends:** ADR-009's `GenerationRequest`, which gains one optional field
**Resolves:** OPEN-QUESTIONS 14's option 4 — the last one left open

## Context — five judges, five different ways to break one schema

Every judge tried against this project has violated the reply contract, and each
family broke a different part of it:

| judge | failure | rate |
|---|---|---|
| `qwen3:8b` | malformed JSON on the richer debates | 3 of 6 |
| `qwen3:4b`, `qwen3:14b` | identical malformed reply at two budgets | always |
| `phi4:14b` | doubled quotes inside a justification | 4 of 10 |
| `mistral-nemo:12b` | invents hit-ledger statuses — `partially rebutted` | 4 of 6 |
| `phi4-mini` | invents evidence ids — `am-255`, never recorded | 1 of 8 |
| `gemma4:12b` | all reasoning, no answer | always |

ADR-026 gave a malformed reply a useful error and declined to retry, and that
still stands. But it left OPEN-QUESTIONS 14's fourth option open with a
measurement shape pre-written: **constrain the reply**.

**Measured 2026-09-17, directly.** The same prompt to `phi4:14b` and
`mistral-nemo:12b-8k`, with and without a JSON schema on the request:

| model | unconstrained | with `json_schema` |
|---|---|---|
| `phi4:14b` | invalid — markdown fence, `"verdict": "Partially addressed"` | valid, enum respected |
| `mistral-nemo` | invalid — fence, `"status": "Closest match"` | valid, enum respected |

Ollama applies **constrained decoding**: at each step the probability of any
token that would violate the schema is set to zero, so a fence, stray prose or an
off-enum value is not merely discouraged but unemittable. Published failure rates
for local models on structured output are 5–15% without fine-tuning; this
project's schema is stricter than most and ran 12–67%.

## Decision

### 1. `GenerationRequest` gains an optional `response_schema`

```python
response_schema: dict | None = None
```

When set, the `openai-compatible` adapter sends it as OpenAI's
`response_format: {"type": "json_schema", "json_schema": {...}}`. When unset —
which is every debate turn — the request is byte-identical to what it is today.

This amends ADR-009's fixed request type. It is additive and defaulted, so every
existing construction is unaffected.

### 2. Only the judge uses it. A debate turn never does

A speech is prose. There is nothing to constrain and a schema would be an
instruction to stop arguing and start emitting JSON. `debate` is untouched by
this ADR in every respect.

### 3. The schema is built from the transcript, not written by hand

Two builders in `judging.py`, and the interesting part is that both close over
the *specific* transcript:

- **the score reply** — five named dimensions per side, integer scores, and
  `hit_ledger[].status` constrained to ADR-017 §3's four values;
- **the claims reply** — `verdict` constrained to ADR-015 §2's four values, and
  **`evidence_ids` constrained to an enum of the ids this transcript actually
  recorded**.

That last one is the one worth naming. `phi4-mini` invented `am-255`; under this
schema `am-255` is not a token the sampler may emit. A whole class of failure
stops being a validation error and becomes impossible.

### 4. It is opt-in, and off by default until measured

`judge --strict-json` turns it on; a `strict_json:` key in the `judge:` block
does the same. **Default off.**

Two reasons, and the second is the real one:

- **Not every backend honours it.** `BACKEND-PROBE-RESULTS` found Ollama honours
  `response_format` where `mlx_lm.server` does not. A server that *ignores* it is
  harmless; one that rejects it would turn a working judge into a failing one.
  Opt-in keeps AFM and `mlx_lm` users exactly where they are.
- **ADR-026 §3 pre-registered the measurement, and it has not been run.**
  Constrained decoding can change *what a model writes*, not merely whether it
  parses. A ledger that parses but says less is not an improvement, and this
  project has already reverted three changes that looked like wins on one metric.

### 5. The measurement that decides the default

Exactly the shape ADR-026 §3 specified, run on the same transcripts both ways:

1. **the parse-failure rate** — how many judge calls fail, by model;
2. **the ledgers themselves** — claim counts and the verdict distribution.

A drop in failures with materially thinner ledgers is a regression, not a fix,
and the flag stays off by default. The artifacts are committed before the verdict
is written into this ADR.

### 6. `_validate_claim` keeps every check it has

The schema constrains the *sampler*; the parser still verifies. Belt and braces
on purpose: a backend that silently ignores `response_format` must not thereby
skip validation, and the two mechanisms fail independently. No check in
`parse_reply` or `parse_claims` is removed or weakened by this ADR.

## Why

**Because the failure was never the model's judgement — it was its typing.**
Five families disagreed about nothing except how to spell a verdict. Chasing a
better judge was treating a symptom; the search for one is what turned this up.

**Because it converts a validation error into an impossibility.** ADR-026's
position — fail loudly, do not retry — is right and unchanged. This reduces how
often there is anything to fail about.

## Consequences

- **`GenerationRequest` gains a field**; `openai_compat` gains one conditional
  block. Both are additive.
- **`gemma4:12b` is still unusable.** Its failure is 32,076 characters of
  reasoning and no answer — a budget problem, not a grammar one. That needs
  `reasoning_effort`, which is OPEN-QUESTIONS 13's unwired half and not this ADR.
- **A non-Ollama backend is unaffected** unless the flag is passed.
- **OPEN-QUESTIONS 14 closes** once §5 is measured, whichever way it falls.

## Measured, 2026-09-17 — §5's comparison

Three judges x three transcripts, each run both ways. Two of the transcripts
already worked unconstrained, so a regression on the working case would be
visible rather than hidden behind a fix to the broken one.

| judge | transcript | off | on |
|---|---|---|---|
| `phi4:14b` | healthcare 14b-pro | **FAILED** | 44 claims `8/9/3/24` |
| `phi4:14b` | healthcare 0.6b-pro | **FAILED** | 21 claims `9/2/4/6` |
| `phi4:14b` | medicaid 14b-pro | 17 claims `2/0/7/8` | 36 claims `4/3/5/24` |
| `mistral-nemo` | healthcare 14b-pro | **FAILED** | 10 claims `4/3/1/2` |
| `mistral-nemo` | healthcare 0.6b-pro | **FAILED** | 6 claims `3/1/0/2` |
| `mistral-nemo` | medicaid 14b-pro | **FAILED** | 6 claims `2/1/2/1` |
| `qwen3:8b` | healthcare 14b-pro | 15 claims `13/2/0/0` | 16 claims `14/2/0/0` |
| `qwen3:8b` | healthcare 0.6b-pro | 11 claims `7/2/2/0` | 12 claims `9/3/0/0` |
| `qwen3:8b` | medicaid 14b-pro | 9 claims `1/4/4/0` | 12 claims `4/4/4/0` |

(counts are supported/contradicted/unsupported/not_checkable)

**1. Parse-failure rate: 5 of 9 → 0 of 9.** Every failure was eliminated, across
three families and three distinct failure modes.

**2. The ledgers got bigger, not thinner** — which is the regression §5 existed
to catch and it did not happen. Every directly comparable pair grew: 15→16,
11→12, 9→12, 17→36. Constrained decoding did not buy parseability by writing
less.

**So §5 is satisfied on both criteria.** The quality question ADR-026 §3 raised
is answered: this is a fix, not a trade.

### The finding §5 did not go looking for

**Under constraint, two families produce all four verdicts in one ledger,
repeatedly:**

| judge | strict off | strict on |
|---|---|---|
| `phi4:14b` | 0 of 1 | **3 of 3** |
| `mistral-nemo` | 0 of 0 | **2 of 3** |
| `qwen3:8b` | 0 of 3 | **0 of 3** |

B6's gate asked for three clauses in one ledger and ADR-031 closed the session
because nothing produced them. Two families now do, reliably.

**And `qwen3:8b` still never emits `not_checkable` — 0 of 3 even constrained.**
That is a fourth independent channel confirming ADR-031's conclusion: clause (3)
is not reachable on that model by changing what we ask for. It is a property of
the judge, and constraining the grammar does not touch it.

**Not a claim that the verdicts are right.** The isolation test on `phi4:14b`'s
earlier contradictions found one confirmed by four models, one contested, and one
false positive. Labels appearing reliably is a different thing from labels being
correct, and §5 measured only the former. Note also that `phi4:14b` marks more
than half its claims `not_checkable` (24 of 44, 24 of 36), which may be its own
distortion.

### Why the default still does not move

§4 gave two reasons. The second — "the measurement has not been run" — is now
discharged. **The first stands untouched:** `mlx_lm.server` does not honour
`response_format` (`BACKEND-PROBE-RESULTS`), and whether it *ignores* the field
or *rejects* it has never been tested. Ignoring is harmless; rejecting would turn
a working judge into a failing one for every AFM and `mlx_lm` user.

So the default stays off, and the thing that would flip it is small and named:
**send a constrained request to `fm serve` and to `mlx_lm.server` and record
which of the two they do.**

### Probed 2026-09-18 — nothing rejects it, and the default flips ON

Each server started on a free port, one plain request as a control and one
carrying the schema:

| server | plain | with `response_format` | verdict |
|---|---|---|---|
| Ollama | invalid JSON | schema-valid | **honours** |
| **AFM** via `fm serve` | ```` ```json ```` fence, off-enum `"approved"` | `{"verdict": "unsupported"}` | **honours** |
| **`mlx_lm.server`** | HTTP 200 | HTTP 200, identical | **ignores — harmless** |

AFM does better than this ADR assumed: it does not merely tolerate the field, it
**constrains on it**. `mlx_lm` returned empty content *both* ways, which is its
known reasoning-field behaviour (OPEN-QUESTIONS 13) and not caused by the schema
— the control proves that. What matters is that it answers 200 rather than
erroring.

**No tested server rejects `response_format`**, so §4's remaining reason is
discharged and `strict_json` now defaults to **on** — in `judge`, in the
`judge:` block, and in `api.judge`. `--no-strict-json` turns it off for a
backend nobody has probed.

The control request earned its place: the first AFM attempt failed on both arms
because the model is named `system`, not `afm`. Without a plain control that
would have been recorded as "AFM rejects response_format" — the opposite of the
truth, and the exact wrong conclusion to build a default on.

## Open questions this doesn't resolve

- Whether `debate` should ever constrain a turn. Nothing suggests it should.
- Whether the default should flip after §5. That is an amendment to this ADR,
  written after the artifacts exist.
- Whether constraining `evidence_ids` to real ids suppresses a *useful* signal:
  an invented citation is evidence the judge is not reading the record, and
  making it unemittable hides that. §5's ledger comparison is where this would
  show up.
