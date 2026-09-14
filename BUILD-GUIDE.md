# debatebench — Session Build Guide

Read `CLAUDE.md` and every accepted ADR (`ADR-001`, `ADR-002`, …) before
starting any session below.
Each session has a single deliverable and an exit gate — don't start the next
session until the current one's gate is met. If a session's findings
contradict something in ADR-001/002, stop and write a new ADR rather than
quietly deviating.

---

## B0 — Hardware reality check

**Why first:** everything downstream assumes 2-3 models can run concurrently
on the dev machine (M2 Pro, 32GB). ADR-002 flags this as unvalidated. Better
to know now than after building around a false assumption.

**Scope:** throwaway probe script only, no CLI, no package structure yet.
Load the *actual intended pairing* — `qwen3-8b` and `mistral-small` (ADR-002's
own example, ~22-24B depending on version), not placeholder small models (a
probe of small models can't say whether the real pairing fits; this was
flagged and is corrected here). Load a third same-tier model standing in for
a local judge/fact-checker alongside them, since that's the actual 3-model
scenario ADR-002's "Hardware" section leaves open. Run a few turns of dummy
generation against each, measure peak unified memory and per-model token/sec
under contention vs. isolation. AFM (the plumbing dev-default, ADR-003) is a
separate, much smaller case — worth a quick contrast measurement, but not a
substitute for probing the real pairing.

**Deliverable:** a short `RESULTS.md` with real numbers: peak memory, per-model
throughput solo vs. concurrent, and a recommendation — run 3 local, offload
judge/fact-checker to `free` over the network, or load/unload per turn.

**Exit gate:** a documented answer to "how do we run this on the dev machine,"
even if the answer is "we can't, here's the workaround." No code from later
sessions should assume concurrency that wasn't actually measured here.

---

## B1 — Config + backend scaffolding

**Depends on:** B0 (for backend choice, not blocking — AFM works regardless).

**Scope:**
- `run.yaml` and `teams/*.yaml` parsing + validation, per the schema in
  ADR-002 and **ADR-007**. Fail loudly and specifically on a malformed config
  — missing team file, no phases listed, missing `output`, missing
  `prep_budget` when `"prep"` is in `phases`, a `teams:` list with other than
  two entries, malformed YAML, missing required field. Don't guess defaults
  for anything the user didn't specify.
- The single-method `async` `Protocol` backend seam (ADR-002/CLAUDE.md).
- One backend implementation only: **AFM or another instant/free model** —
  not MLX yet. The goal here is proving the seam and config loading work, not
  evaluating model quality.

**Deliverable:** a script that loads a `run.yaml` (invoked as `debate
run.yaml`, per ADR-007 — no other flags), resolves its team files,
constructs backend instances per team, and can generate one dummy response per
side through the `Protocol` — no phases, no orchestration loop yet.

**Exit gate:** config validation has a real test case for each failure mode
below, plus the valid-file case, and each fails or succeeds correctly (see
ADR-007 for the full reasoning behind each): missing `output`; missing
`base_url` on any team; `prep_budget` set without `"prep"` in `phases`, and
the reverse; a `teams:` list with other than two entries; the existing
malformed-YAML/missing-required-field cases. `seed` absent is explicitly
**not** a failure case — confirm the loader generates one and it's ready to
be recorded, not that validation rejects it. **Added by ADR-016** (retro-edit
to finished B1): a phase entry with a bad suffix (`rebuttal:huge`), a
`prep:` suffix, a `length` key on a `teams:` entry, and a phase entry that
YAML parsed as a mapping (`rebuttal: long`, space after the colon) — the last
must fail with a hint naming the space, not a generic type error. A valid
suffixed list (`opening:short, rebuttal:long`) must load with the lengths
attached. **Added by ADR-022** (retro-edit): a bare entry must load as
`medium`, and a bare `prep` must still load as no length at all. Backend Protocol produces a real
response from AFM.

---

## B2 — Orchestration loop

**Depends on:** B1.

**Scope:** implement the phase loop as data (not branching on round number),
per-side budget enforcement at the orchestrator level, alternating initiative,
transcript state keyed by `(phase_index, side_index)` (ADR-010 §4), and the
turn rules in ADR-010, and the hard-fail invariant (any
missing phase response aborts the run, nothing partial gets written). Wire in
the typed event system (`EventType`/dataclass dispatch, per ADR-001) even
though nothing consumes the events yet — this is the seam the future live
dashboard/fact-check panel will attach to.

**Deliverable:** a full dummy debate (AFM on both sides) runs end to end
through every configured phase and produces an in-memory transcript object.
**Added by ADR-016** (retro-edit to finished B2): each phase prompt states the
target sentence count when its entry carried a `:length` suffix (ADR-011 §2's
2/5/10), the same instruction to both sides; bare entries say nothing about
length. The turn records `length` only when a suffix was present.
**Amended by ADR-022** (retro-edit): the last two sentences no longer hold —
a bare entry resolves to `medium` at load, so every non-prep prompt states a
target and every non-prep turn records one. The prompt builder is unchanged by
that ADR; it never learns a default exists.
Keep per-phase budgets small enough that every AFM request — instructions,
whatever context the prompt carries, and the reply — stays under AFM's
~4,096-token limit. A request over it fails with HTTP 500 (measured; see
ADR-003's probe results).

**Exit gate:** deliberately break something — kill a phase mid-run, misconfigure
a budget — and confirm the hard-fail invariant and per-phase budget enforcement
actually trigger, not just that the happy path works. Each of the four
anti-patterns from ADR-001/CLAUDE.md has a corresponding test that would have
caught it.

---

## B3 — `debate` command

**Depends on:** B2.

**Scope:** CLI wrapper around the orchestration loop. The `output:` path from
`run.yaml` (per ADR-007 — required, no `--output` flag) is where the
transcript gets written as JSON; all logging/errors go to stderr only,
verified by literally asserting the output file is valid JSON with nothing
else mixed in. Wire in the `openai-compatible base_url` adapter so real MLX
models (`mlx_lm.server`), Ollama, and LM Studio all work through the same
backend implementation used for AFM in B1.

**Deliverable:** `debate run.yaml` (per ADR-007 — a single config-file
argument, no flags) works against both AFM and a real local MLX model,
resolving each team's `base_url`.

**Exit gate:** run the same `run.yaml` twice against AFM (its `seed` field
fixes the value for both runs — there is no `--seed` flag) and confirm each
turn's generated text is identical across the two runs. Compare turn text,
not whole files, since run metadata such as timestamps can legitimately
differ. `fm serve` returned identical output for repeated requests with the
same seed when probed one request at a time (see ADR-003's probe results),
so the old "document why not" fallback shouldn't be needed for AFM.

---

## B4 — Prep phase

**Depends on:** B3.

**Scope:** implement `prep` as a real phase per **ADR-012** and **ADR-014**:
the orchestrator forms each shared-pool query deterministically from `topic`
+ that side's **`side`** (`pro`/`con` — not `stance`, which ADR-007 §7 says
is not a position on the motion), retrieves the top 10 matching passages per
side from `sources` (`args-me`, `debatesum` — both license-checked;
`args-me` is retrieval-only, never bundled), via topic+side metadata
filtering. A team's own `corpus`, a JSONL file resolved relative to the
*team file's own directory* (not `run.yaml`'s — ADR-014 §1), the same row
shape as the shared pool minus `side`, is searched separately by
topic-keyword only, also top 10, layered on top of the shared-pool results.
**A side that retrieves zero passages from both pools combined fails the
run** (ADR-014 §4) — checked after both pools, not after the shared pool
alone, since a corpus-only or sources-only match is still a properly
prepared side. Neither dataset is fetched at runtime: both must exist
locally as pre-downloaded JSONL files under
`~/.cache/debatebench/sources/`, overridable via `DEBATEBENCH_SOURCES_DIR`
(ADR-012 §5, ADR-014 §5, a one-time manual step, not code this session
writes).

Each side then gets exactly one model call, capped at `prep_budget`, to
synthesize its combined retrieved passages into prep notes. **Prep is
private**: a side's own prep turn feeds its own later prompts; the
opponent's prep is never rendered to it, only recorded in the transcript for
the judge and fact-checker to read later (ADR-014 §2) — `render_debate`
takes the viewing side as a required argument, no default. The Prep turn
records the raw retrieved passages (`evidence`, present only on prep turns —
ADR-014 §6) and the synthesis call's output (`text`), with that turn's
`budget` field holding `prep_budget`'s value and `order` set to `0` for both
sides, since nothing about parallel, independent retrieval is sequential
(ADR-014 §3).

**Deliverable:** a debate run where each side's Prep evidence is visible in the
transcript, separately from its argument phases.

**Exit gate:** confirm a claim made during Opening can be traced back to
something actually present in that side's own Prep evidence set — that
traceability is the entire point of this phase. Also confirm two failure
modes ADR-014 specifies: a side whose combined retrieval (both pools) comes
back empty aborts the run with a named error, and a debate transcript where
one side's Opening never references or benefits from the *other* side's prep
notes (privacy actually held, not just assumed).

---

## B5 — `judge` command

**Depends on:** B3 (can run parallel to B4 — judge scoring doesn't need Prep
to exist yet, just a transcript).

**Scope:** per **ADR-013**: one backend call, given the whole transcript,
outputs five independently-scored dimensions per side plus the rebuttal
hit-ledger, never a blended number (Hard Rule 3), capped by a new required
`--budget` flag (ADR-007 §1, amended). The orchestrator, not the model, sums
them into each side's total and picks a winner: higher total, then steelman
fidelity as tiebreaker, then an explicit `"draw"` if still tied. Evidence
grounding scores as `prep_grounded: true` (checked against the side's Prep
evidence) or `prep_grounded: false` (general rigor only) depending on
whether Prep ran in that transcript — this is what lets `judge` run without
Prep ever having existed. A judge model whose context can't hold the whole
transcript fails via the existing `BackendError` path (ADR-009), same as any
other backend limit — no new handling needed for that case. Reads a
transcript file, writes a score file in the shape ADR-013 §5 defines.

**Deliverable:** `judge transcript.json --model <model> --budget <n> --output
score.json` (ADR-007, ADR-013) produces a
per-side, per-dimension breakdown plus a winner, with steelman fidelity as the
explicit tiebreaker.

**Exit gate:** three transcripts, not one: a deliberately lopsided one (clear
winner by total), a genuinely close one (exercises the steelman tiebreak,
including an actual `"draw"` result if totals and steelman both tie), and one
with no `prep` in its phase list (exercises `prep_grounded: false`). Confirm
each score breakdown explains *why*, not just *that*, a side won or the
result was
a draw — the diagnostic value is the point. **This exit gate tests that the
mechanism works, not that the judge's scores are trustworthy** — item 6
(correlating against human ratings) is separate and still fully open; B7
stays blocked on it regardless of B5 passing this gate.
a draw.

---

## B6 — Fact-check pass in `judge`

**Depends on:** B4 (recorded `evidence` to check against) and B5 (the
`judge` command this pass lives in).

**Scope:** per **ADR-015**: a post-hoc pass inside `judge`, on by default,
switched by the existing `--fact-check` / `--no-fact-check` flag. It is a
**second backend call** after the scoring call, capped by the same
`--budget` value applied on its own. It extracts each argument-phase turn's
factual claims and gives each a verdict against **everything recorded in the
transcript** — both sides' `evidence` passages and both sides' turns — never
against the model's own knowledge as ground truth: `supported`,
`contradicted`, `unsupported`, or `not_checkable`. A transcript with no prep
gets `not_checkable` throughout, with a note saying why. Output is the
`fact_check` section of the score file (ADR-015 §4; score-file
`schema_version` 2). Real-time per-turn checking is *not* built here — it's
the Swift app's feature, attaching later to the event seam B2 already wired.

**Deliverable:** a score file whose `fact_check.claims` ledger lists every
extracted factual claim with a verdict and, where applicable, the
`evidence_ids` that support or contradict it.

**Exit gate:** three checks. (1) A side cites something present in *its own*
prep evidence — verdict `supported`, correct `evidence_ids`. (2) A side
asserts something that the *opponent's* recorded evidence contradicts —
verdict `contradicted`, pointing at the opponent's passage; this is the
finding `prep_grounded` alone can never produce, and the reason the pass
exists. (3) A side asserts an opinion or prediction — verdict
`not_checkable`, not a false `unsupported`.

**Status 2026-09-14 — still unmet, and the diagnosis has changed.** Every
one of the three checks has now been observed; none of them together. The
2026-09-13 runs produced (1) and (2) — including a claim contradicted by the
*opponent's* recorded passage — and missed the opinion each time. The
2026-09-14 B7 gate run, the first with prep evidence behind a fresh install,
produced (1) and (3): 18 claims, 17 `supported` each citing the claimant's
own passages with correct ids, and one `not_checkable` on a real opinion
("the CON's focus on 'leakage' overlooks the urgency of action") — with
**zero `contradicted`**.

The old note here, that the model "never lists the opinion" and that
retrying would not help, is **disproven**. Given a real record the audit
listed the opinion and classified it correctly first time. The variable was
never how firmly the prompt was worded; it was whether anything had been
recorded to check against — and a prep-less transcript degrades to all
`not_checkable` by design (ADR-015 §2), so those runs never tested this gate
at all.

The gap was the cross-side check, **and it was not a wiring fault.**
The 2026-09-14 run had a contradiction available — `am-3` (pro: recycling
"turns a regressive tax into a progressive transfer") against `am-4` (con:
regressive "before any rebate arrives … reimbursed last") — and claim 14,
the PRO asserting its revenue-sharing "neutralizes regressive impacts", is
precisely clause (2)'s shape. It was marked `supported` on `am-3` alone.
Ruled out by reading the source: `build_fact_check_request` sends the whole
transcript plus every evidence id from both sides, `render()` attributes each
passage to the side that retrieved it, and the prompt says verbatim "read
every listed passage from BOTH sides … catching that is the point of this
audit".

**What it actually was: a definition, not a delivery problem.** ADR-015 §2
defined `supported` and `contradicted` by the same test and gave no
precedence, so where both sides retrieved passages on one point — which on a
contested motion is most points — `supported` was always a defensible
answer and the gate was structurally unreachable. **ADR-019** makes a
contradiction outrank a backing passage and narrows `supported` to
"uncontested".

**Status 2026-09-14 (later) — clause (2) met and reproducible; clause (3) is
now the only gap.** First B6 runs to leave artifacts, in `probe/b6/`: seven
runs, one saved prep transcript, same seed, `--budget 6000`, `qwen3:8b` on
Ollama. Six return an identical ledger — 20 claims, 15 `supported`, 3
`contradicted`, 2 `unsupported`, hashing the same once `judged_at` is
stripped — with all three contradictions **cross-side**, including the con's
own `am-4` claim contradicted by the pro's `am-3`. The seventh is run 1,
which returned 11 claims and cited the speaker's own `am-4` as `supported`;
it looks like a pre-ADR-019 control but is not one — `judging.py` was saved
at 10:41:06 and that run started at 10:41:54. It was the first judge call
after the model loaded, and is recorded as a cold-server sample.

Clause (3) never fires: zero `not_checkable` across all seven. **The opinions
are listed**, so ADR-015's "Filter nothing out" instruction is working; they
land one verdict over, in `unsupported` — the value judgement "the CON's
focus on leakage overlooks climate urgency" and the prediction "rural
renewable energy investment can offset fossil fuel reliance". The prompt
separates the two verdicts by a question it never tells the model to ask
first: is this a factual claim at all? That is the next thing to test, and it
is testable by wording.

**Withdrawn:** the claim that ADR-019 "traded clause (3) for clause (2)". The
run that produced a `not_checkable` used a different transcript and its score
file was not saved, so there is no before/after on one input and no trade was
measured.

One further observation from the same ledger, unresolved: claim 10 attributes
the PRO's Brindlewick claim to the **CON**, because the CON restated it in
order to rebut it. A side quoting its opponent to attack them is not
asserting the thing.

---

## B7 — Packaging and publish

**Depends on:** B3-B6 all functional.

**Scope:** `NOTICE` file with the ADR-001-specified attributions, a README
written against actual CLI behavior (no draft exists in this repo yet), license
file (MIT), PyPI packaging metadata, confirm
`debatebench` name is still unclaimed before registering.

**Deliverable:** installable via `pip install debatebench` from TestPyPI at
minimum.

**Exit gate:** a clean environment can `pip install`, run a full debate against
a real model, judge it, and get a scored, fact-checked transcript — with
zero manual setup beyond the install, a `run.yaml`, and the model servers it
points at already running. The judge must be a
model whose context holds a full transcript. AFM can't (~4,096-token limit; see
ADR-003's probe results). If the tool should start those servers itself, that
needs a new ADR.

**Amended 2026-09-14, substance unchanged.** This line used to say "a real MLX
model" and name `mlx_lm.server` / `fm serve`. ADR-018 has since recommended
**Ollama** for real-model runs, and open question 6 measured a judge on exactly
one model, `qwen3:8b`, running there — so that is what the gate is run against.
Nothing is relaxed: it must still be a full debate, judged with the fact-check
on, from a wheel installed into an environment that has never seen the source
tree.

**Passing this does not close B6.** B6's gate asks for three specific verdicts,
one of which (`not_checkable` on an opinion) has never appeared. B7's asks only
that the pass runs and writes its ledger. Both are true at once, and neither
substitutes for the other.

---

## Explicitly deferred, not part of this guide

- UI/dashboard (separate repo/effort per CLAUDE.md).
- `DebateKit` Swift port (separate repo, starts only once this design stops
  changing session to session, per ADR-002).
- Fallacy-detector as its own pass (open per ADR-002) and live-vs-static Prep
  retrieval as a user-facing choice (raised in B4 above, not in ADR-002) — decide
  during B4/B5 rather than blocking on them now.
