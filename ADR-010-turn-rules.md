# ADR-010: Turn Rules — Order, Phase Meanings, Budget Tolerance, Valid Turns

**Status:** Accepted
**Date:** 2026-09-11
**Depends on:** ADR-001 (alternating initiative, anti-patterns), ADR-002 (asymmetry,
initiative), ADR-003 (measured overshoot, no truncation signal), ADR-005
(transcript), ADR-007 (phase list), ADR-009 (backend result)
**Resolves:** OPEN-QUESTIONS item 11; ADR-003 open question 1; ADR-005 open
questions 2 and 3

## Decision

### 1. Turn order and what each side sees

- **The two sides speak one after the other within a phase.** The second speaker
  sees the first speaker's turn in that phase, along with every earlier turn:
  each prompt carries the whole debate so far.
- **Nothing runs both sides at once.**
- **Pro speaks first in the first argument phase, and the opener alternates with
  each phase after it.** Each turn's `order` (ADR-005) records who spoke first, so
  this is auditable rather than assumed.

### 2. What each phase asks for

- **opening** — state your case.
- **rebuttal** — first state the opponent's strongest argument fairly, in terms
  they would accept, then answer it and attack their other arguments. **This is
  where steelmanning happens**; there is no separate steelman phase.
- **retort** — answer the rebuttal aimed at your case.
- **conclusion** — sum up why your side should win, with no new arguments.
- **prep** — B4. Until then, a run whose `phases` include `prep` fails before any
  model call, with an error that says so.

### 3. Budget tolerance and what counts as a valid turn

- **A turn fails the run if its `completion_tokens` exceed its `budget` by more
  than 16 tokens.** The server's own cap is advisory (ADR-003); this check is the
  enforcement Hard Rule 5 requires. The tolerance is recorded in the transcript's
  `run` snapshot, so a transcript says which rule it was judged by.
- **A turn whose text is empty or only whitespace fails the run** (Hard Rule 1).
- **A reply that reaches its budget counts, and is flagged `hit_budget`.** Servers
  don't signal truncation — ADR-003 measured `finish_reason: "stop"` on a capped
  reply — so the flag is the only way a reader or the judge knows the reply may
  have been cut off.
- **A refusal written as text counts as a turn**, and the judge scores it. A
  refusal the server returns as an error, such as AFM's HTTP 500, fails the run
  like any other backend error.

### 4. Hard Rule 2 now reads `(phase_index, side_index)`

It said `(round, side)`. ADR-007 dropped `rounds`, so "round" no longer names
anything. The rule's intent — never key by side alone — is unchanged, and
ADR-005 already keys turns this way.

## Why

- **Sequential turns match real formats**, and rebuttal and retort are meaningless
  without the opponent's argument in hand. AFM runs one request at a time
  (ADR-003), so simultaneous turns buy no speed, and one-at-a-time keeps a run
  reproducible for B3's gate.
- **Pro first, then alternating** follows formal debate convention for who opens,
  while ADR-001's alternating initiative stops either side from keeping the
  first-mover advantage.
- **Steelmanning inside rebuttal** keeps ADR-007's phase vocabulary fixed; a
  separate phase would reopen the schema. B5 scores steelman fidelity as its
  tiebreaker and needs passages to score it from.
- **A strict cap is ruled out by measurement.** AFM returned 14 tokens against a
  12 cap, 21 against 20, and 262 against 256 (ADR-003 and B0's `RESULTS.md`). A
  strict cap would fail nearly every AFM turn, which would make B2's own AFM dummy
  debate unrunnable. 16 tokens covers every overshoot measured so far, which ran
  from 1 to 6. ADR-003's third option — streaming and cutting the reply — needs
  reliable streamed usage from every server, which isn't verified.
- **Failing loudly on `prep`** is honest, where fabricating a prep turn would put
  something in a transcript that no session has designed yet.

## Consequences

- **ADR-005 is accepted** alongside this. Its turns gain `hit_budget` and its `run`
  snapshot gains `budget_tolerance`.
- **The debate so far reaches the model as one labelled user message**, not as
  alternating `user`/`assistant` messages. A first draft of this ADR justified
  that by claiming Mistral's chat template rejects two consecutive messages from
  the same role, which alternating initiative produces. That was checked and is
  false for the model we'd actually use: `Mistral-Small-24B-Instruct-2501`'s
  template rejects only unknown roles, and Qwen3-8B's has no role-order check.
  The reasons that do hold: a `base_url` can point at any server, whose chat
  template we neither control nor see, so a system message plus one user message
  is the shape least likely to hit a template's role rules; both sides get an
  identically shaped prompt; and each turn needs a phase label that a chat role
  can't carry.
- **B4 must keep pro opening the first argument phase** when `prep` joins the
  phase list, since prep isn't an argument phase.
- **B5 reads `hit_budget`** when judging a turn that may have been cut off.

## Open questions

None. What a phase's prompt says word for word is B2's to write and tune, within
§2 above.
