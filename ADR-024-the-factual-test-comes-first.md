# ADR-024: The Fact-Check Asks "Is This Checkable?" Before It Asks "Is It Backed?"

**Status:** Accepted
**Date:** 2026-09-14
**Depends on:** ADR-015 (§2 the four verdicts), ADR-019 (precedence between
`supported` and `contradicted`), ADR-013 §4 (`prep_grounded`, the graded
dimension this ledger is not)
**Amends:** ADR-015 §2 — both its extraction clause and the ordering of its
verdicts

## Context — one clause of the gate has never fired

B6's exit gate has three checks. Clause (3) asks that a side's opinion or
prediction be recorded `not_checkable` rather than a false `unsupported`. Across
every post-ADR-019 run on record — seventeen on the saved gate transcript, in
both of the two states that transcript can produce — it has fired **zero**
times. Clauses (1) and (2) both fire; (2) fires in every warm run.

It is not a filtering failure. The opinions reach the ledger: the audit lists
"the CON's focus on leakage overlooks climate urgency" and records it
`unsupported`. One verdict over.

Two things in the spec explain why, and they pull in opposite directions.

**ADR-015 §2 contradicts itself about opinions.** Its extraction sentence says
the pass "extracts the factual claims it makes (not opinions or value
statements)". Its verdict list then defines `not_checkable` as "an opinion,
prediction, or value claim, not a factual one" — a verdict for the very things
extraction was told to drop. A third sentence in the same section settles which
half was meant: the judge's own knowledge "is used only to classify a claim as
factual or not", which presupposes that non-factual claims reach the
classifier. Implementation already resolved this the same way, in the prompt's
own words: *"Filter nothing out: an assertion that turns out not to be factual
is still listed."*

**The verdict list is ordered against the reader.** The prompt presents
`supported`, `contradicted`, `unsupported`, `not_checkable` — in that order.
A model working down it reaches `unsupported`, defined as "it **is** a factual
claim, but nothing recorded bears on it either way", before anything has asked
whether the claim is factual at all. The question that separates the last two
verdicts is never posed as a question; it is left implicit in a definition
three lines above the one that would answer it. ADR-019's `CONTRADICTION WINS`
block, the loudest text in the prompt, adds a further pull toward finding some
passage relationship for every assertion.

## Decision

### 1. The ledger carries every assertion, factual or not

ADR-015 §2's "(not opinions or value statements)" is struck. It was a drafting
slip that made `not_checkable` unreachable outside the prep-less degradation
path, and it contradicted both the same section's classifier sentence and the
gate written from it. The audit lists what a turn asserts; it does not pre-filter.

This is a wording correction, not a change of behaviour — the shipped prompt has
always said "Filter nothing out".

**That sentence was wrong when written, and is corrected here (2026-09-15).**
The *system* prompt said "Filter nothing out"; the *user* turn said "Audit this
debate's factual claims", pre-filtering from the last position the model reads.
The shipped prompt contradicted itself, and §1 described only the half that
agreed with it. Condition C rewrote the user turn and was reverted — it produced
no `not_checkable` either, and collapsed the warm ledger from 20 claims to 5.
The decision in §1 stands; the claim that the code already implemented it did
not.

### 2. Checkability is a gate on the other three verdicts, not a fourth sibling

The audit decides each assertion in two steps, in this order:

1. **Is this checkable against a record at all?** An opinion, a prediction, or
   a value judgement is not — ADR-015 §2's three categories, unchanged. Verdict
   `not_checkable`; cite nothing; stop.
2. **Only then**, for what remains: `contradicted` if any recorded passage
   contradicts it (ADR-019's precedence, unchanged), else `supported` if a
   passage backs it, else `unsupported`.

`unsupported` therefore means "factual, and the record is silent" — which is
what its definition always claimed and what the flat list never enforced.

### 3. `not_checkable` is listed first, and that change is tried on its own

The verdict list is reordered so the checkability question is the first one a
reader meets. **Whether that alone is enough is untested**, and this ADR does
not claim it is. It is the smallest edit that implements §2, it is applied by
itself, and it is measured before anything else is added (§5).

Held in reserve, to be tried only if the reorder fails: stating the two steps
as an explicit instruction above the list. Shipping both at once would make a
success uninterpretable — the reorder has never been run alone, and pairing it
with a second edit would forfeit the one clean reading available.

**Measured 2026-09-14, and the reorder is reverted.** Condition B, four draws
across both load states (`probe/b6/condition-b-*.json`): **zero
`not_checkable`** — the change produced none of what it existed for — and the
warm state lost all three cross-side `contradicted` verdicts, the regression §5
named in advance. Both ledgers also shrank. The order hypothesis is falsified,
and separating the two edits is what makes that statement possible.

§1 and §2 are unaffected: they are decisions about what the ledger holds and in
what order the questions are asked, and nothing measured bears on whether they
are right. What is now open is how to *express* them, given evidence that
leading with the checkability question makes the audit list less rather than
classify better. The reserve option above should not be assumed to escape
that — see `probe/b6/README.md`.

### 4. No code enforcement

Like ADR-019, this is a rule the prompt states and the model may disobey.
`_validate_claim` keeps doing what it does — checking the verdict vocabulary and
that `unsupported` and `not_checkable` cite nothing — and gains no new
authority. Nothing in the code can tell an opinion from a fact, which is the
whole reason the question is put to the model.

### 5. It is measured before it is believed

The change is tested under the amended B6 protocol: two draws per load state,
cold and warm, against the saved gate transcript, compared with the condition-A
baseline already committed. The audit is deterministic within a state, so a
change either moves the output or it does not — there is no favourable draw to
wait for.

A pass requires all three clauses in one ledger. A change that wins clause (3)
by losing clause (2) is a regression, and this ADR is not met by it — that trade
has been claimed once already on this gate and had to be withdrawn.

## Why

ADR-019 fixed the same shape of defect one verdict over: `supported` and
`contradicted` were given the same test with no precedence, so `supported` was
always defensible. Here `unsupported` and `not_checkable` are separated by a
question the prompt never tells the model to ask, so `unsupported` is always
defensible. The fix is the same fix — say which question comes first — and it is
worth noting that the first time this was diagnosed, the conclusion was that
the prompt needed to be *firmer*. It did not. It needed an order.

## Consequences

- **ADR-015 §2**: extraction clause struck (§1); verdicts become a two-step
  decision (§2). Amendment note added.
- **ADR-019** is unaffected. Its precedence still governs step 2, and its being
  the loudest text in the prompt is a reason to make step 1 louder, not to
  soften it.
- **`build_fact_check_request`** changes; `VERDICTS`, the score-file shape and
  `schema_version` do not.
- **The prep-less degradation path is untouched** — a transcript with no
  evidence still returns every claim `not_checkable` with its note (ADR-015 §2),
  and that remains a different thing from this decision.
- **BUILD-GUIDE B6** gains condition B.

## Open questions this doesn't resolve

- Whether a *prediction* is non-factual in the sense that matters. "Emissions
  will fall 14% by 2030" is checkable in principle and uncheckable against a
  transcript; this ADR puts it in `not_checkable` by way of step 1, which is a
  choice about what the ledger is for, not a fact about the claim.
- Whether `unsupported` and `not_checkable` should be distinguishable to a
  reader who only sees totals. Nothing aggregates them today.
