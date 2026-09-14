# ADR-021: `debate` Override Flags for Model and Budget

**Status:** Accepted
**Date:** 2026-09-14
**Depends on:** ADR-007 (§1 CLI invocation, §6 validation), ADR-005 (the
transcript's `run` snapshot), ADR-020 (the same override principle for `judge`),
ADR-002 ("CLI shape")
**Amends:** ADR-007 §1 — `debate` is no longer flagless
**Does not amend:** Hard Rule 7. See §6.

## Context — A/B testing meant maintaining two nearly identical files

Comparing two models on one motion required a second `run.yaml` differing in a
single line, and then keeping the other twenty lines in sync by hand. The
transcript records what ran, so the *evidence* was never in doubt — the cost was
entirely in the editing, and in the risk that the two files drifted in some way
the experimenter did not intend and would not notice.

ADR-020 has already accepted this argument for `judge`: settings live in the
file, and a flag overrides one for a single run. This applies the same rule to
`debate`, and deliberately applies it to **less**.

## Decision

### 1. Two settings are overridable: `model` and `budget`

Nothing else. These are the two the motion's outcome is actually being tested
against, and they are the two ADR-002 names as the asymmetry axis between sides.

### 2. The symmetric form sets both sides at once

```bash
debate run.yaml --model phi4-mini:latest     # both teams
debate run.yaml --budget 4000                # both teams
```

This is the common case: `examples/run.yaml` and most real configs give both
sides the same model, and an A/B usually moves both.

### 3. The per-side form names the side of the motion, not its index

```bash
debate run.yaml --pro-model qwen3:8b --con-model phi4-mini:latest
debate run.yaml --pro-budget 4000
```

`--pro-*` and `--con-*`, matching `side: pro` / `side: con` in the file. **Not**
`--side0-*`: the index is an implementation detail of the teams list, and the
same run is more readable when the flag says which side of the motion it means.
Hard Rule 2 keys *state* by `(phase_index, side_index)` and is untouched by what
a flag is called.

### 4. Giving both forms for one setting is an error

`--model X --pro-model Y` is rejected, naming both flags. There is no
precedence rule, because any precedence would silently discard one of two
things the user explicitly asked for. The error says to drop one.

`--model X --con-budget N` is fine: different settings, no conflict.

### 5. An override changes the config, so the transcript records what ran

Overrides are applied to the loaded `RunConfig` before the debate starts, not
threaded into the backend call. Two things follow, and both are the point:

- **ADR-005's `run.sides` snapshot records the effective values.** A transcript
  produced with `--model phi4-mini:latest` says `phi4-mini:latest`, never the
  file's value. A snapshot that recorded the file would be a record of what was
  *not* run, which is worse than no snapshot.
- **ADR-007 §6's validation still applies.** `--budget 0` fails the same check
  a `budget: 0` in the file fails, with the same message.

### 6. What is deliberately not overridable

- **`output`** — and so **Hard Rule 7 is untouched**. The rule names the absence
  of an `--output` flag as part of its content, and an A/B does not need one:
  each run's output path is a property of that run, and two experiments that
  should not overwrite each other should say so in two files. A run whose output
  path came from the shell is also a run whose transcript no longer explains
  where it went.
- **`seed`** — ADR-007 §5 makes a seed generated-and-recorded when absent, so a
  seed sweep is already available by removing `seed:` from the file and reading
  what each run reports. A `--seed` flag would add a second mechanism for
  something that has one.
- **`base_url`** — not overridable, which bounds §2 and §3: a swapped model must
  be served by the address already in the file. Swapping to a model on a
  *different* server is a different run and wants a different file.
- **`topic`, `format.phases`, `teams`, `sources`** — changing any of these makes
  it a different debate, not the same debate under different conditions. A flag
  would blur the line the transcript exists to keep sharp.

## Why

- **The friction was real and the evidence risk was not.** The transcript always
  recorded what ran; what was expensive was maintaining two files to make one
  line differ.
- **Consistency with ADR-020.** One rule now covers both commands: settings in
  the file, flags override for a single run, and the override is what gets
  recorded.
- **Narrow on purpose.** Every additional overridable field is another way for a
  run's provenance to live in a shell history rather than in a file. Model and
  budget earn it; `topic` does not.
- **`pro`/`con` over indices.** The CLI already prints `side 0 (pro)`, and a
  flag that says `--con-model` needs no lookup to read.

## Consequences

- `debate` is no longer flagless, so ADR-007 §1's first sentence and
  `CLAUDE.md`'s "No other flags" are both now wrong as written and are updated.
- `--help` for `debate` becomes non-trivial for the first time.
- A config error caused by an override must name the **flag**, not the file's
  key, or the message sends the reader to a line that is not the problem.
- `README.md`, `examples/README.md` and `examples/run.yaml`'s comments gain the
  A/B form.

## Open questions

- Whether `judge` should grow the same `--pro-*`/`--con-*` shape is moot — it
  has one model, not two — but a future per-dimension judge model (ADR-020's own
  open question) would raise the same naming problem, and should resolve it the
  same way if it does.
