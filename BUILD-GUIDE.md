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
be recorded, not that validation rejects it. Backend Protocol produces a real
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

**Scope:** implement `prep` as a real phase per **ADR-012**: the orchestrator
forms each shared-pool query deterministically from `topic` + that side's
**`side`** (`pro`/`con` — not `stance`, which ADR-007 §7 says is not a
position on the motion), retrieves the top 10 matching passages per side
from `sources` (`args-me`, `debatesum` — both license-checked; `args-me` is
retrieval-only, never bundled), via topic+side metadata filtering. A team's
own `corpus`, if present, is searched separately by topic-keyword only (no
side filter — everything in it already belongs to that side), also top 10,
layered on top of the shared-pool results. Neither dataset is fetched at
runtime: both must exist locally as pre-downloaded JSONL files (ADR-012 §5,
a one-time manual step, not code this session writes). Each side then gets
exactly one model call, capped at `prep_budget`, to synthesize its combined
retrieved passages into prep notes. The Prep turn records both the raw
retrieved passages (`evidence`) and the synthesis call's output (`text`),
with that turn's `budget` field holding `prep_budget`'s value, not `budget`'s
(ADR-012 §4).

**Deliverable:** a debate run where each side's Prep evidence is visible in the
transcript, separately from its argument phases.

**Exit gate:** confirm a claim made during Opening can be traced back to
something actually present in that side's own Prep evidence set — that
traceability is the entire point of this phase.

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

## B6 — Fact-checker

**Depends on:** B4 (needs Prep evidence to check claims against) and B5 (runs
alongside judge conceptually, but is a separate, faster pass — not part of
`judge` itself).

**Scope:** fast, per-claim verification against the side's own recorded Prep
evidence (not open-ended search), designed to run per-turn rather than only at
the end. Decide whether it's invoked as part of `debate` (emitting fact-check
events per turn) or as a related but separate command — not yet settled, make
the call here and log it as a new ADR if it deviates from assuming it's
event-driven inside `debate`.

**Deliverable:** each turn's claims get a fact-check verdict (supported /
unsupported / not-checkable) against that side's Prep evidence.

**Exit gate:** deliberately have a side cite something outside its own Prep
evidence and confirm the fact-checker catches it — this is the specific
failure mode Prep (B4) exists to make catchable.

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
a real MLX model, judge it, and get a scored, fact-checked transcript — with
zero manual setup beyond the install, a `run.yaml`, and the model servers it
points at already running (`mlx_lm.server`, `fm serve`). The judge must be a
model whose context holds a full transcript. AFM can't (~4,096-token limit; see
ADR-003's probe results). If the tool should start those servers itself, that
needs a new ADR.

---

## Explicitly deferred, not part of this guide

- UI/dashboard (separate repo/effort per CLAUDE.md).
- `DebateKit` Swift port (separate repo, starts only once this design stops
  changing session to session, per ADR-002).
- Fallacy-detector as its own pass (open per ADR-002) and live-vs-static Prep
  retrieval as a user-facing choice (raised in B4 above, not in ADR-002) — decide
  during B4/B5 rather than blocking on them now.
