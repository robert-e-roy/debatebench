# ADR-032: The Judge May Ask the Server to Constrain Its Reply to the Schema

**Status:** Accepted
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

## Open questions this doesn't resolve

- Whether `debate` should ever constrain a turn. Nothing suggests it should.
- Whether the default should flip after §5. That is an amendment to this ADR,
  written after the artifacts exist.
- Whether constraining `evidence_ids` to real ids suppresses a *useful* signal:
  an invented citation is evidence the judge is not reading the record, and
  making it unemittable hides that. §5's ledger comparison is where this would
  show up.
