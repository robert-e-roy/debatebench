# debatebench — Open Questions

Undecided design questions, collected in one place so none gets decided by
default. Per `CLAUDE.md`, nothing listed here gets built on until an ADR settles
it. When one does, remove the item here and cite the ADR that settled it.

Started 2026-09-11 from a review of every doc in this repo. References use section
names rather than line numbers, so they survive edits. Each item notes which
`BUILD-GUIDE.md` session it blocks.

---

## Resolved

### 1. Team files don't match PersonaForge's schema — RESOLVED by ADR-006

Compatibility claim was false (checked against `PersonaDefinition`; only `id`/
`name` overlap). Team files are hand-authored for now, no PersonaForge/
PersonaKit dependency. Schema alignment is real future work, tracked on the
PersonaKit side, not scheduled. B1 is unblocked.

---

## Not yet recorded in any ADR

### 2. Rubric weights and winner vs Hard Rule 3 — RESOLVED by ADR-013 (amended 2026-09-12)

The model outputs five independently-scored fields, never a blend (satisfies
Hard Rule 3 literally), via one call given the whole transcript, both sides
scored together — `judge` now takes a required `--budget` flag for that call
(ADR-007 §1, amended). A deterministic, always-shown-with-its-inputs sum
outside the model computes the winner: higher total, then steelman fidelity
as tiebreaker, then an explicit **draw** if still tied. Evidence grounding
scores in one of two labeled modes (`prep_grounded: true/false`) depending
on whether Prep ran, which is what lets B5 genuinely run in parallel with
B4. **This makes B5 buildable, not trustworthy — item 6 below is untouched
and still fully blocks B7.**

### 3. Budget semantics — RESOLVED by ADR-007

Both, as two fields: `budget` (per-phase cap, completion tokens) and
`prep_budget` (a pool for the whole Prep phase, required iff `"prep"` is in
`phases`). Unit is now explicit (completion tokens, per ADR-003's finding).
ADR-003's overshoot-tolerance question is still separately open.

### 4. Where the fact-checker lives — RESOLVED by ADR-015

Inside `judge`, post-hoc, as a second backend call switched by the existing
`--fact-check` flag. It checks claims against **everything recorded in the
transcript** (both sides' evidence and turns), never against the model's own
knowledge as truth — "the world" isn't reachable offline with two
dependencies. Verdicts: `supported` / `contradicted` / `unsupported` /
`not_checkable`. The real-time per-turn version is the Swift app's feature,
attaching later to the CLI's event seam. This also closes the B0 hardware
question of where a live fact-checker would run: nothing in this repo needs
a live one. The naming question (`prep_grounded` vs `fact_check`) was
already settled in ADR-013 §4.

### 5. Name clash with an existing DebateBench benchmark

- **Where:** ADR-002 "Naming".
- **Issue:** *DebateBench* ([arXiv 2502.06279](https://arxiv.org/abs/2502.06279),
  Feb 2025) is an existing LLM benchmark of British Parliamentary debate
  transcripts: 256 speeches across 32 debates, with official adjudication scores.
  ADR-002's collision check covered "debate"-named projects, not this exact name.
  The PyPI name `debatebench` was still unclaimed on 2026-09-11.
- **DECIDED 2026-09-14: keep the name, and state the distinction in the
  README.** The two are different kinds of thing — that one is a benchmark
  *dataset* of British Parliamentary transcripts with official adjudication
  scores; this is a *tool* that generates and scores debates — so the collision
  is of names, not of function. The name was re-checked and was unclaimed on
  both indexes on 2026-09-14; **`debatebench` 0.1.0.dev0 was then published to
  TestPyPI that same day** (<https://test.pypi.org/project/debatebench/>), so
  the name is now taken there. **Real PyPI is still unclaimed (404) and
  publishing there is a separate decision**, not implied by this one. The
  README opens
  with a "Not the DebateBench benchmark" section linking the arXiv paper, so
  anyone arriving for the benchmark is redirected in one line.
- **Accepted cost, knowingly:** searching the name finds two projects. That was
  decided in advance rather than discovered afterwards.
- **Side note:** its adjudicated speech scores could have been a
  judge-validation candidate (item 6), subject to the licensing gate; its
  licence was never checked, and item 6 was answered from a different dataset,
  so this stayed unused.
- **No longer blocks B7.**

### 6. No build session validates the judge

- **Where:** ADR-002 "Judge design" (validation data); BUILD-GUIDE B5 and B7.
- **Issue:** ADR-002 says the IBM datasets come "before trusting any judge model
  choice". But B5 picks a judge and B7 ships it, with no validation step in
  between. For a tool whose output is scores, that step is what makes them
  trustworthy.
- **Options:**
  - a dedicated session between B5 and B7 that correlates candidate judges with
    human ratings (`debate_speeches`, excluding its 81 control speeches;
    Rank-30k);
  - or fold that into B5's exit gate.
- **ANSWERED 2026-09-14 for `qwen3:8b`, on the full 631 — see
  `JUDGE-VALIDATION.md`.** Tau-C **+0.547** against the human mean (631/631
  parsed, zero failures), clearing the ≥0.38 threshold fixed before any judge
  ran and sitting at 135% of the measured 0.405 human ceiling. The 117-speech
  subset corroborates at +0.513.
- **But only its *ordering* passes, and that bounds what may be claimed.** All
  three human-authored sources land within 0.18 of human ratings; every
  machine-generated source is 0.95–1.52 low. Tau-C measures rank alone and is
  blind to that. So *comparing* two sides' scores is supported — which is what
  ADR-013 §3 does to pick a winner — while an absolute `argument_quality` number
  is not, and `debatebench` judges machine-generated turns, which is exactly
  where calibration is worst.
- **Still unvalidated, and B7's README must say so:** the winner logic itself,
  the steelman tiebreak, `rebuttal_effectiveness`, and the fact-check pass.
  Other candidate judges are unmeasured; only `qwen3:8b` has been run.
- **Method established from the paper first, per ADR-002.**
  The paper ADR-002 told us to read first (*Debatable Intelligence*, arXiv
  2506.05062) settles the statistic (Kendall's Tau-C against the per-speech mean
  of 15 human ratings), the data (`noystl/speech-quality-dataset`, the authors'
  own filtered 631 speeches, cached locally and verified), and the judge prompt.
  It also makes the coverage limit explicit: their annotators gave one *blended*
  1–5 score, so this speaks to `argument_quality` only — the winner logic, the
  steelman tiebreak, `rebuttal_effectiveness` and the fact-check stay
  unvalidated. **Four decisions are still open and are listed in that file**,
  the first being the acceptance threshold, which has to be chosen before
  results are seen or it becomes post-hoc justification.
- **Blocked** trusting any result from B5 onward, and blocked B7. **Cleared
  for B7 on 2026-09-14**, not by the caveats going away but by B7 shipping
  with them stated: the README carries the ordering-passes/calibration-fails
  split and names what stays unvalidated, rather than claiming "the judge was
  validated". The caution against reading an absolute score, or comparing
  scores across debates, is permanent and does not expire with this item.

### 7. B0 probes smaller models than the intended pairing — RESOLVED

BUILD-GUIDE B0 corrected 2026-09-11 to load the actual intended pairing
(`qwen3-8b` + `mistral-small`) plus a third same-tier stand-in for a local
judge, rather than placeholder small models.

### 8. `debate` invocation: flags or `run.yaml` — RESOLVED by ADR-007

File only for `debate` (one positional `run.yaml` argument, no flags;
`output:` is now required in the file). `judge` takes a transcript path plus
flags (`--model` required, `--output` required, `--fact-check`/
`--no-fact-check`) — deliberately different, not an inconsistency; see
ADR-007 "CLI invocation" for why. The `judge:` block is dropped from
`run.yaml` entirely.

### 9. Model and stance are confounded

- **Where:** ADR-002 "Asymmetry is a first-class feature".
- **Issue:** with a different model on each side, one run can't separate "the
  bigger model argued better" from "the liberal side is easier to argue on this
  topic", or from judge bias. LLM judges have documented position (order) biases,
  and may lean by stance.
- **Minimum fix:** a documented protocol rather than a feature — run each pairing
  twice with sides swapped, and vary the order in which the judge sees the
  sides. Swapping is a one-line edit: flip each team's `side:` in `run.yaml`
  (ADR-007 §7). A built-in sweep would be new scope, needing an ADR.
- **Blocks:** interpreting any model comparison. Nothing in B0–B7 strictly.

### 10. `sources` vs `corpus`, and how Prep retrieves — FULLY RESOLVED by ADR-012 (amended 2026-09-12)

`sources:` is a shared pool available to every side; each team's `corpus:` is
an optional additional per-side layer on top of it (ADR-007 §3). Query
formation for the shared pool is orchestrator-driven, keyed on **`side`**
(`pro`/`con`), not `stance` (an earlier version of this ADR used `stance` in
error — ADR-007 §7 already established it's not a position on the motion).
Shared-pool retrieval is topic+side metadata filtering; a team's own
`corpus:` (an unlabeled local directory) gets a separate topic-only keyword
search. Both `args-me` and `debatesum` are license-checked (DebateSum: MIT;
args-me: CC-BY-4.0 with a stated "individual rights still apply" caveat,
retrieval-only, never bundled) and are **not fetched at runtime** — both
must exist locally as pre-downloaded JSONL files, a one-time manual step,
keeping debatebench's dependencies at ADR-008's fixed two and trivially
satisfying the offline requirement. `prep_budget` caps exactly one synthesis
call per side. B4 and the `prep_budget`-enforcement test (ADR-004, Rule 5)
are both unblocked.

### 11. Phase and turn semantics — RESOLVED by ADR-007 and ADR-010

**Resolved (B1-blocking slice):** `format.prep` is dropped — `phases` alone
decides whether Prep runs. `format.rounds` is dropped — multi-round exchange
is expressed by repeating a phase name in the list. Exactly two teams are
required, enforced by B1 validation.

**Resolved by ADR-010 (2026-09-11):** the second speaker sees the first
speaker's turn in the same phase; no phase runs both sides at once; `retort`
answers the rebuttal aimed at your case, while `rebuttal` attacks the
opponent's; steelmanning happens inside each rebuttal, so there's no separate
steelman phase.

### 12. Response length in human terms — RESOLVED by ADR-011, revised by ADR-016 and ADR-022

Labels only, no time-based option: `short`=2, `medium`=5, `long`=10
sentences, fixed constants for v1 (ADR-011). Attached **per phase** as a
suffix in `format.phases` — `rebuttal:long` — applying to both sides, the
way real formats set length by speech type (ADR-016, superseding ADR-011's
per-team field). It states a target in the prompt; `budget` stays the
unchanged hard cap; no cross-field validation; a mismatch surfaces via
`hit_budget`. `prep` takes no suffix. Recorded per turn in the transcript
(`schema_version` 2). **ADR-022** made the suffix optional in form only: a
bare entry asks for `medium`, resolved at load, so there is no longer a way to
run a phase with no length instruction and no non-prep turn without a recorded
length. Whether 2/5/10 are the right counts is still untested, and 5 is now
what every unsuffixed run gets.

### 13. Reasoning models spend the budget on thinking

- **Where:** ADR-007 §2 (`budget`); `CLAUDE.md` Hard Rule 5, which already says
  "Budgets (token/reasoning)"; ADR-005, which has no field for reasoning.
- **Observed 2026-09-11 (B3), Qwen3-8B through `mlx_lm.server`:** it returns its
  thinking as a separate `reasoning` field and its answer as `content`.
  - At a 96-token budget there was no `content` at all: the whole budget went on
    thinking, and the turn failed.
  - At 600 tokens it spent 421, most of them thinking, on an answer of about 30.
  - With `chat_template_kwargs: {"enable_thinking": false}` it answered in 28
    tokens and did no thinking.
- **Why it matters:** `budget` counts completion tokens, which include thinking.
  The same budget therefore buys a reasoning model far less argument than a
  non-reasoning one, which confounds the very model comparison this tool exists
  to make (see item 9).
- **Also observed 2026-09-14, `gemma4:12b` through Ollama** — a second model on
  a second backend, and the failure is worse there. Ollama reports thinking in
  `reasoning`, the same as `mlx_lm.server`, but returns `content` as `""`
  rather than null when the budget runs out mid-thought. A judge scoring call
  at `budget: 6000` came back with an empty answer and 1,563 characters of
  thinking; the same transcript scored fine at 16,000. Until 2026-09-14 the
  adapter's all-reasoning-no-answer guard only caught a *missing* content, so
  the empty string fell through and `judge` reported "the reply holds no JSON
  object … raise --budget" — advice that would have bought more thinking. The
  guard now catches both shapes.
- **Turning thinking off is measured on Ollama, and the field is not the one
  this list assumed.** `reasoning_effort: "none"` works: the same prompt went
  from 99 completion tokens with 318 characters of thinking to **6 tokens and
  zero thinking**, same answer. `chat_template_kwargs: {"enable_thinking":
  false}` — the form that works on `mlx_lm.server` — is **ignored** by Ollama,
  and so is `think: false`. So the switch is per-backend, not one field.
- **Options:**
  - a per-team switch that turns thinking off. The blocker is not that the
    field is exotic — `reasoning_effort` is a standard OpenAI parameter — but
    that `GenerationRequest` (ADR-009) has no field for it *and* the right
    field differs by backend (`reasoning_effort` on Ollama,
    `chat_template_kwargs` on `mlx_lm.server`), so the seam has to carry
    something backend-shaped or the adapter has to translate;
  - count only answer tokens against `budget`, with a separate reasoning
    allowance — which is what Hard Rule 5's "(token/reasoning)" anticipates;
  - leave it to whoever writes the `run.yaml` to set larger budgets for reasoning
    models, and record which model is which.
- **Also undecided:** whether the transcript keeps the reasoning text (v1 has no
  field, so it's dropped today), and whether the judge should ever see it.
- **Blocks:** any fair comparison between a reasoning and a non-reasoning model.
  Nothing in B4–B6 strictly.

---

### 14. A transcript the judge can't parse is permanently unjudgeable — PREMISE DISPROVED 2026-09-14

**The word "permanently" is wrong, and the four options below were written
against it.** The premise was that ADR-017 §6 reuses the transcript's seed, so a
malformed reply reproduces byte-for-byte forever. Measured since: the judge's
reply is deterministic **within a model load state and not across one**
(`probe/b6/README.md`, seventeen runs, two outputs, a pre-registered cold/warm
test that hit both predictions to the byte). Stopping the model and re-running
changes the reply, needs no code, no seed change, and none of the four options.

What stays open is narrower and worth keeping: whether that repair should be
*automated*, and if so whether the tool may retry at all — ADR-017 §4 refuses a
retry loop and permits only lossless deterministic repairs, which an
unload-and-retry is not. Read the options below as answering "should the tool
handle this itself", not "is this recoverable at all".



**Blocks:** nothing yet; it bit `examples/run-prep.yaml` on 2026-09-14 and will
bite any run whose scoring reply happens to be malformed.

`judge` sends `seed=transcript.run.seed` with both its calls, so that re-judging
one transcript is reproducible (ADR-017 §6). That guarantee has a consequence
nobody wrote down: when the scoring reply comes back as invalid JSON, **every
retry reproduces it exactly**. Measured, four attempts on one transcript, the
same fault at the same character offset each time:

```
judging failed: the reply's JSON is malformed: Expecting ',' delimiter:
line 13 column 279 (char 1896)
The text at the fault: …ogic is sound and focused on systemic flaws.""},
```

The defect is a **doubled closing quote** — the model wrote `flaws.""}` where
`flaws."}` was meant. `_repair_escapes` does not catch it, correctly: it drops
backslash escapes JSON doesn't define, and this is not one.

Repairing it mechanically is not obviously safe. `""},` is also the exact shape
of a legitimate empty string (`"justification": ""`), so a rule that collapses
`""` would silently rewrite valid replies. Distinguishing them means knowing
whether text preceded the quotes, which is context a character-level repair
does not have.

Options, none chosen:

1. **A narrower repair** — collapse `""` only when the preceding character is
   neither `:` nor whitespace, so an empty value is untouched. Still a guess
   about intent, which is what ADR-017 §4 was written to avoid.
2. **Re-ask with a different seed on a parse failure.** Cheap and effective, and
   flatly contrary to ADR-017 §4's refusal of a retry loop — but the refusal was
   written when a retry meant "hope for better luck", and a *deliberate* seed
   change is a different thing. It would need the score file to record that it
   happened, or reproducibility becomes a lie.
3. **Do nothing and let it fail**, which is the current behaviour and honest,
   but leaves a transcript that cost eight model calls permanently unscored.
4. **Constrain the reply** — `response_format` is honoured by Ollama in both
   modes per `BACKEND-PROBE-RESULTS.md`, and nothing sends it. This may be the
   real answer, and it is the only option that prevents rather than repairs.

Option 4 is untested here and should be measured before the others are argued
about. Note that it binds the backend: `mlx_lm` honours `response_format` in
neither mode, so anything relying on it would work on Ollama and silently not
on MLX.

**RESOLVED for options 1–3 by ADR-026 (2026-09-15); option 4 is all that is
left of this item.** Options 1 and 2 are declined: the tool does not retry, and
ADR-017 §4's reason has been vindicated rather than weakened — **a 33% malformed
rate (2 of 6 calls in one batch) is only knowable because the failures were
loud.** Option 3's "permanently unscored" half is false, so it is no longer a
cost: re-running after `ollama stop` gets a different reply, demonstrated on
`probe/scale/` where a failed judge succeeded on a plain re-run with no seed and
no code change. The error now says so. Option 4 stays open with the measurement
shape specified in ADR-026 §3 — compare the parse-failure rate **and the ledgers
themselves**, since constrained decoding can change what a model writes, not
merely whether it parses.

### 15. The public API's six exceptions have no common base

**Blocks:** nothing. Raised by ADR-028, which created the surface that makes it
visible.

`debatebench.api` exports six unrelated exception types — `ConfigError`,
`DebateError`, `JudgeError`, `BackendError`, `TranscriptError`,
`RetrievalError`. A caller who wants "anything debatebench raises" — the normal
thing to want at the edge of a script — has to write all six in a tuple, and
will silently miss the seventh when one is added.

A shared base (`DebatebenchError(Exception)`, with each of the six inheriting
it) is backwards-compatible: every existing `except ConfigError` keeps working,
and `except DebatebenchError` starts working. The cost is that it touches six
modules across the layering ADR-008 fixes, so the base class needs a home that
all six may import — `backend.py` is the precedent (ADR-025 put
`DEFAULT_READ_TIMEOUT` there for exactly that reason), though an exception base
is not obviously a backend concern and a new `errors.py` may be cleaner.

Two things to settle before writing it: whether `ValueError` from `api.judge`
(no `base_url`, no `backend`) should also become one — it is an argument error,
not a run failure, and probably should not — and whether the base is exported
as part of the API surface, which it must be for the point of it to hold.

Not urgent. It is additive, so doing it later costs nothing that doing it now
would save.

## Recorded elsewhere — index

| Where | Open question |
|---|---|
| ADR-001, "What we take" | Adopt the `evidence.py`-derived evidence-hygiene scorer? (conditional lift) |
| ADR-002, "Judge design" | Fallacy detector: its own fast pass, or folded into fact-checking |
| ADR-002, "Judge design" | Stance-consistency check: a third fast pass, or folded in |
| ADR-002, "Judge design" | `tasksource/logical-fallacy`: cleared for private validation use (authors' README grants access); redistribution/bundling still ungranted |
| ADR-002, "Judge design" | Where the 631-speech `debate_speeches` figure came from |
| ADR-002, "Hardware" → B0 findings | **Does the 8B+24B debater pair fit?** Doubtful and unmeasured, not ruled out. Needs a quiet-machine B0 rerun before anything trusts the pair. Blocks any local run of the intended pairing; no B-session strictly (one model on both sides fits) |
| ADR-002, "Hardware" | A separate inference engine for prefill-heavy prep |
| ADR-002, "Scope discipline" | A source for the ~25% Aragora scope-creep figure — cite or drop |
| ADR-002, "Language split" | DebateKit's license (a later, separate decision) |
| ADR-003 | TCP vs socket; how a refusal of the model's own output surfaces |
| ADR-004 | Coverage tooling |
| ADR-009 | How `seed` reaches each request (one value or derived per turn), and whether temperature gets a config field. Blocks B3 |
| ADR-005 | An existing file at the output path, and a human-readable view — both B3, and the old `--force` idea is ruled out by ADR-007 §1 |
| BUILD-GUIDE B4 | Static corpora only, or live retrieval too |

---

## Housekeeping (actions, not design questions)

- **Resolved 2026-09-12 — the ADR-008 collision.** The Prep-retrieval decision
  drafted earlier under the label "ADR-008" is reinstated as **ADR-012**
  (revalidated against everything accepted since, and adding the args-me/
  DebateSum license check that draft never did). See item 10 above.

- **Resolved 2026-09-11 — backed up; extended 2026-09-16.** This folder is a git
  repo. **`origin` is now GitHub** —
  <https://github.com/robert-e-roy/debatebench>, public, MIT — and **`box` is the
  second remote** (`box:Projects/DebateBench.git`), which is the arrangement the
  workspace convention describes for a published package. Push both; box is the
  backup. On 2026-09-16 a second scrub was needed before publishing: the mirror
  probe transcripts carried an absolute home path in their `team_file` field
  across 14 commits, rewritten out of all 83 with `git filter-repo` and
  force-pushed (a verified pre-rewrite bundle was kept outside the repo). A
  full-history scan afterwards found no home paths, no hostname, no private
  addresses and no credentials. On 2026-09-11:
  - `probe/b0/` was scrubbed of local paths and the running-process list;
  - `RESULTS.md` was generalized, with no app names or hostname;
  - history was squashed into one clean commit and force-pushed, so no earlier
    version survives.

  `free` still appears as ADR-002's name for the offload host, in ADR-002,
  BUILD-GUIDE and this file.
- **Resolved 2026-09-11 — the R0 evidence is now in this repo** as
  `R0-repo-review-session.md` and `R0-RESULTS.md`. It was moved from
  `~/Projects/DebateKit/`, the folder reserved for the not-yet-started Swift
  port, which is now empty.
- **R0's headline contradicts its own scores.** `R0-RESULTS.md` says "all four
  projects are built to make agents agree", but its per-repo scores disagree.
  ADR-001 was corrected; the R0 record was left as it is. Annotate it, or leave it
  as a historical record?
