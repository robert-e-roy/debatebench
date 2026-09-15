# ADR-023: A Coin Toss Resolves What the Steelman Tiebreak Can't

**Status:** Accepted
**Date:** 2026-09-14
**Depends on:** ADR-013 (§3 winner determination, §5 score-file format),
ADR-005 (the transcript's recorded `seed`), ADR-007 §5 (a seed is always
present), ADR-017 §6 (the judge reuses the transcript's seed)
**Supersedes:** ADR-013 §3 clause 3 — the explicit draw

## Context — the draw is not as principled as it was argued to be

ADR-013 §3 ends its tiebreak chain with a draw, and defends it:

> If `steelman_fidelity` is also equal, the result is an explicit **draw**, not
> an arbitrary tiebreak. A confident-looking forced verdict the evidence doesn't
> support is the same dishonesty the hard invariant already refuses for a
> one-sided debate.

The objection is to a verdict that *looks* earned and isn't. It is not an
objection to resolving the tie — it is an objection to hiding that the
resolution was arbitrary. The score file already has the field that removes the
disguise: `winner_reason` sits beside `winner` and is written on every run.

A second thing has changed since ADR-013. The draw it protects is not rare or
hard-won: `examples/` produces 100/100 against 100/100, both sides maxing all
five dimensions, and `judge` reports "a draw (tied after steelman tiebreak)".
`JUDGE-VALIDATION` records that only the judge's *ordering* is validated and
that it scores machine-generated text 0.95–1.52 low against human raters. A
scale that saturates is a live possibility, and "draw" is what saturation looks
like from outside.

## Decision

### 1. A tie after the steelman tiebreak is resolved by a coin toss

The chain becomes:

1. Higher total wins — `winner_reason: "total"`.
2. Equal totals: higher `steelman_fidelity` wins — `"steelman_tiebreak"`.
3. Still equal: a coin toss — **`winner_reason: "coin_toss"`**.

`winner` is then `"pro"` or `"con"`. `"draw"` is no longer produced.

### 2. The coin is the transcript's own seed, and the rule is published

```
winning side_index = transcript.run.seed % 2
```

Nothing is drawn at judging time. ADR-007 §5 guarantees a seed is always
present — written in `run.yaml` or generated and recorded — and it is generated
with `secrets.randbelow(2**31)`, a uniform draw over an even bound, so its
parity is a fair coin.

This keeps ADR-013 §3's actual principle intact: the winner still comes from "a
fixed, published arithmetic step, not a model judgment". It is one line of
arithmetic over a number the transcript already records, so a reader can check
the toss by hand.

### 3. It maps to the side index, not to the team

The alternative — hash the team ids so a given team always wins its tosses —
was rejected, and the reason is the protocol in OPEN-QUESTIONS 9. That protocol
runs a pairing twice with `side:` swapped to separate model strength from
position. Under a team-keyed coin the *same team* would win both tosses, adding
a team-correlated constant to exactly the comparison the protocol exists to
make. Keyed to the side index, a swapped pair at one seed gives one toss to
each team, and across runs with fresh seeds the tosses split evenly between
positions.

It also survives the mirror case — the same team file on both sides, which is
how position bias is actually measured. There the teams are identical and a
team-keyed coin has nothing to key on.

### 4. `schema_version` is unchanged

`winner_reason` gains a value; the key, its type, and `winner`'s three
permitted strings are untouched. ADR-005 bumps on a change to the document's
shape, and this is a change to which values occur — the same reasoning ADR-022
§5 recorded for per-turn `length`. `"draw"` stays a legal value of `winner`
because score files written before this ADR contain it, and a reader must keep
understanding them.

### 5. The reason field is the whole defence, so it is not optional

A `coin_toss` winner is only honest while the file says so. `winner_reason` is
already required in every score file (ADR-013 §5) and the CLI already prints it
beside the winner. Nothing may report a `winner` without its reason, and any
analysis that counts wins must be able to exclude coin tosses — which is why
the value is its own string rather than folded into `steelman_tiebreak`.

## Why

The draw was defended on the grounds that a forced verdict is dishonest. That
holds for an *unlabelled* forced verdict. Labelled, a coin toss discards no
information: `winner_reason: "coin_toss"` says precisely as much as
`winner: "draw"` did, and additionally hands a caller who needs a decision one
that is fair rather than absent.

Seeding it from the transcript rather than drawing at judging time matters more
than it looks. Re-judging a transcript already produced a different verdict
under some conditions (see `probe/b6/README.md`); a freshly drawn coin would
have added a second, unrelated source of the same instability, on the one step
of the pipeline that is supposed to be pure arithmetic.

## Consequences

- **ADR-013 §3** clause 3 superseded; §5's enumeration of `winner_reason` gains
  `"coin_toss"`. Amendment notes added to both.
- **`decide()`** in `judging.py` returns a side where it returned `"draw"`.
- **Hard Rule 3 is untouched.** No dimensions are blended; the coin reads a
  seed, not a score.
- **A tied re-judge is stable**: the same transcript always tosses the same way.
- **Tests** that assert a draw now assert a coin toss; the draw path keeps a
  reader test, since old files still carry it.
- **`JUDGE-VALIDATION`**'s list of unvalidated machinery gains one entry. The
  winner logic and the steelman tiebreak were already on it.

## Open questions this doesn't resolve

- **Whether a tie means "equal" or "the scale topped out".** The observed draw
  is 100/100 against 100/100, which is a ceiling, not a close contest. A coin
  toss resolves it either way and tells you nothing about which it was. Counting
  how many ties sit at the maximum — answerable from score files already on
  disk — would say whether the rubric needs a wider scale, and that is a
  different fix from this one.
- **Whether `"draw"` should be recoverable** for a caller that would rather
  know. No flag is added here; if one is wanted it is a new ADR.
