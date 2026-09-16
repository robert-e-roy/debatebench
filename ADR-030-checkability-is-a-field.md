# ADR-030: The Checkability Question Is a Field the Model Must Answer, Not a Verdict It May Reach

**Status:** Accepted, and its mechanism (§1–§4) **measured and REVERTED** on
2026-09-16. §7's prediction was wrong on all three counts; the result and what it
teaches are in §9, which is the part of this ADR worth reading.
**Date:** 2026-09-16
**Depends on:** ADR-015 §2 (the four verdicts), ADR-019 (contradiction wins),
ADR-024 §2 (checkability gates the other three verdicts), ADR-013 §5 (the score
file), Hard Rule 1
**Amends:** ADR-024 §4 ("no code enforcement") — see §6. ADR-024 §2 is
unchanged; this implements it.
**Implements:** ADR-024 §2 as schema rather than prose, which `probe/b6/README.md`
and `CLAUDE.md` both name as the remaining option.

## Context — the target is one model, two assertions, and it is the validated one

B6's gate asks for all three fact-check clauses in one ledger. The framing this
project has carried since 2026-09-15 is "nothing has produced all three; every
working judge returns exactly two." That is true, and it is the wrong unit of
analysis for choosing a fix, because the two missing clauses have different
causes.

**`qwen3:8b` warm is two verdicts short of the entire gate.** Its baseline
ledger (`probe/b6/baseline-a-d2.json`) is 20 claims: 15 `supported`, **3
`contradicted`** — all cross-side — and 2 `unsupported`, which are:

- "Rural renewable energy investment **can** offset fossil fuel reliance"
- "The CON's focus on leakage **overlooks climate urgency**"

A prediction and a value judgement: ADR-015 §2's `not_checkable` categories,
verbatim. Move those two and `qwen3:8b` warm has clauses (1), (2) and (3) in one
ledger. It is also the **only judge whose ordering is validated** — Tau-C +0.547
over 631 speeches, and `MODEL-COVERAGE.md` warns that result does not transfer
across models or generations.

**`qwen3:14b`'s missing clause is a different defect and this ADR does not
address it.** Checked before choosing a fix, in `probe/b6/ladder-qwen3-14b.json`:
14b lists *both halves* of the known contradiction pair as separate claims and
marks each `supported`, citing `am-3` and `am-4` correctly.

| side | claim | cited | verdict |
|---|---|---|---|
| 0 | dividend "turns a regressive tax into a progressive" one | `am-3` | `supported` |
| 1 | "A carbon tax is regressive before any rebate arrives" | `am-4` | `supported` |

Its citation mechanics are exact. What it never does is weigh a claim against the
*opposing* side's passage — an ADR-019 precedence failure, reappearing on a model
ADR-019 was never measured on. **No amount of checkability schema fixes that**,
and pointing this change at 14b would be aiming it at the wrong defect.

So: the target is `qwen3:8b` warm, named before the measurement.

## The reason to be suspicious of this change

Two previous attempts to make this model answer the checkability question
earlier both failed, and both failed the same way:

| condition | change | `not_checkable` | collateral |
|---|---|---|---|
| B (ADR-024 §3) | `not_checkable` listed first | **0** | lost all 3 cross-side `contradicted` |
| C | user turn rewritten toward checkability | **0** | warm ledger 20 claims → 5 |

A `factual` field is a third attempt at the same goal. This ADR has to say why
it is not a third instance of the same move, and say it in advance.

**It is a different mechanism, and the difference is that the competition is
removed rather than reordered.** B and C changed what the model *reads* and hoped
that would change what it *writes*; the four verdicts stayed in one list, and
`unsupported` — "it **is** a factual claim, but nothing bears on it" — remained
available as a satisfying answer reachable without the checkability question ever
being posed. Under this change the model never chooses between `unsupported` and
`not_checkable`: it answers a boolean, and the verdict list it is then shown
contains only the three factual verdicts. The question cannot be skipped by
arriving at an adjacent verdict first, because there is no adjacent verdict.

That is an argument, not a result. §7 states what would falsify it.

## Decision

### 1. Every claim carries a required `factual` boolean, before its verdict

```json
{"turn": 3, "claim": "what was asserted", "factual": true,
 "verdict": "supported", "evidence_ids": ["am-1"]}

{"turn": 5, "claim": "an opinion about the opponent", "factual": false}
```

`factual: false` means the assertion is an opinion, a prediction or a value
judgement — ADR-015 §2's three categories, unchanged. It takes no verdict and no
ids.

### 2. `not_checkable` is derived from `factual: false`, never chosen

The code sets the verdict and clears the citations. This is a derivation rule,
not a validation: a verdict supplied alongside `factual: false` is discarded
rather than argued with, because the model cannot be told how to resolve a
disagreement with itself and aborting a whole run over one would be worse than
either answer.

The model is no longer offered `not_checkable` as a verdict at all. It is still
a legal stored value — it is what §2 derives, and the prep-less degradation path
(ADR-015 §2) still produces it for every claim.

### 3. `factual: true` faces exactly the three verdicts it faced before

`supported`, `contradicted`, `unsupported`, **in that order**, with ADR-019's
precedence unchanged and its `CONTRADICTION WINS` block untouched. Condition B
demonstrated that disturbing this order costs the cross-side contradictions, so
it is not disturbed. `factual: true` with `verdict: "not_checkable"` is a parse
error naming both fields, since that combination is the model contradicting
itself in a way it can fix.

### 4. A missing `factual` is a parse failure

Hard Rule 1. The field is the whole change; a reply without it has not answered
the question, and silently defaulting it would reintroduce exactly the
"`unsupported` is always defensible" gap ADR-024 diagnosed.

This breaks the reply shape every previously recorded ledger was produced under.
Those artifacts stay as they are and are **not re-run**; the comparison baseline
is condition A as committed, which is what the amended B6 protocol compares
against anyway.

### 5. No `schema_version` bump — the stored shape does not change

`factual: false` and `verdict: "not_checkable"` are the same statement, so the
boolean is recoverable from the verdict and storing it would record one fact
twice. `Claim`, the score file and `SCORE_SCHEMA_VERSION` are untouched. This is
the same reasoning ADR-023 §4 used: the shape is unchanged, only how a value is
arrived at.

The change is therefore confined to the **request/reply contract with the
model** — `build_fact_check_request` and `parse_claims` — and is invisible to
anything reading a score file.

### 6. The code now enforces that the question was answered — which is not what §4 denied

ADR-024 §4 said "nothing in the code can tell an opinion from a fact, which is
the whole reason the question is put to the model." **That remains exactly
true** and nothing here changes it: the classification is still entirely the
model's, and `_validate_claim` still cannot inspect an assertion's content.

What the code can now do is require *that an answer was given*, and reject a
reply whose two answers contradict each other. That is a claim about the reply's
structure, not about the world, and it is the only kind of enforcement available
at this seam. ADR-024 §4 is amended to say so rather than reversed.

### 7. The prediction, and what would falsify it

Stated before the measurement, because with conditions B and C in the record a
result read afterwards could be rationalised either way.

**Predicted**, on `qwen3:8b` warm against `probe/b6/transcript-2026-09-14-gate.json`:

1. The two assertions above become `not_checkable` — clause (3) fires.
2. The **three cross-side `contradicted` verdicts survive** — clause (2) holds.
3. The ledger stays near 20 claims; it does not collapse the way condition C's did.

**All three are required.** ADR-024 §5 already fixed this standard: a change that
wins clause (3) by losing clause (2) is a regression and is reverted, as B and C
were. A shrunken ledger is the condition-C failure and counts the same way.

### 8. Measured under the amended B6 protocol, artifacts first

Two draws per load state, cold and warm, on the saved gate transcript. Same-state
draws must be byte-identical — the protocol's self-test, which has passed on four
models — or the run is not interpretable and nothing is concluded from it.

The artifacts are committed **before** the verdict is written into this ADR,
`probe/b6/README.md`, `BUILD-GUIDE.md` or `CLAUDE.md`. The three reverted
conditions are in this repository because that order was followed; the two
withdrawn claims on this gate happened when it was not.

## Why

**Because it is the only lever left that is not wording.** Three prompt
conditions have been written and reverted against a defect that moves with the
judge. `probe/b6/README.md`'s own conclusion is that no wording can make one
model do what another does — which is an argument for changing what the reply
must *contain*, not how the instructions are phrased.

**Because the gap is two assertions on the one judge whose scoring is
validated.** Every other candidate either lacks a validated ordering or is
missing clause (2) for an unrelated reason.

## Consequences

- **`build_fact_check_request` and `parse_claims` change.** Nothing else in the
  pipeline does; `debate` is untouched.
- **ADR-024 §4 is amended** (§6), not reversed.
- **Every existing fact-check test that scripts a reply needs the new field**,
  which is the correct blast radius for a change to the reply contract.
- **The prep-less path is unchanged**: with nothing recorded, every claim is
  still forced to `not_checkable` with its note, regardless of `factual`.
- **A judge that cannot emit a boolean now fails loudly** rather than returning a
  ledger with the question unanswered. On the evidence so far that is the
  0.6b/1.7b models, which already return one claim and cannot do the task.

## 9. Measured 2026-09-16 — falsified on all three counts, and reverted

Four draws, two per load state, `qwen3:8b`, budget 6000, against the saved gate
transcript. Artifacts committed before this section was written
(`probe/b6/adr030-*.json`, commit `f787447`).

| draw | claims | supported | contradicted | unsupported | `not_checkable` | hash |
|---|---|---|---|---|---|---|
| cold ×2 | 16 | 13 | **0** | 3 | **0** | `873a3c47aeee8f64` |
| warm ×2 | 16 | 13 | **0** | 3 | **0** | `873a3c47aeee8f64` |
| **baseline warm** | **20** | 15 | **3** | 2 | 0 | `36859fa6f7798c1c` |

Against §7's three requirements:

1. **Clause (3) did not fire.** Zero `not_checkable`, which is what the change
   existed to produce.
2. **Clause (2) was lost.** All three cross-side `contradicted` verdicts gone —
   the regression ADR-024 §5 named in advance.
3. **The ledger shrank**, 20 claims to 16.

**What actually happened to the two target assertions is the finding.** The
value judgement — "the CON's focus on leakage overlooks climate urgency" — was
not reclassified. It **disappeared from the ledger entirely**. The prediction —
"can offset fossil fuel reliance" — stayed `unsupported`. And of the three lost
contradictions, one became `supported` **citing the speaker's own passage**
while two dropped out of the ledger.

So a required `factual` field made this model *list less* and *look across sides
less*, which is precisely what conditions B and C did. Being forced to answer
"is this factual?" for every assertion appears to be read as licence to drop the
assertions that are not, despite the prompt saying the opposite two lines
earlier.

### What three failures through three channels are worth

This is now a replicated result rather than an anecdote. **On `qwen3:8b`, every
change that foregrounds the checkability question trades away clause (2) and
shrinks the ledger** — through verdict-list order (B), through user-turn framing
(C), and now through a required schema field, which is the strongest channel
available and the one §"The reason to be suspicious" argued should escape. It
did not.

The argument in that section — that removing the competition differs from
reordering it — was reasonable and is wrong. It is left in place above, unedited,
because the prediction being legible is the only thing that makes this reading
possible.

**The honest conclusion is that clause (3) is not reachable on `qwen3:8b` by
changing what we ask for.** Three channels, three failures, same shape. `qwen3:4b`
and `qwen3:14b` produce it unprompted on the same transcript. The variable is the
judge, which is what `probe/b6/README.md` concluded before this ADR was written
and what this ADR did not manage to overturn.

### One genuinely new thing: the state sensitivity vanished

Baseline `qwen3:8b` is the model this project's determinism note is built on —
cold gives 11 claims, warm gives 20, and which one you get depends on whether the
model was resident. **Under this change all four draws are byte-identical across
the cold/warm boundary**: 16 claims either way, one hash.

That is the first time `qwen3:8b` has been state-insensitive on this transcript.
It does not rescue the change, but it is a real, reproducible effect of it, and
it bears on CLAUDE.md's determinism claim — which is already flagged as measured
on `qwen3:8b` and not general. Whether a mandatory boolean is what removed the
state sensitivity, or whether any sufficiently constraining reply shape would,
is untested.

### What is reverted and what is kept

- **Reverted:** §1–§4 in full — `build_fact_check_request`, `parse_claims`, the
  `_CLAIM_SHAPE`, and the seven tests that pinned the contract. The wire shape is
  back to four verdicts in one list.
- **Kept:** the artifacts, this section, and §"Context"'s two premise checks,
  neither of which the measurement touched — `qwen3:8b` warm is still two
  verdicts from the gate, and `qwen3:14b`'s cross-side blindness is still an
  uninvestigated ADR-019 failure on an unmeasured model.
- **ADR-024 §4 stands unamended.** §6 proposed amending it; with §1–§4 reverted
  there is no code enforcement to justify the amendment, so the original text —
  "nothing in the code can tell an opinion from a fact" — is untouched.

## Open questions this doesn't resolve

- **`qwen3:14b`'s cross-side blindness**, newly characterised above: it cites
  correctly and never compares across sides. That is ADR-019's problem on a model
  ADR-019 was not measured on, and it needs its own investigation. It is now the
  most promising route to the gate left, since 14b already produces clause (3)
  stably in both states and needs only clause (2).
- **Why a mandatory field made the model drop assertions**, when the prompt
  directly above it says "Filter nothing out". Three conditions have now produced
  a smaller ledger; none has explained the mechanism.
- **Whether a constraining reply shape removes load-state sensitivity in
  general**, or whether that was specific to this one (§9).
- Whether `factual` should also be asked of the *scoring* pass, where
  `evidence_grounding` has the same latent question.
- Whether a prediction is non-factual in the sense that matters — ADR-024's open
  question, untouched and now load-bearing for a field rather than a verdict.
