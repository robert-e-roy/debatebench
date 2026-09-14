# CLAUDE.md — debatebench

Read `ADR-001` and `ADR-002` in full before making any architectural decision.
This file is the quick-reference; the ADRs are the actual spec, and take
precedence if anything here seems to conflict.

## What this project is

An open-source Python CLI (`debate`, `judge`) for running structured, multi-turn,
adversarial LLM debates and scoring them against a fixed rubric, with a post-hoc
fact-check pass inside `judge` (ADR-015 — real-time per-turn fact-checking is the
Swift app's feature, not this repo's). Built to evaluate MLX model + dataset choices for a companion Mac
app, but scoped and built as a standalone, general-purpose tool — not app-specific
code. See ADR-002 for full scope.

## Documents and where work stands

- `ADR-001`, `ADR-002`, `ADR-003` (AFM via `fm serve`), `ADR-004` (test
  framework), `ADR-006`, `ADR-007` (`run.yaml` schema and CLI invocation),
  `ADR-008` (Python 3.11+, `httpx`, PyYAML), `ADR-009` (backend request and
  result types), `ADR-005` (transcript format), `ADR-010` (turn order, phase
  meanings, budget tolerance, valid turns), `ADR-011` (response length,
  `short`/`medium`/`long`), `ADR-012` (Prep retrieval mechanism), `ADR-013`
  (judge scoring aggregation, winner determination, score-file format),
  `ADR-014` (corpus format, prep privacy, empty-retrieval failure), `ADR-015`
  (fact-check lives in `judge`; real-time deferred to the Swift app),
  `ADR-016` (per-phase length as a `name:length` suffix; supersedes ADR-011's
  per-team field), `ADR-017` (judge CLI details: `--base-url` required, the
  hit-ledger vocabulary, reading the model's reply), `ADR-018` (Ollama for
  real-model runs; send both budget fields, superseding ADR-003 rule 2) —
  accepted; together they are the spec.
- `BUILD-GUIDE.md` — the session-by-session build plan (B0–B7), each session with
  an exit gate. **B0 is done** for the machine as used (`RESULTS.md`: the 8B+24B
  pair can't co-reside alongside normal workload; no concurrency was measured).
  The pair is unmeasured, not ruled out: a quiet-machine B0 rerun comes before
  anything trusts it. **B1 is done** (2026-09-11): config loading and
  validation, the backend seam (ADR-009) and the `openai-compatible` adapter,
  with its exit gate met, including a live reply from AFM. **B2 is done**
  (2026-09-11): the phase loop, turn checks, the event seam and the in-memory
  transcript, with a full eight-turn debate run live on AFM and a mid-run server
  kill confirming the hard-fail invariant. **B3 is done** (2026-09-11): the
  transcript is written as JSON to the `output:` path, with any existing file
  rotated to `<output>.1`; two AFM runs with the same seed produced identical
  turns; and one debate ran across two servers at once, Qwen3-8B on
  `mlx_lm.server` against AFM. **B4 is done** (2026-09-12): prep retrieves by
  topic+side from the shared pool and by topic from a team's own corpus, spends
  `prep_budget` on one synthesis call per side, and records the raw passages as
  the turn's `evidence`; its gate was met live on AFM, an opening citing two
  invented place names that exist only in that side's evidence. **B5 is done**
  (2026-09-12): `judge` scores a transcript in one call, five dimensions per
  side, with the total and winner computed outside the model and printed beside
  every score. **B6 is built and its live gate is still NOT met** (updated
  2026-09-14): the fact-check pass runs end to end and produces a full claims
  ledger, but no single run has produced all three of its checks at once.
  **Each check has now been seen — never together.** The 2026-09-13 runs gave
  (1) and (2), including a claim contradicted by the *opponent's* recorded
  evidence, the finding `prep_grounded` cannot produce, and missed the opinion
  every time. The 2026-09-14 B7 gate run — the first with prep evidence behind
  a fresh install — gave (1) and (3): 18 claims, 17 `supported` each citing the
  claimant's own passages with correct ids, one `not_checkable` on a real
  opinion, and **zero `contradicted`**. **The earlier diagnosis on this line
  was wrong and is corrected here**: it said the model "never lists the
  opinion", called that a settled classification failure, and concluded
  "retrying will not help". Given a real evidence record the audit listed the
  opinion and classified it correctly on the first attempt. The variable was
  never the prompt's firmness — it was whether anything had been recorded to
  check against, and a prep-less transcript degrades to all `not_checkable` by
  design (ADR-015 §2), so those runs never tested the gate at all. What remains
  is the cross-side check, **and it is not a wiring fault**: the run had a
  contradiction available (`am-3` against `am-4`) and claim 14 was exactly its
  shape, yet `build_fact_check_request` sends the whole transcript plus every
  evidence id from both sides, `render()` attributes each passage to the side
  that retrieved it, and the prompt says verbatim "read every listed passage
  from BOTH sides". The malformed-JSON problem that *did* vary was fixed
  separately by having the audit cite a turn number instead of transcribing
  coordinates. See `BUILD-GUIDE.md` B6 for the full ledger. **Open question 6 is answered for
  `qwen3:8b`** (2026-09-14, `JUDGE-VALIDATION.md`): over the full 631 speeches
  of the paper's own dataset it scored **Tau-C +0.547** against the human mean —
  135% of the measured 0.405 human ceiling, clearing the ≥0.38 threshold fixed
  before any judge ran, with **631/631 replies parsed and zero failures**; a
  117-speech subset corroborates at +0.513. **Only its ordering passes.** All
  three human-authored sources land within 0.18 of human ratings while every
  machine-generated source is 0.95–1.52 low, and Tau-C is blind to that. So
  comparing two sides' scores is supported — which is what ADR-013 §3 does to
  pick a winner — while an absolute `argument_quality` number is not, and this
  tool judges machine-generated turns, where calibration is worst. The winner
  logic, steelman tiebreak, `rebuttal_effectiveness` and fact-check remain
  unvalidated. **B7 is done** (2026-09-14) and its gate is met: `LICENSE`
  (MIT), `NOTICE` carrying ADR-001's attributions, a `README.md` written
  against actual CLI behaviour, PyPI packaging metadata, and a runnable
  `examples/`. A wheel built from this tree, installed into a venv that had
  never seen the source and pulling only `httpx` and PyYAML, ran two full
  debates against Ollama and judged both — scored, fact-checked transcripts
  stamped `0.1.0.dev0`. The prep-enabled run re-verified B4 live from the
  installed package: side-filtered retrieval disjoint across sides
  (`am-1/2/3+ds-1` against `am-4/5/6/7+ds-2`, zero overlap), off-topic rows
  filtered out, `order: 0` on both prep turns, evidence absent rather than
  empty elsewhere, and a side citing its own passage by name in its opening.
  The README carries the ordering-passes/calibration-fails distinction and
  flags B6's gap **at the `--fact-check` flag itself**, since that flag is on
  by default. **Nothing is published**: the name is kept by decision (open
  question 5), and `debatebench` was still unclaimed on both PyPI and TestPyPI
  on 2026-09-14.
- `OPEN-QUESTIONS.md` — every undecided design question, with the build session
  each one blocks. Check it before starting a session, and don't pick a default
  for anything listed there.
- `JUDGE-VALIDATION.md` — the method for OPEN-QUESTIONS item 6 (does a candidate
  judge's scores track human judgement), established from the paper ADR-002
  requires reading first. Records the statistic, the verified dataset, the judge
  prompt, **what it does and does not validate**, and four decisions that are
  still open. Nothing has been run yet.
- `BACKEND-PROBE.md`, `BACKEND-PROBE-RESULTS.md`, `probe/backend/` — the
  three-server comparison behind ADR-018, its instruments and its raw rows.
- `debate-formats-research.md` — background research on real debate formats; not
  a spec.
- `R0-repo-review-session.md`, `R0-RESULTS.md` — the R0 repo review behind
  ADR-001, kept as a historical record (moved here from `~/Projects/DebateKit/`
  on 2026-09-11).

## Repository structure

This repo is **`debatebench` (Python only)**. It does not contain, and should
never gain, Swift/Xcode code, app-target files, or anything specific to the
companion Mac app.

`DebateKit` (the Swift port, per ADR-002) lives in its **own, separate GitHub
repo**, not started yet. When it exists, it depends on this project only in
the sense that its design is ported from a stabilized version of this CLI's
logic — there is no build-time or runtime dependency between the two repos.
Do not add cross-repo tooling, shared CI, or a monorepo layout without a new
ADR; the two-repo split is deliberate (see ADR-002, "Language split").

If a task references "the Swift side," "DebateKit," or the companion app and
you're working in this repo, that's out of scope here — flag it rather than
reaching across.

## Working style

- Spec-driven. Do not start writing code for a design decision that isn't
  already settled in an ADR. If something is genuinely undecided, stop and ask
  rather than picking a default silently.
- Every non-trivial architectural decision gets logged as a new ADR
  (`ADR-00N-short-title.md`), same format as `ADR-001`: Status, Date, Decision,
  Why, Consequences. (ADR-002 is a scope document organized by topic, not in that
  shape.)
- Ground-truth everything. If you're about to state what an existing file
  contains, a dependency does, or a prior decision was, verify by reading it —
  don't reconstruct it from memory of the conversation that led here.
- **A failure must carry what's needed to fix it.** Hard Rule 1 says fail
  loudly; this says fail *usefully*. An error that reports only that something
  went wrong, when it was holding the evidence, wastes the next person's time
  reconstructing what it already knew. `"Expecting ':' delimiter: line 35
  column 78"` is true and useless — recovering the reply behind it cost three
  throwaway scripts. Quote the offending text, name the field and the side, say
  which budget was exceeded and by how much, and where a fix is obvious
  (`"raise --budget"`, `"remove the space after the colon"`) say that too. This
  applies to the probe rows as much as the code: "could not test A9 because the
  engine was wedged" is a finding; a blank cell is not.

## Hard rules (non-negotiable)

Rules 1–6 each trace to a real defect found in a reviewed competing project (see
ADR-001). Rule 7 predates that review (ADR-002, "CLI shape"); R0 found nothing
against it.

1. **Never let a phase fail silently.** Every configured phase must get a
   response from every side, or the run aborts and no file is written to
   `run.yaml`'s `output:` path. No default-to-first-side fallback, no
   `continue`-past-a-failure with just a log line.
2. **Key all transcript/state by `(phase_index, side_index)`, never by side
   alone.** Overwriting per-round state is a real bug we found and are explicitly
   avoiding. This rule said `(round, side)` until ADR-007 dropped `rounds`; the
   intent is unchanged (ADR-010 §4, ADR-005).
3. **Never blend judge rubric dimensions into one number.** Score argument
   quality, evidence grounding, steelman fidelity, rebuttal effectiveness, and
   clarity independently. A parse failure on any dimension is an error, not a
   zero.
4. **Never call a synchronous SDK client inside `async def`** without
   `asyncio.to_thread`. Fake concurrency here stalls the live fact-check/
   dashboard use case this tool exists to support.
5. **Budgets (token/reasoning) are enforced by the orchestrator, per phase** —
   never left to a backend's own constructor default. An unenforced budget
   claim is worse than no budget claim for a benchmarking tool.
6. **Phases are data, not control flow.** The orchestration loop iterates a
   configured phase list. Do not branch on round number in the loop body.
7. **`debate` writes only to the `output:` path from `run.yaml`** (required
   field, no `--output` flag — see ADR-007). Never mix logging or errors into
   that file's stream; never rely on shell redirection to keep it clean.

## Config

Two file types — see ADR-002 and ADR-007 for full schema and rationale:
- `run.yaml` — one per run: topic, `format.phases` (the only source of truth
  for whether `prep` runs — no separate `prep`/`rounds` flags; each entry may
  be `name:length`, e.g. `rebuttal:long`, applying to both sides — ADR-016;
  `prep` takes no suffix; no space after the colon), per-team
  **`side` (`pro` or `con`, required, one of each — ADR-007 §7)**, `model`,
  **`base_url` (required, no default — see ADR-007)**, `budget`
  (per-phase cap, completion tokens), `prep_budget` (required iff `"prep"`
  is in `phases`; a validation error either way if it's set without `prep`
  present, or missing while `prep` is present), `sources`, `seed` (optional —
  generated and recorded in the transcript if omitted, never silently
  guessed-and-hidden), and a **required** `output` path. Exactly two entries
  in `teams:`. No `judge:` block — nothing reads it.
- `teams/*.yaml` — durable persona files (`id`, `name`, `voice`, `stance`,
  `corpus`, `values`), **hand-authored for now** (see ADR-006 — no
  PersonaForge/PersonaKit dependency exists yet; the earlier "compatible"
  claim was checked and found false). **No `model` or `budget` field here,
  ever** — that's a run-time concern, not identity.

Validation is strict (ADR-007 §6): unknown or duplicate keys are errors, phase
names come from a fixed list, and paths resolve from `run.yaml`'s directory.
Load YAML only through the package's strict loader, never plain `safe_load`
(ADR-008 lists the YAML 1.1 coercions it blocks).

`debate` takes exactly one argument, the path to a `run.yaml`. No other flags
— see ADR-007. `judge` takes a transcript path plus flags: `--model` and
`--output` (both required), an optional `--base-url`, and `--fact-check` /
`--no-fact-check` (default on). The asymmetry is deliberate, not an oversight
(ADR-007, "CLI invocation").

## Backend

Single-method `async` `Protocol` as the LLM seam (not a multi-method ABC). Its
request and result types are fixed in ADR-009: the result carries token usage,
and a reply without usage is an error, never zeros. One
`openai-compatible` adapter with configurable `base_url` should cover MLX
(`mlx_lm.server`), Ollama, LM Studio, and OpenAI through one code path — don't
build separate bespoke adapters per provider unless a provider genuinely can't
fit that shape.

The adapter uses `httpx` (ADR-008). Set explicit timeouts: httpx's 5-second
default kills real turns. **Model servers must run with `HF_HUB_OFFLINE=1`**
(ADR-002, "Backend abstraction"). Otherwise `mlx_lm.server` contacts
huggingface.co on every start. AFM goes through the same adapter via `fm serve`
(ADR-003), and its measured quirks bind the adapter:
- send `"stream": false` explicitly;
- send budgets as **both** `max_tokens` and `max_completion_tokens`, set to the
  same value (ADR-018 §4, superseding ADR-003's "never `max_tokens`"). No single
  field works everywhere: AFM honours only `max_completion_tokens`, `vllm-mlx`
  and Ollama honour only `max_tokens`, `mlx_lm` honours both. **Implemented and
  verified live** (2026-09-13): the request that drew 1287 tokens from Ollama
  against a cap of 20 now returns 20, and AFM is unaffected;
- check `usage.completion_tokens` against the budget yourself — `finish_reason`
  doesn't signal truncation.

`mlx_lm.server` (verified in B3) reads `max_completion_tokens` and `seed` from
the request body, and a team's `model` must be exactly the repo id the server
loaded. A reasoning model there returns its thinking as a separate `reasoning`
field and can spend a whole budget on it, leaving no answer — see
OPEN-QUESTIONS 13. **Ollama is the recommended server for real-model runs (ADR-018)**, measured
against `mlx_lm.server` and `vllm-mlx` on the same model in
`BACKEND-PROBE-RESULTS.md`: it honours `response_format` in both modes where
`mlx_lm` honours neither, queues a second request where `vllm-mlx` refuses it
with a 503, and prefills fastest. It costs ~20% decode speed against
`vllm-mlx`. A team's `model` is Ollama's own name (`qwen3:8b`), not a Hugging
Face repo id — the "exact repo id" rule is `mlx_lm`-specific. AFM remains the
dev default for plumbing (ADR-002). Ollama binds `*:11434` by default, which on
this machine is a deliberate toggle for remote work, not a defect; a run must
not depend on network reachability either way. LM Studio still hasn't been run
against.

**Default model for development/testing the CLI itself is Apple Foundation
Models (AFM) or another very small/instant model.** Don't reach for a real MLX
candidate model while iterating on plumbing, config parsing, or output format —
save real models for once the harness is proven and the actual question is
debate quality, not whether the pipe works.

## Explicitly out of scope — do not add without a new ADR

- Any consensus, voting, or convergence logic. This tool's whole premise is
  sustained, non-converging adversarial positions — consensus-seeking built into
  the turn loop is what ruled out `aragora-debate` and `arbgjr/multi-agent-debate`
  (see ADR-001); don't repeat it here.
- Formal verification (Z3/SymPy-style claim proving). Domain-mismatched for
  non-formalizable topics.
- Cloud-provider-specific feature creep. Stay a narrow, general-purpose
  structured-comparison tool. Aragora's own self-documented scope creep
  (~25% of its codebase, by its own authors' admission, not serving its core
  thesis) is the cautionary example — see ADR-002, "Scope discipline" (the
  source for the ~25% figure isn't recorded yet).
- UI/dashboard code. This repo is the CLI and library only.

## Attribution

`NOTICE` file required for design lifts from `aragora-debate` (`events.py`
shape) and `arbgjr/multi-agent-debate` (`Protocol` shape), and conditionally
from `aragora-debate`'s `evidence.py` if the evidence-hygiene scorer is adopted.
All source projects are MIT — see ADR-001 for exact attribution requirements.

## Testing

Per ADR-004 (accepted): pytest, with a scripted `FakeBackend` for every default
test, and live-model tests opt-in behind `DEBATEBENCH_LIVE_TESTS=1`. CI is
deferred to B7. Python ≥ 3.11 (ADR-008).
