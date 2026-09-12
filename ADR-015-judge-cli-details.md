# ADR-015: Judge CLI Details — Fact-Check Default, `--base-url`, and Reading the Model's Reply

**Status:** Accepted
**Date:** 2026-09-12
**Depends on:** ADR-002 ("Judge design", the hit-ledger vocabulary), ADR-005
(the transcript is the interface, and its rotation rule), ADR-007 (§1 `judge`'s
flags — amended here), ADR-009 (`GenerationRequest`), ADR-013 (the scoring
decision this fills in), ADR-014 (§2 prep privacy, which does not bind the judge)
**Resolves:** the gaps B5 hit on contact with ADR-013.

## Decision

### 1. `--fact-check` defaults to **off** until B6, and asking for it is an error

ADR-007 §1 gives `judge` a `--fact-check` / `--no-fact-check` pair defaulting
to on. Nothing can honour that yet: the fact-checker is B6, and where it even
lives is still open (OPEN-QUESTIONS item 4). Until B6:

- the default is **off**, and the score file records
  `"fact_check_enabled": false`, which is true;
- passing `--fact-check` explicitly is a **clear error** naming B6, the same
  loud failure `prep` gave between ADR-010 and B4;
- `--no-fact-check` is accepted and is a no-op, so a script written against
  the eventual default keeps working.

The alternative — accepting the flag and writing `"fact_check_enabled": true`
while nothing ran — was rejected outright. A score file that claims a check
that never happened is the unearned confidence this whole project is built
against. **B6 flips the default back to on** and deletes the error.

### 2. `--base-url` is **required**

ADR-007 §1 called it optional and never said what it would default to. It is
now required, with no default, for exactly the reason ADR-007 already gives
for a team's `base_url`: a hidden default hides which server produced a
result, and judging is a separate act from debating that may well run on a
different machine or a different model server than the debate did.

Taking it from the transcript's recorded `base_url` was considered and
rejected: the two sides may have used different servers (B3 ran exactly that),
so the rule would need a tie-break, and it would quietly couple the judge's
server to the debaters'.

### 3. The hit-ledger's statuses are ADR-002's four, and nothing else

`open`, `conceded`, `rebutted`, `dodged` — the vocabulary ADR-002 already
names. ADR-013 §1 makes a malformed dimension a hard error but never said what
a valid `status` is, so this states it: any other value is a parse failure and
aborts the judging run, exactly as a missing field does. A fixed vocabulary is
what makes the ledger comparable across runs, the same reason ADR-007 §6 fixes
the phase names.

### 4. The reply is JSON, and the parser tolerates a fence and a preamble

The judge is asked for a single JSON object. Models routinely wrap it in a
```` ```json ```` fence or introduce it with a sentence, so the parser strips a
fence and then reads from the first `{` to the last `}`. **Everything past that
is a parse failure**, which aborts the run with the reply in the message.

This is deliberately a small, stated tolerance rather than a retry loop: a
retry would make a scoring run non-deterministic and hide a model that can't
produce the format, which is a fact worth knowing about a candidate judge.

### 5. The judge sees everything, including both sides' prep evidence

Prep privacy (ADR-014 §2) is a rule about what a *debater* sees, to stop a side
pre-empting arguments it was never shown. The judge is not a participant: it
reads the finished transcript, both sides' notes and both evidence sets. That
is precisely what makes `prep_grounded: true` checkable — scoring whether a
claim traces to that side's own evidence requires seeing that evidence.

**`prep_grounded` is read off the transcript, never off the model's reply.**
Whether a debate recorded prep evidence is a fact about the file, not a
judgment, so the judge is *told* which mode applies and the score file records
what the transcript actually shows. Taking the model's word for it would let a
mistaken flag describe a guarantee the run never had — and that field exists
precisely to stop an unverified score from looking like a verified one.

### 6. The judge sends the transcript's recorded seed

The score file already records `judge_model` and `judge_budget`; the seed comes
from the transcript being judged (ADR-005 records it), so re-judging the same
transcript with the same model and budget is reproducible for any server that
honours a seed. A judging run is not a new experiment with its own seed — it is
a measurement of an existing one.

### 7. The score file rotates, exactly as a transcript does

Whatever sits at `--output` is moved to `<output>.1` before the new file takes
its place, and only one generation is kept (ADR-005, "Writing"). Re-judging the
same transcript with a different model is the normal way this command is used —
ADR-007 says so — so silently destroying the previous verdict is the same loss
ADR-005 rejected for transcripts. Written atomically, by the same code path.

### 8. An absent hit-ledger reads as empty; a malformed one still fails

ADR-013 §1 makes a missing dimension field a hard error. Hard Rule 3's actual
words are narrower and are the ones that govern: *"A parse failure on any
dimension is an error, not a zero."* A reply carrying a valid `score` and a
real `justification` for `rebuttal_effectiveness`, but no `hit_ledger`, has not
failed to score that dimension. The ledger is a diagnostic enrichment — ADR-002
introduces it so the dimension is "not a subjective number alone" — not an
input to any score or to the winner.

So: **an absent `hit_ledger` is read as empty, and the score file records
`hit_ledger_reported: false`** so an empty ledger the judge actually gave is
never confused with one it never gave. A ledger that *is* present is validated
exactly as strictly as before: a list, every entry with a non-empty point, every
status one of §3's four. Throwing away a complete, well-calibrated score sheet
over a missing extra would be the opposite of what Hard Rule 3 protects.

**Measured, which is why this section exists.** Qwen3-8B-4bit produced
well-formed, sensibly-calibrated sheets (93 against 23 on a deliberately
lopsided debate; a close 82/80 on an evenly matched one) and omitted the ledger
on the close debates every time, including after the requirement was stated in
prose rather than only shown in the example. Its `rebuttal_effectiveness`
scores were right in every one of those runs.

One further observation, recorded so nobody repeats it: stating the same
requirement a *second* time, in the user message as well as the system message,
pushed the model from complete-JSON-at-3000-tokens to nothing-but-reasoning at
both 3000 and 6000. On a reasoning model, extra instruction load buys more
thinking, not more compliance. That change was reverted.

## Why

Each of these is something ADR-013 implies but doesn't state, and each had a
wrong answer available that would have looked reasonable: a fact-check flag
honoured in name only, a `--base-url` default that hides which server scored
the debate, a free-text status vocabulary that can't be compared between runs,
a retry loop that papers over a judge model that can't hold a format, a judge
hobbled by a privacy rule written for debaters, and an overwritten verdict.

## Consequences

- **ADR-007 §1 is amended twice**: `--base-url` moves from optional to
  required, and `--fact-check`'s default is off until B6 ships.
- **B6 owns flipping the default back** and removing the explicit-flag error.
- **A judge model that can't produce the format fails the run**, and that
  failure is a real finding about that model, not a bug to retry around.

## Open questions this doesn't resolve

- **Item 6 stands untouched**: nothing here validates that a judge's scores
  track human judgment. B5 passing its exit gate means the mechanism works.
- Whether the fallacy-detector and stance-consistency checks become dimensions
  (ADR-002, ADR-013's own open questions) — unaffected.
