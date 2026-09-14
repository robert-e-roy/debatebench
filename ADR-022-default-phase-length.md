# ADR-022: A Bare Phase Means `medium`, Not "No Instruction"

**Status:** Accepted
**Date:** 2026-09-14
**Depends on:** ADR-016 (the `phase:length` suffix), ADR-011 (§2 the labels and
their sentence counts), ADR-005 (the transcript's per-turn record), ADR-021
(the principle that resolution happens before the run, not during it)
**Supersedes:** ADR-011 §4 and ADR-016 §3 — "omitted means no length
instruction" — and narrows ADR-016 §6's "present only when the phase carried a
suffix"

## Context — the fallback was invisible at the place it applied

`phases: [opening, rebuttal, conclusion]` is the shortest thing that runs, so it
is what a first config looks like and what the README's shortest example looked
like. It was also the one form that sent no length instruction at all, and
nothing in the file, the log, or the run said so. The difference between it and
`phases: [opening:medium, ...]` was a prompt sentence that appeared or didn't,
decided by a suffix that wasn't there.

ADR-011 §4 chose that fallback for a defensible reason: it was the behaviour
before length existed, so making it the fallback changed nothing for anyone. The
reason has expired. Length is not a new feature being added beside an existing
default any more — it is the mechanism, and "no instruction" is now a third
state hiding behind the absence of a value, distinguishable from `short`,
`medium` and `long` only by knowing this rule.

The practical cost is that an unsuffixed run's turn lengths are set by whatever
the model does unprompted, which varies by model. That is exactly the variable a
benchmark comparing two models is trying not to leave free.

## Decision

### 1. A phase entry with no suffix asks for `medium`

```yaml
phases: [opening, rebuttal, conclusion]           # every phase asks for ~5 sentences
phases: [opening:short, rebuttal, conclusion]     # 2, then 5, then 5
```

`medium` is ADR-011 §2's middle label, about 5 sentences. Naming it explicitly
still means exactly what it meant; `opening` and `opening:medium` are now the
same run.

### 2. `prep` is unchanged and still carries no length

ADR-016 §4 stands: `prep:short` is an error, and prep is bounded by
`prep_budget` alone. The default does **not** apply to prep — a prep entry
resolves to no length, exactly as before, and a prep turn still records none.

### 3. The default is resolved at load, not at prompt time

`RunConfig.lengths` carries `"medium"` where the entry was bare. Nothing
downstream — the prompt builder, the orchestrator, the transcript writer —
learns that a default exists; each sees a length that was already decided.

This is ADR-021 §5's rule applied to a second kind of resolution: what the run
actually asked for is fixed before the run starts, so the record of the run is
the record of what happened, not a set of inputs the reader has to re-resolve.
One consequence is that `prompts.LENGTH_SENTENCES` and `build_request` needed no
change at all.

### 4. Every non-prep turn now records its length (narrows ADR-016 §6)

ADR-016 §6 made `turn.length` "present only when the phase carried a suffix."
It is now present on every non-prep turn, because every non-prep phase now has
one. Prep turns still omit it, so the field stays optional and the
absent-not-null rule (ADR-014 §6) is unchanged.

`judge` does not read the field. ADR-016's Consequences left open that B5
*might* use it, so this was checked rather than assumed: no reference to
`length` exists in `judging.py` or `judge_cli.py`, and neither the scoring nor
the fact-check prompt interpolates it. So the same debate judged before and
after this ADR gets the same prompt, which matters because ADR-017 §6 reuses
the transcript's seed — a difference there would have been permanent, not
merely a re-run away.

The alternative — keep writing the field only where a suffix was typed, and let
absent mean "the default, whatever it is" — was rejected. It would make the
meaning of an old transcript depend on the default in force when it is *read*,
so changing the default later would silently re-interpret every file written
before the change. A transcript has to say what was asked for.

### 5. No `schema_version` bump

ADR-005 bumps on "any change to the document's shape." The shape is unchanged:
same key, same type, same rule about when it may be absent. Only which values
occur changes. A v2 file written before this ADR still reads correctly, and its
absent `length` on a non-prep turn still honestly means the instruction wasn't
sent — because it wasn't. A v2 reader written before this ADR reads a new file
correctly too. Recording the non-bump here so the next reader can see it was
decided rather than missed.

### 6. "No length instruction" is no longer expressible

There is no `opening:none`. The capability ADR-011 §4 provided is dropped, not
relocated — the same treatment, and the same reasoning, ADR-016 §2 gave the
per-team `length` field: one mechanism, and a capability nobody asked for is not
worth a second way to say nothing.

## Why

Three rules were competing and the weakest won. "Don't change behaviour when
adding a feature" (ADR-011 §4) beat "a config should say what it does" and "a
benchmark shouldn't leave a compared variable free." The first rule only had
force while length was new.

`medium` rather than `short` or `long` because it is the middle of the three and
the one both shipped examples already use for their substantive phases, so the
default matches what the project's own configs had already converged on by hand.

## Consequences

- **ADR-011 §4** and **ADR-016 §3** superseded; amendment notes added to both.
- **ADR-016 §6** narrowed by §4 above; its §1, §2, §4, §5 and §7 stand.
- **A bare-phase run produces different turns at the same seed.** The prompt
  gained a sentence, so a re-run of an unsuffixed config will not reproduce a
  transcript recorded before this change. Expected, and stated here because an
  unlabelled prompt change is exactly what cost this project two wrong
  diagnoses on 2026-09-14.
- **`examples/` is unaffected in behaviour** — both example configs already
  suffix every phase. Their comments now say what a bare entry would mean.
- **BUILD-GUIDE**: B1's validation cases and B2's prompt construction gain the
  default — retro-edits to finished sessions, the pattern ADR-011, ADR-014 and
  ADR-016 already set.
- **OPEN-QUESTIONS item 12**'s resolution note points here.
- **`CLAUDE.md`** Config section and the ADR list updated.
- **README.md**: the `format.phases` row and the length section.

## Open questions this doesn't resolve

- Whether 2/5/10 are the right sentence counts — untested since ADR-011 §2 set
  them, and this ADR makes 5 the one every unsuffixed run gets, so it is now the
  count most runs depend on.
- Whether a way to send no length instruction is worth having back (a
  model's unprompted length is itself a measurable property). If it is, that is
  a new ADR adding a fourth label, not a return to absence meaning it.
