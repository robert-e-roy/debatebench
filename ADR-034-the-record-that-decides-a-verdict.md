# ADR-034: A Verdict Is Decided Against the Retrieved Passages; Turns Are Context

**Status:** Accepted
**Date:** 2026-09-18
**Depends on:** ADR-015 §2 (what the pass checks against), ADR-019 (contradiction
outranks a backing passage), ADR-002 ("Judge design", the hit ledger), ADR-017 §3
(the hit-ledger vocabulary), ADR-013 §4 (`rebuttal_effectiveness`)
**Amends:** ADR-015 §2 — "and what either side said", for the purpose of
*deciding a verdict*
**Resolves:** OPEN-QUESTIONS 16

## Context — one job, two mechanisms, and an uncheckable citation

ADR-015 §2 says the fact-check judges against "the passages each side retrieved,
**and what either side said**". B6's gate clause (2) asks for something narrower:
a claim contradicted by the opponent's *recorded evidence*, **citing that
passage**. Only passages have ids, so a contradiction the judge found in a *turn*
gets a topically-related passage id attached, and nothing verifies the cited
passage is what did the contradicting.

Measured (`probe/b6/`):

- Adding the opponent's turn text to a passage flips three of four model/pair
  cells from NO to YES, with reasons that name the turn — "the record *argues*
  that…".
- Asked about the **cited passage alone**, all four models tested reject two of
  the three contradictions `qwen3:8b` reports — including `qwen3:8b` itself.
- Under `phi4:14b`, the same test returned one confirmed, one contested, one
  false positive.

So the citation is unfalsifiable, which `_evidence_citations`'s own comment calls
"exactly what this pass exists to avoid".

## The argument that decides it

**In an adversarial debate, "the opponent's turn contradicts this claim" is true
by construction.** The tool exists to produce sustained opposing positions
(ADR-002); a con turn opposing a pro claim is the debate working, not a finding.
Admitting turns as a basis for `contradicted` therefore makes the verdict
approach vacuous on a contested motion — every assertion has an opposing turn
somewhere. That is precisely the pattern the isolation test exposed: those were
not contradictions of fact, they were the debate happening.

**And the thing that would be lost already has a better home.** ADR-002 designed
a **structured hit ledger** — `open` / `conceded` / `rebutted` / `dodged` per
point — for argument-versus-argument engagement, and ADR-017 §3 fixed its
vocabulary. It lives in `rebuttal_effectiveness`, where a rebuttal belongs.
Item 16's confusion is two mechanisms doing one job: the hit ledger already
records whether an argument was answered, and the fact-check was quietly
duplicating it in a field that cannot express it.

## Decision

### 1. A verdict is decided against the retrieved passages, and only those

- **`supported`** — a retrieved passage backs it, and none contradicts it.
- **`contradicted`** — a retrieved passage contradicts it (ADR-019's precedence
  unchanged, now operating over passages only).
- **`unsupported`** — it is a factual claim and **no retrieved passage** bears on
  it either way. A claim the opponent merely *argued against* is `unsupported`.
- **`not_checkable`** — not a factual claim at all (ADR-024 §2 unchanged).

Every citing verdict therefore names the passage that decided it, and a reader
can check that passage against that claim. That is the whole point of the pass.

### 2. Turns remain context, and are still read

The judge still sees every turn, and must: to know what a claim *means*, to
attribute it to the turn that made it, and to extract it at all. **Turns inform
what the claim is; passages decide what the verdict is.** This is a narrowing of
what may *justify* a verdict, not of what the judge may read.

### 3. Argument-versus-argument stays where it was designed to go

A point the opponent answered is `rebutted` in the hit ledger; one they ignored
is `dodged`; one still standing is `open`. Nothing is lost by keeping the
fact-check to evidence — it is recorded in the dimension built for it, by a
vocabulary chosen for it, and scored under `rebuttal_effectiveness`.

### 4. No schema change, and no `schema_version` bump

`VERDICTS` is unchanged, the claim shape is unchanged, the score file is
unchanged. What changes is **which verdict a given assertion earns** and what the
prompt says. Same reasoning as ADR-023 §4: the shape is unchanged, only which
values occur.

The code already implements the narrow reading — `_evidence_citations` has always
required ids of *recorded passages*, because those are the only ids there are.
**It is the specification and the prompt that were broad.** This ADR makes the
three agree.

### 5. B6 clause (2) is not met on the saved gate transcript

Under §1, a `contradicted` verdict whose cited passage does not contradict the
claim is simply wrong. The isolation test says two of `qwen3:8b`'s three fail
that check. So clause (2)'s "met and reproducible" status from 2026-09-14 is
**withdrawn for that transcript**, not merely unsettled.

This does not reopen B6. ADR-031 re-specified the gate around a well-formed,
structurally checkable ledger and explicitly stopped claiming the verdicts are
correct; §5 is that decision being consistent rather than a new failure.

## Why

**Because a citation nobody can check is worse than no citation.** It reads as
evidence and is not, which is a stronger claim than the tool can support and the
exact failure the fact-check was built to prevent.

**Because the alternative makes the verdict vacuous.** If an opposing turn
counts, every claim in a real debate is contradicted, and the verdict stops
carrying information.

**Because nothing is lost.** The hit ledger has recorded argument engagement
since ADR-002, in a vocabulary chosen for it.

## Consequences

- **`build_fact_check_request` changes**: the prompt says verdicts are decided
  against the passages, and names turns as context.
- **Expect fewer `contradicted` and more `unsupported`.** That is the intended
  direction: a claim only the opponent *argued* against was never evidentially
  contradicted.
- **ADR-015 §2 is amended** for verdict-deciding; its "checked against the
  record, not the world" principle is untouched and is what this sharpens.
- **ADR-019 is unaffected** — precedence between `supported` and `contradicted`
  is unchanged; it now ranges over passages only.
- **The gate clause and the definition agree** for the first time.
- **Measured before believed**, per this project's standing practice: the
  artifacts are committed before any verdict is written into this ADR.

## Open questions this doesn't resolve

- Whether `rebuttal_effectiveness`'s hit ledger is *good* at what it is now
  solely responsible for. It has never been validated (OPEN-QUESTIONS 6).
- Whether a claim contradicted by a passage **the claimant's own side
  retrieved** should read differently from one contradicted by the opponent's.
  ADR-019 says the verdict is the same; the gate clause cares about the
  difference, and nothing records which it was.
