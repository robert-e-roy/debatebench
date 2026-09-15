# ADR-026: A Malformed Judge Reply Names Its Repair; the Tool Still Doesn't Retry

**Status:** Accepted
**Date:** 2026-09-15
**Depends on:** ADR-017 (§4 the parser's tolerances and its refusal of a retry
loop, §6 the reused seed), ADR-018 (Ollama's `response_format` support),
ADR-015 (the fact-check call, where replies break)
**Resolves:** OPEN-QUESTIONS 14, except its option 4, which is gated on a
measurement this ADR specifies rather than argues about

## Context — the question was built on a premise that turned out false

Item 14 was written as "a transcript the judge can't parse is permanently
unjudgeable". The reasoning: ADR-017 §6 sends `seed=transcript.run.seed`, so a
malformed reply reproduces byte-for-byte forever, and four attempts on one
transcript did reproduce the same fault at the same character offset.

That is true **within a model load state and not across one**. Seventeen
re-judgements of one transcript produced exactly two outputs, and a
pre-registered test confirmed the selector is whether the model was already
resident when the call arrived (`probe/b6/README.md`). The four attempts that
looked permanent were four attempts in one state.

Demonstrated end to end on 2026-09-15: the `probe/scale/` judge call failed with
malformed JSON, was re-run with **no seed change and no code change**, and
succeeded — scoring the debate 89 against 45.

The frequency is also no longer hypothetical. **Two of six judge calls in one
batch returned unparseable JSON**, a third of them, across both the scoring and
fact-check calls.

## Decision

### 1. The tool does not retry. ADR-017 §4 stands, and is now better supported

§4 refused a retry loop because "a retry would make a scoring run
non-deterministic and hide a model that can't produce the format, which is a
fact worth knowing about a candidate judge."

That reasoning has been vindicated in the strongest available way: **the 33%
failure rate above is only knowable because failures were visible.** A tool that
had been quietly retrying since B5 would have produced the same scores and hidden
the single most concrete reliability fact this project has about its judge.

So options 1 and 2 of item 14 are **declined**. Not because a retry could not be
made to work, but because the visible failure is carrying information the project
needs more than it needs the convenience.

### 2. The failure names the repair, because the repair is now known

Item 14's option 3 — "do nothing and let it fail" — was described as "honest,
but leaves a transcript that cost eight model calls permanently unscored". The
second half is no longer true, and the error has been withholding the fix.

A malformed-JSON failure now says what to do:

> re-running often clears this: the reply is deterministic only while the model
> stays loaded, so `ollama stop <model>` and judge again gets a different reply.
> Nothing else needs to change — not the seed, not the budget.

This is CLAUDE.md's "a failure must carry what's needed to fix it" applied to a
repair that was measured after the message was written. It is not a retry: the
operator decides, the run still fails, and the failure is still counted.

### 3. `response_format` is the preventive candidate, and it is gated on a measurement

Option 4 is the only one that prevents rather than repairs, and its own note
says it "should be measured before the others are argued about". That note is
honoured rather than overridden: **this ADR does not adopt it.**

The measurement it needs, specified here so the result is interpretable:

- Judge `probe/b6/transcript-2026-09-14-gate.json` with and without
  `response_format: {"type": "json_object"}`, two draws per load state each, per
  B6's protocol.
- Compare **both** the parse-failure rate and the ledgers themselves. Constrained
  decoding can change what a model writes, not merely whether it parses, and a
  format fix that quietly alters verdicts is a worse defect than the one it cures.
- Record the backend divergence: `BACKEND-PROBE-RESULTS` has Ollama honouring
  `response_format` in both modes and `mlx_lm` in neither. Adopting it would make
  the judge reliable on one backend and unchanged on another **with no signal to
  the user**, which is its own hazard and must be stated wherever it lands.

### 4. Item 14 stays open, narrowed to that one measurement

Everything else in it is decided: the premise is corrected, retries are declined
with a reason, and the error carries the repair. What remains is a single
experiment with a specified shape.

## Why

The instinct on finding a 33% failure rate is to make the failure go away. The
better move here was to notice that the rate was *only measurable because the
failure was loud*, and that the project has been wrong three times this week in
ways that only visible failures caught.

What was actually broken was not the retry policy but the error message: it held
a dead end for a problem that had a one-command fix, and CLAUDE.md already
required it to say so.

## Consequences

- **ADR-017 §4** is unchanged and gains a citation: its refusal now has
  measured support rather than only an argument.
- **`_json_object`** in `judging.py` carries the repair in both its failure
  messages.
- **OPEN-QUESTIONS 14** narrows to option 4 and points here.
- **No behaviour changes.** No retry, no new request field, no schema change —
  only what the failure says.

## Open questions this doesn't resolve

- Option 4, above, as specified in §3.
- Whether the *scoring* call and the *fact-check* call deserve different
  treatment. ADR-017 §4 measured that scoring parses reliably and the audit is
  where replies break; this batch had one of each fail, which is the first
  evidence against that split and is far too little to act on.
