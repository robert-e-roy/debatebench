# ADR-011: Response Length — `short`/`medium`/`long` Sentence Targets

**Status:** Accepted
**Date:** 2026-09-12
**Amended:** 2026-09-12 — §1 (the per-team `length` field) and §6 ("one
length per side, not per phase") are superseded by ADR-016: length is now a
`name:length` suffix on each entry in `format.phases`, applying to both sides.
§2–§5 stand unchanged. The consequence below that `run.sides` gains a
`length` field is withdrawn; ADR-016 §6 puts `length` on each turn instead.
**Depends on:** ADR-002 ("Asymmetry"), ADR-005 (transcript `sides` snapshot),
ADR-007 (`run.yaml` schema, validation), ADR-010 (`hit_budget`)
**Resolves:** OPEN-QUESTIONS.md item 12

## Decision

### 1. A new optional per-team field, `length`

Each `teams:` entry in `run.yaml` may carry `length: short | medium | long`.
Any other value is a validation error, same tier as an invalid `side`
(ADR-007 §7). It applies to every non-prep phase for that side, the same
scope `budget` already has; Prep is governed separately and isn't affected.

### 2. Fixed sentence-count targets, not configurable in v1

- `short` — about 2 sentences.
- `medium` — about 5 sentences.
- `long` — about 10 sentences.

These are fixed constants, not a schema knob, for the same reason Prep's
top-10-passages default wasn't made configurable: there's no real usage yet
to say whether 2/5/10 are the right numbers, and exposing a knob before that
evidence exists is guessing dressed up as flexibility.

### 3. `length` states a target in the prompt; `budget` stays the hard cap

The two fields do different jobs and neither replaces the other. `length`
becomes part of what the prompt asks for, "answer in about five sentences,"
exact wording is B2's to write, per the precedent ADR-010 already set for
phase-prompt text. `budget` remains the required, orchestrator-enforced
token ceiling (Hard Rule 5), unchanged.

**No new cross-field validation between them.** If `budget` is too small to
hold the requested `length`, that's a real possible misconfiguration, but
catching it would need a tokens-per-sentence estimate baked into strict
validation, which is exactly the kind of guess this project avoids adding
without evidence. The existing `hit_budget` flag (ADR-005/ADR-010) already
surfaces this failure mode after the fact: a turn that hit its budget before
finishing is visible in the transcript regardless of why.

### 4. Optional, with today's behavior as the fallback

If `length` is omitted, no length instruction is added to the prompt —
exactly the behavior item 12 already described as the current default
(budget-only cap, no stated target).

### 5. No time-based option

Sentence counts, not minutes. This avoids the conversion chain a time-based
setting would need (a speaking rate to get from time to words, then a
tokenizer-dependent rate to get from words to tokens, and whether those rates
get recorded for reproducibility) and the YAML syntax problem an unquoted
time value would hit (`1:30` parses as a YAML 1.1 base-60 integer, which the
strict loader rejects). If a time-based mode is wanted later, it's new scope
with its own ADR, not a variant of this one.

### 6. One length per side, not per phase, in v1

Real formats vary length by phase (Public Forum: 4, 4, 3, 2 minutes across
its four speech types), but `length` here applies uniformly across all of a
side's argument-phase turns, the same granularity `budget` already has.
Per-phase length is a real future enhancement, not decided here.

## Why

`budget` alone is a ceiling, not a target: a generous budget doesn't make a
reply longer, since the model writes however long the prompt implicitly
suggests, which in practice runs to five, ten, or more sentences, far past
what a natural debate turn sounds like. A stated target is what actually
makes length follow a setting. Sentence counts were chosen over time
specifically to skip a whole layer of unit conversion and a YAML parsing
problem that a time-based version of this same decision would otherwise need
to solve first.

## Consequences

- **ADR-007 §6 (validation) gains a case**: `length`, if present, must be
  exactly one of `short`, `medium`, `long`; any other value, including
  near-misses like `Short` or `med`, is an error.
- **ADR-005's `run.sides` snapshot gains a `length` field per side** (when
  set), parallel to how `model`, `budget`, and `prep_budget` are already
  recorded there — a transcript stays self-documenting about what length was
  requested even if `run.yaml` changes later.
- **B2's prompt construction** now has one more concrete instruction to
  write in: stating the phase's target sentence count. Exact wording is
  B2's call, within this ADR's numbers.
- OPEN-QUESTIONS item 12 is resolved.

## Numbering note

This is ADR-011. Separately from this decision: the Prep-retrieval mechanism
I drafted earlier under the label "ADR-008" was never reconciled with the
canonical ADR-008 (Python/`httpx`/PyYAML/strict YAML loader), which took that
number in this repo. If that Prep-retrieval decision gets reinstated, it
should be numbered **ADR-012** or later, not ADR-008, to avoid recreating the
exact collision this note exists to prevent.
