# ADR-031: B6 Closes on a Re-Specified Gate, and Verdict Accuracy Moves to Validation

**Status:** Accepted
**Date:** 2026-09-16
**Depends on:** ADR-015 (the pass and its verdicts), ADR-019, ADR-024, ADR-030
(all three measured), OPEN-QUESTIONS 6 (the validation track), OPEN-QUESTIONS 16
(what "the record" means)
**Supersedes:** BUILD-GUIDE B6's three-clause exit gate and both of its
measurement protocols (N=5, then two draws per load state)

## Context — the gate asked a validation question in a build gate's clothes

B6's gate has stood unmet since 2026-09-13. Its three clauses ask for a
`supported` citing the speaker's own passage, a `contradicted` citing the
opponent's, and a `not_checkable` on an opinion — **all three in one ledger from
one judge**.

Everything measured since says that conjunction is not a property of the pass:

- **Clause (3) is a property of the judge, not the prompt.** `qwen3:4b` and
  `qwen3:14b` produce it unprompted on the gate transcript; `qwen3:8b` never has,
  in 29 draws. Three interventions — verdict-list order (condition B), user-turn
  framing (condition C), and a required `factual` field in the reply schema
  (ADR-030) — were each predicted, measured and reverted. All three produced zero
  `not_checkable` *and* cost clause (2).
- **Clause (2) is not well defined.** ADR-015 §2 judges against "the passages each
  side retrieved, **and what either side said**"; the gate demands a citation
  pointing at the opponent's *passage*. A contradiction found in a turn can
  satisfy one or the other, never both. Measured 2026-09-16: asked about the cited
  passage alone, all four models tested — **including `qwen3:8b` itself** — reject
  two of the three contradictions `qwen3:8b` reports in its audit. This is
  OPEN-QUESTIONS 16, a specification defect no run can resolve.
- **Seven judges, and every one that works returns exactly two clauses.** Which
  two varies by model *and by generation*: `qwen3:4b` and `qwen3.5:4b`, identical
  parameter counts, return opposite pairs.

The diagnosis is structural. **B5 gated the scoring pass as a mechanism and left
its accuracy to OPEN-QUESTIONS 6 and `JUDGE-VALIDATION.md`.** B6's gate tried to
do both at once: it is written as a build gate but its clauses assert that
particular verdicts are *correct*, which is a validation claim about a model. No
amount of building satisfies it, and four interventions across three channels are
what that looks like from the inside.

## Decision

### 1. B6's exit gate is re-specified, and B6 closes

The three-clause conjunction is retired, with both measurement protocols it
carried. The new gate has **one testable condition** and three recorded findings,
because a gate whose every clause is retrospectively true is a rubber stamp
however good its reasoning.

### 2. The gate: the pass produces a well-formed, checkable-in-shape ledger

This is the condition, and a future change can break it:

- every claim maps to a turn the transcript actually contains, by the turn number
  the rendering prints;
- every cited id is one the transcript recorded — an invented id fails the run;
- `supported` and `contradicted` cite at least one id, `unsupported` and
  `not_checkable` cite none;
- the reply's verdict vocabulary is exactly ADR-015 §2's four, and anything else
  fails;
- the audit is a second backend call capped by `--budget` on its own, enforced
  with ADR-010 §3's tolerance;
- a malformed reply fails loudly and **carries the offending text** rather than
  a bare line/column, naming a repair where one is known (ADR-026), instead of
  being silently dropped or retried;
- a transcript with no recorded evidence degrades to all-`not_checkable` with a
  note, rather than inventing citations.

**Met**, pinned against the scripted backend by `tests/test_fact_check.py` and,
for the malformed-reply clause, `tests/test_judging.py`; and demonstrated live
across seven judges whose artifacts are in `probe/b6/`. Each clause was checked
against a named test before this was written, rather than asserted from
memory.

### 3. Recorded as findings, not as gate conditions

- **Every verdict in the vocabulary has been observed on a real model**:
  `supported`, `contradicted` and `unsupported` on `qwen3:8b` warm;
  `not_checkable` on `qwen3:4b` and `qwen3:14b`; all-`not_checkable` on the
  prep-less path.
- **Clause coverage varies by judge and by generation**, and which verdicts a
  given judge produces is documented per model in `MODEL-COVERAGE.md` with the
  artifact behind each.
- **The known defects are written down rather than hidden**: `contradicted`
  citations are not verified to name the passage that actually contradicts
  (OPEN-QUESTIONS 16); coverage is model-dependent; no accuracy validation
  exists.

### 4. What B6 no longer claims

Stated plainly, because the rewrite gives something up and a reader should be
able to see exactly what.

The old gate asserted that the pass **finds a claim contradicted by the
opponent's recorded evidence, and cites that evidence** — described there as
"the finding `prep_grounded` alone can never produce, and the reason the pass
exists". **That assertion is withdrawn.** B6 no longer claims:

- that the audit's verdicts are correct;
- that a `contradicted` verdict's citation names what contradicted the claim;
- that any single judge produces the full range of verdicts on a given
  transcript.

What B6 claims is that the pass runs, that its output is well formed and
structurally checkable, that it fails loudly when it cannot be, and that what
each judge actually produces is documented.

### 5. Verdict accuracy moves to the validation track, under OPEN-QUESTIONS 6

Not a new open question — OPEN-QUESTIONS 6 is already "no build session validates
the judge" and already records that only `qwen3:8b`'s *ordering* passes. The
fact-check is the same judge's second pass and belongs there, as a clause saying
its accuracy is unvalidated and what would be needed to validate it.

Nothing in `JUDGE-VALIDATION.md`'s Tau-C result bears on the fact-check: that
statistic measures rank correlation on scoring, and the audit produces a ledger
of categorical verdicts.

### 6. The B6 protocol artifacts stay

Every ledger, every reverted condition, the state test, the ladder, the four-model
spread and the citation probes stay in `probe/b6/`. They are the evidence for §3
and for four falsified hypotheses, and the write-ups record what each predicted
before it ran.

## Why

**Because the gate could not be satisfied by building, and building is what a
build gate tests.** Four interventions, three channels, seven judges, two
generations. Each was predicted in advance, measured under a pre-registered
protocol and reverted on the result — that is the process working, and the answer
it produced is that the target was misspecified.

**Because the project already separates these questions everywhere else.** B5
gated a mechanism; `JUDGE-VALIDATION.md` and OPEN-QUESTIONS 6 carry whether its
output is any good. B6 is the only session that tried to gate a model's judgement
as though it were a feature.

**Because an honest unmet gate that never closes is worse than a narrower one that
does.** The pass ships, on by default, and the README tells users what it does not
do. That disclosure is the thing that has to be right, and it is more useful than
a gate status nobody outside the repo can see.

## Consequences

- **BUILD-GUIDE B6 is rewritten**: new gate, and both retired protocols kept as
  dated historical blocks rather than deleted — including the withdrawn "the
  audit is not reproducible" premise the N=5 standard was built on, which is left
  visible with its correction beside it.
- **B0–B7 are now all closed.** No build session remains open.
- **The README's `--fact-check` note is rewritten.** Its current text says the
  claims the audit does list "have been accurate, including ones contradicting
  the opponent's own recorded evidence" — the specific sentence the four-model
  spread undercuts. It is user-facing and wrong, and the repo copy is corrected
  here. Whether that warrants a patch release is a separate decision.
- **OPEN-QUESTIONS 6 gains a fact-check clause**; no new item is created.
- **OPEN-QUESTIONS 16 stays open and is now the substantive one**: until "the
  record" means one thing, a `contradicted` verdict cannot be checked.

## What would reopen this

A judge that produces all four verdicts on one transcript with citations that
survive the isolation test in `probe/b6/README.md`. Nothing tested does. If one
appears, the finding belongs in `MODEL-COVERAGE.md`, and the question of whether
the gate should have been harder can be asked again then.
