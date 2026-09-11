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

### 2. Rubric weights and winner vs Hard Rule 3

- **Where:** ADR-002 "Judge design"; BUILD-GUIDE B5; `CLAUDE.md` Hard Rule 3.
- **Issue:** Rule 3 forbids blending the dimensions into one number. But the rubric
  has weights summing to 100 (30/25/20/15/10), B5 must name a winner, and steelman
  fidelity is a "tiebreaker". All three imply an aggregate.
- **A reading that reconciles them:** the judge model never outputs a blended
  score; a deterministic, documented step combines the per-dimension scores to
  pick a winner; every per-dimension score is always reported. Either state that
  or drop the weights and the winner.
- **Also undecided:** what "evidence grounding" is scored against. If it's the
  side's prep evidence, then B5 depends on B4, contradicting B5's "can run
  parallel to B4".
- **Blocks:** B5.

### 3. Budget semantics — RESOLVED by ADR-007

Both, as two fields: `budget` (per-phase cap, completion tokens) and
`prep_budget` (a pool for the whole Prep phase, required iff `"prep"` is in
`phases`). Unit is now explicit (completion tokens, per ADR-003's finding).
ADR-003's overshoot-tolerance question is still separately open.

### 4. Where the fact-checker lives

- **Where:** ADR-002 "CLI shape" and "Fact-checking is separate from judging"; the
  `run.yaml` example; BUILD-GUIDE B6; ADR-005.
- **Issue:** the docs disagree:
  - ADR-002 "CLI shape" says `judge` scores "against the rubric plus fact-check";
  - ADR-002 "Fact-checking is separate from judging" says it runs per turn,
    during the debate;
  - B6 says it isn't part of `judge`, and leaves open whether it runs inside
    `debate` or as its own command;
  - moot as of ADR-007: the `judge:` block (which `fact_check: true` sat
    under) is dropped from `run.yaml` entirely, so this particular
    contradiction is gone — but *where the fact-checker actually lives* is
    still undecided.

  ADR-005 keeps fact-check verdicts out of transcript v1 until this is settled.
- **Also undecided:**
  - what it checks against when the optional `prep` phase is off;
  - its name. Checking a claim against a side's own prep evidence tests
    grounding, not truth, and ADR-001/002 already refuse to call surface-form
    scoring "fact-check".
- **Options:**
  - per-turn events inside `debate`;
  - a re-runnable pass over a saved transcript;
  - both.

  If it runs only inside `debate`, re-checking with a different model means
  regenerating the debate — the coupling ADR-002's two-command split exists to
  avoid.
- **Blocks:** B6. Also the `run.yaml` schema (B1), if the switch moves.

### 5. Name clash with an existing DebateBench benchmark

- **Where:** ADR-002 "Naming".
- **Issue:** *DebateBench* ([arXiv 2502.06279](https://arxiv.org/abs/2502.06279),
  Feb 2025) is an existing LLM benchmark of British Parliamentary debate
  transcripts: 256 speeches across 32 debates, with official adjudication scores.
  ADR-002's collision check covered "debate"-named projects, not this exact name.
  The PyPI name `debatebench` was still unclaimed on 2026-09-11.
- **Options:** keep the name and state the distinction in the README; or rename
  before anything is published.
- **Side note:** its adjudicated speech scores could be a judge-validation
  candidate (item 6), subject to the licensing gate. Its license hasn't been
  checked.
- **Blocks:** B7 (PyPI registration) — ideally decided before the first public
  GitHub push.

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
- **Blocks:** trusting any result from B5 onward; B7.

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
  twice with stances swapped, and vary the order in which the judge sees the
  sides. A built-in sweep would be new scope, needing an ADR.
- **Blocks:** interpreting any model comparison. Nothing in B0–B7 strictly.

### 10. `sources` vs `corpus`, and how Prep retrieves — SCHEMA SLICE RESOLVED by ADR-007

`sources:` is a shared pool available to every side; each team's `corpus:` is
an optional additional per-side layer on top of it. B1 validates only that
both are well-formed. **Still open, blocks B4 only:** who forms retrieval
queries (model vs. orchestrator), the retrieval method itself, and exactly
what `prep_budget` is spent on mechanically — and, per ADR-004, this also
blocks writing a `prep_budget`-enforcement test (deliberately out of ADR-004's
Rule 5 table for now; belongs to B4/B6 once the mechanism exists).

### 11. Phase and turn semantics — NARROWED by ADR-007

**Resolved (B1-blocking slice):** `format.prep` is dropped — `phases` alone
decides whether Prep runs. `format.rounds` is dropped — multi-round exchange
is expressed by repeating a phase name in the list. Exactly two teams are
required, enforced by B1 validation.

**Still open, B2-only (the orchestration loop, not config parsing):**
- What the second speaker in a phase sees: the first speaker's turn in the
  same phase, or only earlier phases.
- Which phases (if any) run both sides at once. Affects fairness, Hard Rule 4
  and B0's load.
- What distinguishes `retort` from `rebuttal`.
- Where steelmanning happens. Steelman fidelity is scored and is the
  tiebreaker, but no phase currently asks a side to steelman.
- **Blocks:** B2 (the loop) only — no longer B1.

---

## Recorded elsewhere — index

| Where | Open question |
|---|---|
| ADR-001, "What we take" | Adopt the `evidence.py`-derived evidence-hygiene scorer? (conditional lift) |
| ADR-002, "Judge design" | Fallacy detector: its own fast pass, or folded into fact-checking |
| ADR-002, "Judge design" | Stance-consistency check: a third fast pass, or folded in |
| ADR-002, "Judge design" | `tasksource/logical-fallacy`: cleared for private validation use (authors' README grants access); redistribution/bundling still ungranted |
| ADR-002, "Judge design" | Where the 631-speech `debate_speeches` figure came from |
| ADR-002, "Hardware" | Offload judge/fact-checker to `free`, or load/unload per turn — B0 answered as-used (`RESULTS.md`): the judge can load after the debate; the pair's co-residency is unproven. **`free` is the dev machine itself** (this Mac's hostname), so "offload to `free`" isn't an offload. Is there a genuinely separate host? Until one is named, the fact-checker's only non-local option is AFM |
| ADR-002, "Hardware" | A separate inference engine for prefill-heavy prep |
| ADR-002, "Scope discipline" | A source for the ~25% Aragora scope-creep figure — cite or drop |
| ADR-002, "Language split" | DebateKit's license (a later, separate decision) |
| ADR-003 | Budget overshoot policy; HTTP client; TCP vs socket; guardrail refusals |
| ADR-004 | Minimum Python version; coverage tooling |
| ADR-005 | An existing file at the output path; what counts as a valid turn; what "round" means; a human-readable view |
| ADR-007 (gaps B1 must settle) | A `prep_budget` given when `prep` isn't in `phases`: error or ignored? Is `seed` required? Is a team's `base_url` required, and if not, what's the default? ADR-007 doesn't say |
| BUILD-GUIDE B4 | Static corpora only, or live retrieval too |
| BUILD-GUIDE B6 | Fact-checker inside `debate` or as its own command (see item 4) |

---

## Housekeeping (actions, not design questions)

- **Resolved 2026-09-11 — backed up.** This folder is a git repo, with `origin` at
  `box:Projects/DebateBench.git` via `box-backup-init.sh`. Push regularly; it's
  the backup. When the public GitHub repo is created, the helper keeps `box` as
  a second remote. On 2026-09-11:
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
