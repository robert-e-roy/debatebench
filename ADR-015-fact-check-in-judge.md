# ADR-015: Fact-Checking Lives in `judge` — Real-Time Per-Turn Deferred to the Swift App

**Status:** Accepted
**Date:** 2026-09-12
**Amended:** 2026-09-12 — researched existing claim-verification tools
(MiniCheck) before committing to a custom prompt; recorded why none becomes
a dependency and what methodology gets adopted anyway. No decision changed;
see "Prior art considered" below.
**Depends on:** ADR-002 ("CLI shape", "Fact-checking is separate from judging",
"Hardware" B0 findings, "Language split"), ADR-007 (`judge` flags),
ADR-013 (judge call structure, `prep_grounded`, score-file format),
ADR-014 (prep privacy — evidence is recorded for the judge to read)
**Resolves:** OPEN-QUESTIONS.md item 4, and the "where the fact-checker runs"
hardware question left open by B0

## Decision

### 1. For v1 of the Python CLI, fact-checking is a pass inside `judge`

Fact-checking runs post-hoc, over the finished transcript, as part of
`judge`, controlled by the existing `--fact-check` / `--no-fact-check` flag
(default on, ADR-007 §1). It is not part of `debate`, and it is not its own
command.

**Real-time, per-turn fact-checking is a feature of the future Swift app
(`DebateKit`), not this repo.** ADR-002's "Fact-checking is separate from
judging, and runs on a different clock" described the per-turn version; that
description now applies to the Swift app. The CLI keeps the typed event
seam B2 wired in (ADR-001's `events.py` lift) precisely so a live consumer
can attach later — nothing in this repo consumes those events, and nothing
needs to.

### 2. What the v1 pass actually checks against — the record, not the world

ADR-013 §4 distinguished `prep_grounded` ("against the side's own prep
evidence") from `fact_check` ("against the world"). "The world" isn't
reachable in v1: no web access, no external knowledge base, no new
dependencies (ADR-008), offline by requirement (ADR-002). So the v1
fact-check is defined honestly as **a per-claim audit against everything
recorded in the transcript** — both sides' `evidence` passages, and both
sides' turns — not against external truth.

Concretely, for each argument-phase turn, the pass extracts the factual
claims it makes (not opinions or value statements) and gives each one a
verdict:

- **`supported`** — a recorded passage (either side's) backs it.
- **`contradicted`** — a recorded passage (either side's) contradicts it.
- **`unsupported`** — nothing recorded bears on it either way.
- **`not_checkable`** — an opinion, prediction, or value claim, not a
  factual one.

This differs from `prep_grounded` in two ways, which is why both exist:
`prep_grounded` is a *graded dimension* (0–25) about how well a side's own
citations trace to its own prep; the fact-check is a *claim-level ledger*
across the whole record, and it checks against the opponent's evidence too —
side A's claim contradicted by side B's recorded passage is a finding
`prep_grounded` can't produce.

The judge model's own knowledge is used only to classify a claim as factual
or not, never as a source of truth for a verdict. A transcript with no prep
(no `evidence` anywhere) gets `not_checkable` for every factual claim, with
a top-level note saying why, the same graceful degradation as
`prep_grounded: false`.

### 3. A second call, not the same call

ADR-013 §2 fixed the scoring at exactly one backend call. The fact-check is a
different task (claim extraction and verification, not rubric scoring) with
a different output shape, so when `--fact-check` is on, **`judge` makes one
additional call**, capped by the same `--budget` value applied to that call
on its own. The scoring call and its output are unchanged. ADR-013 §2's
"exactly one call" now reads "exactly one *scoring* call; the fact-check, if
enabled, is a second call."

### 4. Score-file addition

When enabled, the score file (ADR-013 §5) gains a `fact_check` section:

```jsonc
"fact_check": {
  "checked_against": "recorded_evidence",   // never "world" in v1
  "claims": [
    { "phase_index": 1, "side_index": 0,
      "claim": "Carbon pricing reduced emissions in British Columbia.",
      "verdict": "supported", "evidence_ids": ["args-me:48213"] },
    { "phase_index": 2, "side_index": 1,
      "claim": "...", "verdict": "contradicted", "evidence_ids": ["debatesum:9917"] }
  ]
}
```

`fact_check_enabled: false` means the section is absent, not empty. This is
a `schema_version` bump for the score file (ADR-013 defined it at 1 without
this section), to 2.

## Why

Three accepted ADRs had already assumed this by accretion — ADR-002 "CLI
shape" said `judge` scores "against the rubric plus fact-check", ADR-007
gave `judge` the flag, ADR-013's score file had `fact_check_enabled` — while
ADR-002's own "different clock" section and OPEN-QUESTIONS item 4 said the
opposite or said it was undecided. This ADR writes down the direction the
code was already pointing, and puts the per-turn version where it actually
belongs: the app that has a live UI to show it in. It also removes a real
hardware problem: B0 found no separate host for a live pass to run on, and a
post-hoc pass doesn't need one — it runs when the judge runs, after the
debaters have unloaded.

Defining "against the record, not the world" is the honest scope for a tool
that is offline and dependency-frozen. A fact-checker that quietly used the
model's own knowledge as ground truth would be the confident-looking,
unauditable check this project has refused everywhere else.

## Consequences

- **ADR-002 amended**: "What this is" no longer says "real-time
  fact-checking"; the "different clock" section is marked as describing the
  Swift app's feature; the B0 "fact-checker has no offload target" finding is
  marked resolved (moot for v1).
- **ADR-013 amended**: §2's one-call statement narrowed to the scoring call;
  §5's score file gains the `fact_check` section and moves to
  `schema_version` 2.
- **BUILD-GUIDE B6 rewritten**: it's now "the fact-check pass in `judge`",
  depends on B4 (recorded evidence) and B5 (the `judge` command), and its
  deliverable is the claims ledger above.
- **OPEN-QUESTIONS item 4 resolved**; the "where the fact-checker runs"
  hardware row and the "B6: inside `debate` or its own command" row in the
  index are both closed.
- **`CLAUDE.md`'s "What this project is"** drops "real-time".
- **DebateKit**, when it starts, inherits the per-turn version as a feature
  requirement, attaching to the CLI's existing event seam.

## Prior art considered, and why it isn't a dependency (added 2026-09-12)

Checked before assuming a custom prompt was the only option, per this
project's own practice of researching before building. `MiniCheck` (Tang,
Laban, Durrett; EMNLP 2024) is a real, purpose-built tool for exactly this
task, given a document and a sentence, is the sentence supported. Unlike
most prior-art checks in this project's history, it isn't solving an
adjacent problem; it's the same one.

It doesn't become a dependency here, for three separate, stated reasons:

- **License splits by size.** The two smallest variants
  (`lytang/MiniCheck-RoBERTa-Large`, `lytang/MiniCheck-DeBERTa-v3-Large`,
  both ~0.4B) are MIT. The best-performing variant
  (`bespokelabs/Bespoke-MiniCheck-7B`) is free for non-commercial use only.
- **The MIT-licensed variants are classifiers, not chat models.** They
  output a binary label from a classification head, with no chat-completions
  interface at all. Every backend in this project goes through one seam
  (ADR-001's single-method `async generate()`, ADR-009's `Message`-based
  request shape). Using them would mean a second, structurally different
  backend type, not a config change.
- **Any variant means a new runtime dependency** (`transformers`/`torch` at
  minimum), contradicting ADR-008's fixed two. Unlike the dataset question
  ADR-012 resolved, there's no "one-time manual step" escape hatch available
  here, this is inference code, not data.

**What's actually adopted is the methodology, not the package**: B6's
claim-extraction step (§2) decomposes each turn into individual sentence-
level factual claims and checks each independently against the evidence,
the same decomposition MiniCheck's own approach uses, run through the
existing single second-call seam this ADR already fixed, with no new
dependency. The four-verdict vocabulary (`supported`/`contradicted`/
`unsupported`/`not_checkable`) is richer than MiniCheck's binary output by
design, `contradicted` and `not_checkable` are both genuinely useful
distinctions in a debate context that a generic hallucination-detection
binary doesn't need to make.

RAGAS (a full RAG-evaluation framework with a "faithfulness" metric doing
structurally the same job) was also surfaced in the same search and rejected
faster: it's a batch-evaluation framework with its own dependency footprint,
a shape mismatch for a single pass inside one CLI command, independent of
the licensing and backend-type questions above.

**OpenFactCheck** (Wang et al., 2024) was checked separately and rejected
more fundamentally than either. It's a full research framework, three
modules for response evaluation, whole-LLM benchmarking, and leaderboarding
fact-checkers against each other, and its `ResponseEvaluator` is explicitly
built for *open-domain* verification, checking claims against the live
world via search or an external knowledge base, not against a closed,
recorded evidence set. That's the opposite of what this ADR requires: this
project checks against the record because the world isn't reachable
offline, with two fixed dependencies, by design. OpenFactCheck fails on
mechanism before its dependency weight (a full framework, `pip install
openfactcheck`, its own config and pipeline system) even becomes the
deciding factor. Its own licensing is also inconsistent across releases,
GitHub states MIT, one PyPI snapshot shows Apache-2.0, worth a direct check
if it ever mattered more than it does here, since the mechanism mismatch
alone is disqualifying regardless of which license is current.

## Open questions this doesn't resolve

- Claim extraction is itself a model task with its own failure modes (missed
  claims, split claims). Its prompt and any sanity checks are B6's to write,
  within the verdict vocabulary above, informed by MiniCheck's decomposition
  approach per the above.
- Whether the fallacy-detector and stance-consistency checks (ADR-002, still
  open) join this second call, get their own, or stay out of v1.
