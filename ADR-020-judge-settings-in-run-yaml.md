# ADR-020: Judge Settings Belong in `run.yaml`, as an Optional `judge:` Block

**Status:** Accepted
**Date:** 2026-09-14
**Depends on:** ADR-007 (§1 CLI invocation, §6 validation), ADR-017 (judge CLI
details), ADR-013 (§2 `--budget`), ADR-015 (§3 the fact-check flag), ADR-005
(the transcript's `run` snapshot)
**Amends:** ADR-007 §1 — its consequence dropping `judge:` from the schema, and
its "flags for `judge`" rule
**Amended 2026-09-14:** §7 adds `judge.transcript`, naming the input the block
had left implicit, and resolves this ADR's own open question about judging
another run's transcript.
**Resolves:** the file-versus-flags asymmetry between the two commands

## Context — the asymmetry was argued from a smaller command

ADR-007 §1 gave `debate` a file and `judge` flags, and defended it:

> This isn't an inconsistency, it reflects what each command's config actually
> is. `debate`'s config is multi-part and fixed for that run — a file fits.
> `judge`'s entire reason for being a separate command is that the same
> transcript gets re-judged with different settings each time — a file you'd
> just edit and rerun is more friction than a flag, not less.

That is a fair argument about **one or two** settings. It is not the command
that now exists. `judge` requires **four** flags — `--model`, `--base-url`,
`--budget`, `--output` — three of which were added after ADR-007 was written
(ADR-013 §2 added `--budget`, ADR-017 §2 made `--base-url` required). A
64-character command line retyped for every run is not less friction than a
file, and "edit and rerun" is exactly what a flag override handles.

ADR-007's **stated** reason for dropping the `judge:` block was different, and
narrower:

> Nothing reads it — `debate` never invokes `judge`, and ADR-005's transcript
> `run` snapshot doesn't capture it. An unused block in the schema is worse
> than no block; a `judge:` section in a debate config would silently suggest
> it does something it doesn't.

Every clause of that is about a block **nothing reads**. This ADR adds one that
`judge` reads. The objection does not transfer, so this is a new decision
rather than a reversal of a considered one.

## Decision

### 1. `run.yaml` gains an optional top-level `judge:` block

```yaml
topic: "A federal carbon tax would do more good than harm."
format:
  phases: [opening:medium, rebuttal:medium, conclusion:short]
teams:
  - team: teams/advocate.yaml
    side: pro
    model: qwen3:8b
    base_url: http://127.0.0.1:11434/v1
    budget: 2000
  - team: teams/skeptic.yaml
    side: con
    model: qwen3:8b
    base_url: http://127.0.0.1:11434/v1
    budget: 2000
seed: 42
output: transcript.json

judge:
  model: qwen3:8b
  base_url: http://127.0.0.1:11434/v1
  budget: 6000
  output: scores.json
  fact_check: true      # optional; default true (ADR-015 §3)
```

**Nothing above `judge:` moves.** The existing top-level keys keep their
meaning and position, so every `run.yaml` written before today stays valid.
A nested `debate:` section was considered and rejected: it reads better, but
it invalidates every config in `examples/`, in `tests/fixtures/`, in the
README quickstart, and in the sdist already published to TestPyPI, and it buys
nothing the flat form does not.

`judge:` is **optional**. A `run.yaml` without it is valid and is exactly what
exists today.

### 2. `debate` still never invokes `judge`

Two commands, two passes. `debate` reads `judge:` only far enough to validate
it, and acts on nothing in it. Hard Rule 7 is untouched: `debate` writes to
`output:` and nowhere else, and `judge:`'s own `output:` is written only by
`judge`.

This was considered and declined deliberately. Folding the judge into `debate`
would make one command produce two files, which is a larger change than the
friction it removes, and it would couple a cheap re-judge to an expensive
re-debate.

### 3. `judge` takes either a `run.yaml` or a transcript

- `judge run.yaml` — reads the `judge:` block, and takes the transcript from
  the run's own `output:` path. The common case, and one word long.
- `judge transcript.json --model … --base-url … --budget … --output …` —
  unchanged, and still the only way to judge a transcript that has no
  `run.yaml`. `probe/validation/` and `probe/b6/` hold exactly those.

The two are told apart by **extension**, not by sniffing content: a path
ending `.yaml` or `.yml` is a run config, anything else is a transcript.
This is stated in the error messages rather than inferred, per ADR-007 §6's
"no silent guessing" rule.

### 4. Flags override the file

Where a setting appears in both, the flag wins, so one-off variations need no
edit:

```bash
judge run.yaml --model phi4-mini:latest     # same config, different judge
```

A flag that is absent from both the command line and the `judge:` block is an
error naming the field and both ways to supply it. `--model`, `--base-url`,
`--budget` and `--output` stop being argparse-`required` and become
**required after merging** — which is what lets the same parser serve both
forms. `fact_check` defaults to true in both (ADR-015 §3).

### 5. The transcript does not record the `judge:` block

ADR-005's `run` snapshot captures what produced the debate. Judge settings did
not produce it, and the transcript is routinely judged later with settings that
differ from whatever sat in the file at debate time — recording them would be
recording a claim that goes stale the first time anyone re-judges. The score
file already records `judge_model` and `judge_budget` (ADR-013 §5), which is
where that belongs.

### 6. `judge.output` may not be the transcript path

If `judge.output` resolves to the same file as the run's `output:`, `judge`
would rotate the transcript to `<name>.1` and write the score file over it —
destroying, on the second run, the input it had just read. Nothing about the
two-`output:` shape makes that mistake obvious to the person writing the file.
It is a validation error, naming both keys.

### 7. `judge.transcript` names the input (added 2026-09-14)

As first written, the block said where its **output** went and never named its
**input**: `judge run.yaml` read the run's own `output:`, and a comment had to
explain that the judge's input was the key called `output`. Needing a comment to
explain a data flow is the defect, not the comment.

```yaml
output: transcript.json      # debate writes here

judge:
  transcript: transcript.json   # optional: judge reads here
  output: scores.json           # judge writes here
```

`transcript:` is **optional** and defaults to the run's `output:`, so every
`judge:` block written before this amendment keeps working. Naming it also
settles this ADR's open question — judging an *earlier* run's transcript with
today's settings is now a path, not a workaround:

```yaml
judge:
  transcript: archive/2026-09-01.json
  output: scores-rejudged.json
```

The collision check in §6 widens with it. `judge.output` must differ from both
its own input **and** the run's `output:` — otherwise `transcript: old.json`
with `output: transcript.json` would clobber the debate's transcript from the
other direction. The error names whichever key the reader actually wrote:
blaming `judge.transcript` for a collision with a default they never typed
would send them to a line that is not in their file.

## Why

- **The friction argument reversed as the command grew.** ADR-007 weighed one
  flag against a file. Four required flags is the case a file is for.
- **The original objection was about dead config.** A block nothing reads is
  worse than no block — and that is still true. This block is read.
- **Non-breaking beats tidy.** The nested form is prettier and costs every
  existing config. The project has a published artifact and its own examples
  to keep working.
- **A transcript outlives its run config.** Keeping the transcript-plus-flags
  form is not backward-compatibility ballast; it is the only form that works
  for a transcript someone hands you.

## Consequences

- `config.py` gains a `JudgeConfig` and a `judge:` parser; `judge` leaves
  `_REMOVED_RUN_KEYS` and joins `_RUN_KEYS`. Its removal hint is deleted —
  the key means something again.
- `judge_cli.py` merges file and flags, and validates requiredness after the
  merge rather than in argparse.
- ADR-007 §1's sentence "This isn't an inconsistency" no longer describes the
  tool. ADR-007 stays the record of why it was once true.
- `examples/run.yaml`, the README's judge invocation and `CLAUDE.md`'s Config
  section all gain the block.
- **`run.yaml` now has two `output:` keys at different levels**, one for the
  transcript and one for the score file. That is a real readability hazard and
  the validator should keep their error messages distinguishable by path
  (`output` versus `judge.output`).

## Open questions

- Whether `judge:` should accept a `model` per *dimension* later (a cheap model
  for clarity, an expensive one for `argument_quality`) is untouched here and
  would be its own ADR.
- ~~Whether a `judge:` block should be allowed to name a transcript other than
  the run's own `output:`~~ — **resolved 2026-09-14 by §7**: `judge.transcript`
  names it, and defaults to `output:` when omitted.
