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

**ADR-015 settled what B5 hit on contact:** `--fact-check` defaults to off
until B6 and asking for it is an error (a score file never claims a check that
didn't run); `--base-url` is required, with no hidden default; the hit-ledger's
statuses are ADR-002's four; the reply is JSON with a fence and a preamble
tolerated and nothing else; the judge sees both sides' prep evidence, since
privacy binds debaters not judges; `prep_grounded` is read off the transcript,
never off the reply; the score file rotates like a transcript; and an absent
`hit_ledger` reads as empty with `hit_ledger_reported: false`, because Hard
Rule 3 forbids a *score* failing to parse, not a missing diagnostic extra.
**Built and live-tested 2026-09-12** against Qwen3-8B on `mlx_lm.server`.

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
`corpus:` gets a separate topic-only keyword search. Both `args-me` and
`debatesum` are license-checked (DebateSum: MIT;
args-me: CC-BY-4.0 with a stated "individual rights still apply" caveat,
retrieval-only, never bundled) and are **not fetched at runtime** — both
must exist locally as pre-downloaded JSONL files, a one-time manual step,
keeping debatebench's dependencies at ADR-008's fixed two and trivially
satisfying the offline requirement. `prep_budget` caps exactly one synthesis
call per side.

**ADR-014 settled what B4 hit on contact** with this: a team's `corpus:` is a
JSONL file in the shared pool's row shape (minus `side`), resolved from the
team file's own directory; prep is private to the side that wrote it; a prep
turn's `order` is 0 for both sides, since nothing about prep is sequential;
zero passages **after both pools** fails the run, so a corpus-only side is
properly prepared; `DEBATEBENCH_SOURCES_DIR` overrides where the pools are
read from; and `evidence` appears only on prep turns. **B4 was built and its
exit gate met live on 2026-09-12**, including the `prep_budget`-enforcement
test ADR-004's Rule 5 table was waiting on.

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

### 12. Response length in human terms — RESOLVED by ADR-011

Labels only, no time-based option: a new optional per-team `length` field
(`short`=2 sentences, `medium`=5, `long`=10), fixed constants for v1. It
states a target in the prompt; `budget` stays the unchanged hard cap. No
cross-field validation between them — a mismatch surfaces via the existing
`hit_budget` flag. Sentence counts sidestep both the time-to-token conversion
question and the YAML time-syntax problem entirely. Applies uniformly across
a side's argument phases, not per-phase, for v1.

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
- **Options:**
  - a per-team switch that turns thinking off, which means passing
    `chat_template_kwargs` through a request shape that has no room for it
    (ADR-009);
  - count only answer tokens against `budget`, with a separate reasoning
    allowance — which is what Hard Rule 5's "(token/reasoning)" anticipates;
  - leave it to whoever writes the `run.yaml` to set larger budgets for reasoning
    models, and record which model is which.
- **Also undecided:** whether the transcript keeps the reasoning text (v1 has no
  field, so it's dropped today), and whether the judge should ever see it.
- **Observed 2026-09-12 (B5), Qwen3-8B judging through `mlx_lm.server`:** the
  same problem now bites `judge --budget`, not just a debater's `budget`.
  - 3,000 tokens was enough to score a four-turn transcript, and was entirely
    consumed by thinking on a *prepped* one, whose evidence passages make the
    prompt much longer. The run failed with "all reasoning and no answer".
  - 6,000 scored every transcript, prepped included. B5's live tests default
    there for that reason.
  - Stating one requirement a second time (system message *and* user message)
    pushed it from complete JSON at 3,000 to nothing but reasoning at 6,000.
    On a reasoning model, extra instruction load buys more thinking, not more
    compliance — recorded in ADR-015 §8 so it isn't retried.
  - **Implication:** `judge --budget` needs a documented floor for reasoning
    models, or the same per-team thinking switch this item already weighs.
- **Blocks:** any fair comparison between a reasoning and a non-reasoning model.
  Nothing in B4–B6 strictly, but it sets `judge --budget` in practice.

---

## Recorded elsewhere — index

| Where | Open question |
|---|---|
| ADR-001, "What we take" | Adopt the `evidence.py`-derived evidence-hygiene scorer? (conditional lift) |
| ADR-002, "Judge design" | Fallacy detector: its own fast pass, or folded into fact-checking |
| ADR-002, "Judge design" | Stance-consistency check: a third fast pass, or folded in |
| ADR-002, "Judge design" | `tasksource/logical-fallacy`: cleared for private validation use (authors' README grants access); redistribution/bundling still ungranted |
| ADR-002, "Judge design" | Where the 631-speech `debate_speeches` figure came from |
| ADR-002, "Hardware" → B0 findings | **Where the fact-checker runs.** Its designated offload target, `free`, is the dev machine itself. Options: AFM-scoped per-claim checks (≤ ~4,096 tokens per request including evidence, ADR-003), which may be enough but must be decided, not assumed. AFM handles one request at a time (ADR-003), so an AFM fact-checker queues behind any AFM debater; whether it runs in parallel with MLX debaters is unmeasured; a real second machine (none identified); or a small co-resident local model. Blocks B6 |
| ADR-002, "Hardware" → B0 findings | **Does the 8B+24B debater pair fit?** Doubtful and unmeasured, not ruled out. Needs a quiet-machine B0 rerun before anything trusts the pair. Blocks any local run of the intended pairing; no B-session strictly (one model on both sides fits) |
| ADR-002, "Hardware" | A separate inference engine for prefill-heavy prep |
| ADR-002, "Scope discipline" | A source for the ~25% Aragora scope-creep figure — cite or drop |
| ADR-002, "Language split" | DebateKit's license (a later, separate decision) |
| ADR-003 | TCP vs socket; how a refusal of the model's own output surfaces |
| ADR-004 | Coverage tooling |
| ADR-009 | How `seed` reaches each request (one value or derived per turn), and whether temperature gets a config field. Blocks B3 |
| ADR-005 | An existing file at the output path, and a human-readable view — both B3, and the old `--force` idea is ruled out by ADR-007 §1 |
| BUILD-GUIDE B4 | Static corpora only, or live retrieval too |
| BUILD-GUIDE B6 | Fact-checker inside `debate` or as its own command (see item 4) |

---

## Housekeeping (actions, not design questions)

- **Resolved 2026-09-12 — the ADR-008 collision.** The Prep-retrieval decision
  drafted earlier under the label "ADR-008" is reinstated as **ADR-012**
  (revalidated against everything accepted since, and adding the args-me/
  DebateSum license check that draft never did). See item 10 above.

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
