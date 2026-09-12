# ADR-013: Judge Scoring — Aggregation, Winner Determination, and Score-File Format

**Status:** Accepted
**Date:** 2026-09-12
**Amended:** 2026-09-12 — added the judge call structure and a required
`--budget` flag (both genuinely missing, not just underspecified); renamed
`verified` to `prep_grounded` to stop it colliding in meaning with
`fact_check`; made explicit that this ADR makes B5 buildable, not
trustworthy — item 6 (validating the judge against human ratings) is
untouched and still blocks B7.
**Depends on:** ADR-002 ("Judge design"), ADR-003 (AFM's ~4,096-token
session limit), ADR-005 (transcript format), ADR-007 (`judge` CLI flags —
amended by this ADR, see §2), ADR-009 (`BackendError` on any failed call),
CLAUDE.md Hard Rule 3
**Resolves:** OPEN-QUESTIONS.md item 2

## Decision

### 1. The judge model never outputs a blended score

One call, described in §2, produces exactly five independently-scored fields
**per side**, each with its own justification text:

```jsonc
{
  "argument_quality": {"score": 24, "max": 30, "justification": "..."},
  "evidence_grounding": {"score": 18, "max": 25, "justification": "...", "prep_grounded": true},
  "steelman_fidelity": {"score": 15, "max": 20, "justification": "..."},
  "rebuttal_effectiveness": {"score": 11, "max": 15, "justification": "...",
    "hit_ledger": [
      {"point": "carbon tax regressivity", "status": "rebutted"},
      {"point": "border adjustment complexity", "status": "conceded"}
    ]},
  "clarity": {"score": 8, "max": 10, "justification": "..."}
}
```

A missing field, an out-of-range score, or a non-integer score is a hard
error for the whole judging run, never a zero, never a partial result. This
is what satisfies Hard Rule 3 literally: the model itself never collapses
these five qualities into one number.

### 2. Judge call structure — one call, whole transcript, both sides at once

The judge makes **exactly one *scoring* call** per judging run, with the
entire transcript (both sides, every phase) as context, and returns both
sides' five-dimension scores in that single structured response. (When
`--fact-check` is on, ADR-015 §3 adds one further call for the claims
ledger; the scoring call is unchanged.)

This isn't a detail left to "prompt wording is B5's job" (ADR-010's
deferral pattern covers *what a prompt says*, not *whether there's one call
or several*, which is a real architectural choice this ADR has to make).
One call, not one per side, because `rebuttal_effectiveness` and the
hit-ledger inherently require the opponent's turns in context regardless of
how many calls are made, and scoring both sides from the same single read of
the debate avoids the risk of two separate calls applying the rubric
inconsistently between them, a real concern given LLM judges' documented
position/order biases (OPEN-QUESTIONS item 9).

**`judge` gains a required `--budget` flag** (an amendment to ADR-007 §1's
CLI flag list, which didn't have one): the completion-token cap for this one
call, enforced by the orchestrator exactly as any other budget (Hard Rule
5). No default — required, for the same reason `budget`/`prep_budget` in
`run.yaml` have none.

**A judge model whose context can't hold the whole transcript fails via the
existing `BackendError` path (ADR-009)**, the same as any other backend
limit. No new special-case handling or pre-flight size check is added here.
BUILD-GUIDE B7 already documents that AFM specifically can't serve as judge
for a real transcript (~4,096-token session limit, ADR-003); this ADR
doesn't change that, it just confirms the failure mode is already covered
generically rather than needing its own mechanism.

### 3. The winner comes from a deterministic step outside the model

A **fixed, published arithmetic step**, not a model judgment, computes each
side's total (sum of the five scores, max 100) and compares them. This
isn't "blending" in Hard Rule 3's sense: the rule forbids an opaque,
model-internal collapse of incomparable qualities into a number nobody can
audit, the exact anti-pattern rd-serendipity's blended score was (ADR-001).
A transparent sum of five numbers that are *always reported individually
alongside it* is fully inspectable by construction. The score file (§5)
always includes all five raw scores per side, both totals, and the winner
together; the total is never printed alone.

**Tie-break, in order:**
1. Higher total wins.
2. If totals are equal, higher `steelman_fidelity` score wins (ADR-002 calls
   this "the explicit tiebreaker").
3. If `steelman_fidelity` is also equal, the result is an explicit **draw**,
   not an arbitrary tiebreak. A confident-looking forced verdict the
   evidence doesn't support is the same dishonesty the hard invariant
   already refuses for a one-sided debate.

### 4. Evidence grounding degrades gracefully when Prep didn't run

`prep` is optional (ADR-007 §4, ADR-010 §2). Scoring `evidence_grounding`
has two modes, and the score file states which one applied via
**`prep_grounded`** (renamed from an earlier draft's `verified`, which read
as too close in meaning to `fact_check`, a different guarantee entirely —
`prep_grounded` checks a claim against the side's own recorded Prep
evidence; `fact_check`, wherever it ends up living, checks a claim against
the world):

- **`prep_grounded: true`** — Prep ran. The judge checks cited claims against
  that side's own recorded `evidence` (ADR-005/ADR-012). Real traceability.
- **`prep_grounded: false`** — Prep didn't run. The judge scores general
  argumentative rigor from its own knowledge, with nothing recorded to check
  against — a materially weaker guarantee, visibly labeled as such rather
  than looking identical to a verified score.

This is what lets B5 run in parallel with B4, as BUILD-GUIDE says: it
produces an honestly different, honestly labeled result depending on
whether Prep ran, rather than silently depending on it.

### 5. Score-file format

`judge transcript.json --model <model> --budget <n> --output score.json`
writes:

```jsonc
{
  "schema_version": 2,   // 2 adds the optional fact_check section, ADR-015 §4
  "debatebench_version": "0.1.0",
  "judged_at": "2026-09-12T10:00:00Z",
  "judge_model": "claude-sonnet-5",
  "judge_budget": 4000,
  "fact_check_enabled": true,   // when true, a "fact_check" section follows (ADR-015)
  "sides": [
    { "side_index": 0, "side": "pro", "dimensions": { /* §1 shape */ },
      "total": 76 },
    { "side_index": 1, "side": "con", "dimensions": { /* §1 shape */ },
      "total": 76 }
  ],
  "winner": "draw",
  "winner_reason": "tied_after_steelman_tiebreak"
}
```

`winner` is `"pro"`, `"con"`, or `"draw"`. `winner_reason` is one of
`"total"`, `"steelman_tiebreak"`, or `"tied_after_steelman_tiebreak"`.

## Why

The rubric's weights, the required winner, and "steelman fidelity is the
tiebreaker" all imply an aggregate, which reads as contradicting Hard Rule 3
until the rule's actual target is named precisely: it forbids the model
producing an opaque collapsed number, not a transparent arithmetic step
performed on the model's own separately-reported outputs, always shown
alongside them. The `prep_grounded` split is what actually reconciles B5
with BUILD-GUIDE's "can run parallel to B4": without it, evidence grounding
scored against Prep evidence would make B5 silently depend on B4 existing.

## Consequences

- **B5's scope is fully specified**: the five-field schema, the one-call
  structure with a required `--budget`, the orchestrator-side aggregation
  and tie-break logic, `prep_grounded`, and the score-file format above.
- **ADR-007 §1 is amended**: `judge`'s flags are now `--model`, `--budget`,
  `--output` (all required), `--base-url` (optional), `--fact-check`/
  `--no-fact-check` (default on).
- **B5's exit gate** needs three transcripts, not one: a deliberately
  lopsided one, a genuinely close one that exercises the steelman tiebreak
  (including an actual `"draw"`), and one with no `prep` in its phase list
  (exercises `prep_grounded: false`).
- **A parse failure on any dimension aborts the judging run**, consistent
  with `debate`'s Hard Rule 1 behavior, rather than a partial or
  zero-filled score file.
- OPEN-QUESTIONS item 2 is resolved.

## What this ADR does not do

**This makes B5 buildable. It does not make its scores trustworthy.** Item 6
in OPEN-QUESTIONS, correlating a candidate judge's scores against real human
ratings (`ibm-research/argument_quality_ranking_30k`, `debate_speeches`), is
completely untouched by this decision and remains fully open. The
three-transcript exit gate above tests that the *mechanism* works, code
paths, aggregation, tie-breaking, the two `prep_grounded` modes, it says
nothing about whether the judge's actual scores track human judgment. B7
stays blocked on item 6 regardless of B5 being done.

## Open questions this doesn't resolve

- Item 6 (see above) — unaffected, still fully open.
- Whether the fallacy-detector or stance-consistency checks (ADR-002, still
  open) become additional dimensions here or stay separate fast passes.
- The exact prompt/instructions given to the judge model for scoring each
  dimension — B5's to write, within the shape this ADR fixes.

