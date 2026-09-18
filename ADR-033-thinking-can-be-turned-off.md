# ADR-033: `thinking: false` Sends Both Switches, and Is Opt-In Because AFM Rejects One

**Status:** Accepted
**Date:** 2026-09-18
**Depends on:** ADR-009 (the backend request type), ADR-018 §4 (send both budget
fields, for the same reason), ADR-032 (the pattern an optional request field
follows), Hard Rule 5 ("budgets (token/reasoning)")
**Amends:** ADR-009's `GenerationRequest`, which gains one optional field
**Resolves:** OPEN-QUESTIONS 13's unwired half

## Context — the budget buys thinking, and thinking is not the product

`budget` caps completion tokens, and completion tokens include a reasoning
model's thinking. Hard Rule 5 already says "budgets (token/reasoning)"; nothing
has ever acted on the second word. The cost is not theoretical:

- **`gemma4:12b` cannot judge at all.** On a full judge prompt it returned
  **32,076 characters of reasoning and no answer**, failing after 14 minutes. An
  entire family is unusable, not merely expensive.
- **The comparison this tool exists to make is confounded.** The same budget
  buys a reasoning model far less argument than a non-reasoning one — which is
  OPEN-QUESTIONS 9's problem arriving through a second door.

## Measured first, because the design depended on it

Every cell below was probed directly on 2026-09-18, each with a plain control.

**What turning it off is worth** (Ollama, one prompt, budget 3000):

| model | field | tokens | thinking chars | answer chars | time |
|---|---|---|---|---|---|
| `gemma4:12b` | — | 492 | 2,254 | 229 | 35.9s |
| `gemma4:12b` | `reasoning_effort: none` | **45** | **0** | **257** | **2.7s** |
| `qwen3:8b` | — | 255 | 1,040 | 251 | 14.0s |
| `qwen3:8b` | `reasoning_effort: none` | **40** | **0** | 212 | **1.6s** |

Thinking goes to zero, the answer is **no shorter**, and the call is an order of
magnitude faster. `reasoning_effort: "low"` is **inert on Ollama** — byte-identical
to sending nothing — so `none` is the only value that does anything.

**Which switch each server takes:**

| server | `reasoning_effort: "none"` | `chat_template_kwargs` | both |
|---|---|---|---|
| **Ollama** | **works** | accepted, ignored | **works** |
| **`mlx_lm.server`** | accepted, **inert** | **works** | would work |
| **AFM** (`fm serve`) | **HTTP 400 — rejected** | n/a | would fail |

AFM's refusal is explicit: `reasoning_effort is not supported by the 'system'
model`. AFM also does not need it — it returns no reasoning at all.

## Decision

### 1. One setting, expressing intent rather than mechanism

`thinking: false` on a team entry in `run.yaml`, and in the `judge:` block.
`GenerationRequest` gains `thinking: bool = True`; when it is false the adapter
sends **both** switches:

```json
"reasoning_effort": "none",
"chat_template_kwargs": {"enable_thinking": false}
```

A boolean, not `low`/`medium`/`high`, because `low` was measured inert and off is
the only setting that does anything. If a server ever grades effort usefully,
that is an amendment with a measurement attached.

### 2. Both switches, for exactly ADR-018 §4's reason

No single field works everywhere: Ollama reads one, `mlx_lm` reads the other,
each ignores the one it does not know. That is the same shape as `max_tokens`
versus `max_completion_tokens`, and it is settled the same way — send both, let
each server take the one it understands.

### 3. But **opt-in**, which is where this differs from ADR-018 §4

ADR-018 could send both budget fields unconditionally because every server
ignores the field it does not know. **AFM does not ignore `reasoning_effort` —
it returns HTTP 400.** Sending this by default would break every AFM user, and
AFM is this project's documented development default (ADR-002).

So `thinking` defaults to **true** (think as you always did), and turning it off
is a deliberate per-run choice. This is the opposite of ADR-032's conclusion, and
for a concrete reason: nothing rejected `response_format`; something rejects
this.

**Do not set `thinking: false` on an AFM side.** It is a config error waiting to
happen at run time rather than load time, and §5 is why it is not validated here.

### 4. It is available to debaters as well as the judge

The confound in OPEN-QUESTIONS 13 is about *debaters* — a reasoning debater
spends its budget thinking and speaks less for the same cap. So it is a per-side
key, not judge-only. `debate` gains no flag: ADR-021 fixed that command's
override list at model and budget, and this is a property of the run, not a
sweep.

### 5. It is not validated against the backend, and that is deliberate

`config.py` cannot tell which server a `base_url` points at, and ADR-002 keeps
this tool from sniffing. A wrong combination therefore fails at the first call
with the server's own message — `reasoning_effort is not supported by the
'system' model` — which names the field, the model and the cause. That is
ADR-026's standard for a useful failure, and it is better than a guess encoded
in a validator.

## Why

**Because a judge that never answers is not a judging problem.** `gemma4:12b`
spent fourteen minutes thinking and produced nothing. No prompt, schema or budget
fixes that; one request field does.

**Because the thing it costs is the thing being measured.** Comparing models on
argument quality while the budget silently funds monologue in one and argument in
the other measures the wrong thing.

## Consequences

- **`GenerationRequest` gains `thinking: bool = True`.** Default true, so every
  existing request is byte-identical.
- **`gemma4:12b` becomes usable as a judge** — untested as such, and it should
  be characterised before being trusted (`MODEL-COVERAGE.md` gap 5).
- **Turning it off changes what a model writes**, so a comparison must hold it
  constant, exactly as load state and budget must be held constant.
- **AFM users must leave it alone.** Recorded in the README and in `run.yaml`'s
  documentation rather than enforced.

## Verified 2026-09-18 — a judge family came back

`gemma4:12b` judging `healthcare-14b-pro` with `--no-thinking`:

| | before | after |
|---|---|---|
| result | **32,076 chars of reasoning, no answer** | pro 93, con 44 |
| ledger | — | 42 claims: 30 supported, 1 contradicted, **11 not_checkable** |
| time | 14 min, then failed | **4m34s** |

It also produces `not_checkable` — a **third** family doing so, where `qwen3:8b`
never has in any configuration. That strengthens ADR-031's reading further: the
clause is a property of the judge.

`gemma4:12b` is still uncharacterised as a judge and should not be trusted on one
run; note the 93-44 spread is the widest any judge has produced on these
transcripts, which is as likely to be miscalibration as insight.

## Open questions this doesn't resolve

- Whether a transcript should record it. ADR-005 has no field, and this changes
  the reply materially — unlike `timeout`, which ADR-025 §6 excluded precisely
  because it cannot. It probably belongs in the snapshot; that is a
  `schema_version` question and its own decision.
- Whether `gemma4:12b`, once it can answer, is any good at judging.
- Whether AFM's refusal extends to `chat_template_kwargs` — untested, because
  AFM needs neither.
