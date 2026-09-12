# ADR-016: Per-Phase Length — `phase:length` in the Phase List

**Status:** Accepted
**Date:** 2026-09-12
**Depends on:** ADR-007 (§4 phase list, §6 validation), ADR-010 (§2 phase
meanings, prompts), ADR-011 (length labels and sentence counts), ADR-005
(transcript)
**Supersedes:** ADR-011 §1 (the per-team `length` field) and §6 ("one length
per side, not per phase"). ADR-011 §2 (the labels and their sentence counts),
§3 (target-in-prompt, `budget` stays the cap, no cross-field validation), §4
(omitted means no length instruction) and §5 (no time-based option) all
stand unchanged.

## Decision

### 1. Length is a suffix on a phase entry

Each entry in `format.phases` is either a bare phase name or
`name:length`:

```yaml
format:
  phases: [prep, opening:short, rebuttal:long, retort:medium, rebuttal:long, conclusion:short]
```

`length` is one of `short`, `medium`, `long`, with ADR-011 §2's meanings
(about 2, 5, 10 sentences). A suffix applies to **both sides** for that
phase — same for both teams, the way every real format sets a speech length
by speech type, not by team.

### 2. The per-team `length` field is removed

ADR-011 §1 put `length` on each `teams:` entry. That field is gone. A
`length` key in a `teams:` entry is a validation error whose message points
here, the same treatment ADR-007 §6 gives `format.prep` and `format.rounds`.
One mechanism, not two.

This drops one capability ADR-011 had: a different length per side. It was
never a stated requirement — ADR-002's asymmetry axis is model and budget —
and the per-phase form is the one real formats use. If per-side length is
wanted later, that's a new ADR, not a second field alongside this one.

### 3. Omitted suffix means no length instruction

A bare name (`opening`) gets no length target in its prompt, exactly ADR-011
§4's fallback. Mixed lists are fine: some phases with a suffix, some without.

### 4. `prep` never takes a suffix

`prep:short` is an error. ADR-011 §1 already excludes prep from length, and
ADR-012 §3 bounds the prep synthesis call by `prep_budget` alone.

### 5. Validation (amends ADR-007 §6)

For each entry in `format.phases`:

- it must be a string. **A mapping is an error with a hint**: `rebuttal: long`
  (space after the colon) is a YAML mapping, not the string `rebuttal:long`;
  the error says to remove the space.
- at most one `:`; the part before it is a phase name from ADR-007 §6's fixed
  list; the part after it, if present, is exactly one of `short`, `medium`,
  `long` — no other value, no case variants.
- `prep` may not carry a suffix (§4).
- everything ADR-007 §6 already says about the list (non-empty, `prep` at
  most once and first, other names may repeat) still applies to the bare
  names.

### 6. Transcript (amends ADR-005)

- `run.phases` stays a list of **bare names**, as now — `turn.phase` is a bare
  name and ADR-010 §2's meanings are keyed by name; nothing that reads
  `run.phases` today should have to split a string.
- Each turn gains an optional **`length`** field, `"short"` / `"medium"` /
  `"long"`, **present only when the phase carried a suffix** — absent
  otherwise, never `null`, following ADR-014 §6's absent-not-empty rule for
  `evidence`. Prep turns never have it.
- ADR-011's consequence that `run.sides` would gain a `length` field per
  side is withdrawn with the field.
- This is a shape change to the document, and B3 has already written
  version-1 transcripts, so **`schema_version` becomes 2**, per ADR-005's
  own rule ("bumped on any change to the document's shape"). Migrating a v1
  transcript forward is a no-op: it has no `length` fields.

### 7. Prompts (B2)

The phase prompt states the target sentence count for that phase (ADR-011
§3's wording is B2's to write), read from the suffix rather than from the
team entry. Both sides get the same instruction for the same phase.

## Why

`opening:short, rebuttal:long, conclusion:short` says, in one line, what a
real format's timing table says, and it says it once. The per-team field
could only say "this side is always long," which no format does, and it
couldn't say "rebuttals are longer than conclusions," which every format
does. Keeping both fields would have meant defining a precedence rule for a
combination nobody asked for.

## Consequences

- **ADR-011**: §1 and §6 superseded; amendment note added.
- **ADR-007 §6**: phase-entry grammar as in §5 above; `length` in a `teams:`
  entry becomes an error.
- **ADR-005**: per-turn `length`, `schema_version` 2.
- **ADR-002**: the `run.yaml` example shows suffixes.
- **BUILD-GUIDE**: B1's validation cases gain the entries in §5 (mapping-with-
  hint, bad suffix, `prep:` suffix, `length` on a team); B2's prompt
  construction reads the suffix. Both are retro-edits to finished sessions,
  the same pattern ADR-011 and ADR-014 already set.
- **`CLAUDE.md`** Config section updated.
- **OPEN-QUESTIONS** item 12's resolution note updated to point here.
- **`judge`** (ADR-013) can now see, per turn, what length was asked for,
  which bears on how it reads `hit_budget` and scores clarity. No change to
  ADR-013 is required by this; B5 may use the field.

## Open questions this doesn't resolve

- Whether 2/5/10 are the right counts — unchanged from ADR-011, untested.
- Per-side length asymmetry — explicitly out, see §2.
