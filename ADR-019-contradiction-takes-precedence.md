# ADR-019: Contradiction Takes Precedence in the Claims Ledger

**Status:** Accepted
**Date:** 2026-09-14
**Depends on:** ADR-015 (§2 the verdict vocabulary, §4 the score-file section),
ADR-013 (§4 `prep_grounded`, §5 score-file format), ADR-008 (two runtime
dependencies), ADR-004 (live tests opt-in)
**Amends:** ADR-015 §2 — the definitions of `supported` and `contradicted`
**Resolves:** the reason B6's exit gate was unreachable on a two-sided corpus

## Context — a gate that could not be met as written

ADR-015 §2 defines two verdicts by the same test, on the same evidence pool:

- `supported` — a recorded passage (either side's) **backs** it.
- `contradicted` — a recorded passage (either side's) **contradicts** it.

`verdict` is single-valued, and **no rule anywhere said which wins when both
are true.** Grepping ADR-015, ADR-013 and `judging.py` for a precedence rule
returned nothing.

On a real debate this is not an edge case, it is the normal case. A contested
motion is precisely where both sides retrieve passages bearing on the same
point. Measured on the B6/B7 fixture pools, *every* on-topic passage pair is a
two-sided disagreement:

| bears on | pro | con |
|---|---|---|
| incidence of the tax | `am-3` recycling "turns a regressive tax into a progressive transfer" | `am-4` regressive "before any rebate arrives … reimbursed last" |
| whether it cuts emissions | `am-1`, `ds-1` | `am-5`, `am-6` (leakage, unworkable border adjustments) |
| predictability for firms | `am-2` a price firms can plan around | `ds-2` every tax so far arrived with exemptions |

So any claim a passage contradicts is also a claim some passage backs, and
`supported` was a defensible reading every time. In the 2026-09-14 gate run the
judge returned **17 `supported`, 1 `not_checkable`, 0 `contradicted`** on 18
claims. Claim 14 — the PRO asserting its revenue-sharing "neutralizes
regressive impacts" — is exactly the shape B6 clause (2) asks for, and came
back `supported` citing `am-3`. That was not a model error. It was the ADR
being ambiguous and the model picking one of two permitted answers.

## Decision

### 1. Contradiction wins

**If any recorded passage contradicts a claim, the verdict is `contradicted`,
even when another recorded passage backs it.** `supported` therefore narrows
to mean *backed by the record and contradicted by nothing in it* — uncontested.

The four verdicts, restated in full, replacing ADR-015 §2's list:

- **`supported`** — a recorded passage backs it, and **no** recorded passage
  contradicts it.
- **`contradicted`** — a recorded passage contradicts it. This wins over
  `supported`.
- **`unsupported`** — it is a factual claim, but nothing recorded bears on it
  either way.
- **`not_checkable`** — an opinion, prediction, or value judgement.

### 2. `evidence_ids` cites the passage that decided the verdict

For `contradicted`, cite the **contradicting** passage, not the backing one.

The flat list in ADR-015 §4 is unchanged and stays flat. Citing both would be
ambiguous — nothing in a list of ids marks which refutes and which backs — and
`_evidence_citations` would accept the mixture silently, since it validates
only that an id was recorded. One verdict, one kind of citation.

### 3. This is a prompt rule, not an enforced invariant — stated plainly

**Nothing in the code can check it.** Deciding whether a passage backs or
refutes a claim is entailment; the only tools for that are a model or a
classifier, and ADR-008 fixes the runtime at `httpx` + PyYAML (ADR-015's own
"Prior art considered" already rejected MiniCheck on exactly this ground).
`_evidence_citations` verifies that cited ids were actually recorded and that
the citation pattern matches the verdict — nothing more, and it cannot be made
to do more without a new dependency.

So §1 is an instruction in the audit prompt that a model may disregard, and the
ledger is only as reliable as the judge. This is written down rather than
implied, because a precedence rule that looked enforced would be the
confident-looking, unauditable check this project has refused everywhere else.

### 4. No `schema_version` bump, and why the meaning still changed

The score file's shape is unchanged: same keys, same flat `evidence_ids`,
`schema_version` stays **2**. ADR-016 §6's precedent bumps the version on a
change to the document's *shape*, and this is not one.

**But the meaning of `supported` has changed**, and that is a real
discontinuity: a score file written before 2026-09-14 and one written after can
disagree about the same debate, with no field distinguishing them. Anyone
comparing ledgers across that date must know it. The alternative — bumping the
version for a semantic change — would make `schema_version` mean two different
things, which is worse.

## Why

The pass exists to surface what `prep_grounded` cannot: ADR-015 §2 says so
outright, "side A's claim contradicted by side B's recorded passage is a
finding `prep_grounded` can't produce". A ledger that marks a contested claim
`supported` because the speaker's own evidence agrees with it reports the least
interesting half of the record, and hides the exact finding the pass was built
for.

`debatebench` exists to show where an argument fails to survive contact with a
good opponent. "Both sides retrieved evidence and they disagree" is the
substance of a debate, not noise to be resolved in the speaker's favour.

The rejected alternatives, and why:

- **A fifth verdict (`contested`), or per-id polarity.** Most faithful to what
  is actually true of claim 14 — but it is a score-file shape change, a
  `schema_version` bump, and an addition to ADR-013's vocabulary, for a
  distinction §1 already captures at the cost of one bit of nuance.
- **Changing the fixtures so an uncontested contradiction exists.** Smallest
  blast radius, and it would have closed B6's gate today. Rejected because it
  makes the gate pass without making the tool better — arranging the test to
  pass is the move this project refuses (see ADR-015's `response_format` note
  and BACKEND-PROBE-RESULTS' refusal to drop a row).

## Consequences

- **ADR-015 §2 amended**: the verdict list is replaced by §1 above. Everything
  else in ADR-015 — the record-not-the-world scope, the second call, the
  score-file section, the no-evidence degradation — stands unchanged.
- **The audit prompt** (`build_fact_check_request`) states the precedence rule
  and the narrowed meaning of `supported`.
- **Ledgers change meaning, not shape.** Claims previously `supported` may now
  be `contradicted`. Expect the `supported` count to fall on any two-sided
  corpus.
- **BUILD-GUIDE B6's exit gate is now reachable** without weakening it. Its
  three checks are unchanged.
- **No test asserts the model obeys this.** It cannot be tested with a scripted
  backend — a fake returns whatever it is told to — and asserting it against a
  live model would make the default suite non-deterministic, which ADR-004
  forbids. Parse-side behaviour is tested; obedience is measured by the live
  gate, and recorded in `probe/b6/`.
- **`CLAUDE.md`** ADR list gains this entry.

## Open questions this doesn't resolve

- **Whether the judge obeys it.** That is the live B6 gate, and this ADR makes
  it answerable rather than answering it.
- **Whether `unsupported` needs the same treatment.** A claim nothing bears on
  is unambiguous today, but if a passage were both irrelevant and refuting, the
  same collision would exist. No case has been observed; not decided here.
