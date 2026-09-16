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
  real-model runs; send both budget fields, superseding ADR-003 rule 2),
  `ADR-019` (in the fact-check, a contradiction outranks a backing passage;
  `supported` narrows to "uncontested" — a prompt rule with no code
  enforcement), `ADR-020` (judge settings live in an optional `judge:` block in
  `run.yaml`; `judge` takes a run.yaml or a transcript; flags override —
  amending ADR-007 §1), `ADR-021` (`debate` gains `--model`/`--budget` and
  `--pro-*`/`--con-*` overrides; nothing else, and Hard Rule 7 stands),
  `ADR-022` (a phase entry with no `:length` suffix asks for `medium`, resolved
  at load; supersedes ADR-011 §4 and ADR-016 §3, narrows ADR-016 §6, no
  `schema_version` bump), `ADR-023` (a tie after the steelman tiebreak is
  resolved by a coin toss — `run.seed % 2`, keyed to the side index, recorded
  as `winner_reason: "coin_toss"`; supersedes ADR-013 §3 clause 3, no
  `schema_version` bump), `ADR-025` (the read timeout is a `timeout:` key in
  `run.yaml` and in the `judge:` block plus a `--timeout` flag on both commands,
  default 600 seconds unchanged; deliberately **not** recorded in the transcript,
  since it cannot shape the output — only whether one arrives), `ADR-024`
  (checkability gates the other three fact-check verdicts; §1 and §2 stand, §3's
  reorder was measured and reverted), `ADR-026` (a malformed judge reply names
  its repair — stop the model and re-run — and the tool still does not retry;
  resolves OPEN-QUESTIONS 14 except its `response_format` option), `ADR-027`
  (`debate --events` streams JSONL on stdout, one line per event, flushed per
  line, with a `run` header carrying `schema_version`; a contract for other
  programs so the stderr log stays free to change — Hard Rule 7 untouched, and
  the stream is explicitly **not** a transcript), `ADR-028` (one public module,
  `debatebench.api`: two async functions `debate(config)` and `judge(transcript)`
  named for the two commands, a curated export list, and **both CLIs call it**
  so there is one composition rather than two; it writes no files and takes an
  injected `Backend`, so a caller needs no HTTP server; `__init__.py` still
  exports nothing, and the JSON `schema_version`s remain the durable contract
  while the Python surface is pre-1.0 — resolves ADR-027's open question about
  whether the event stream should be the only machine-readable seam: it is not),
  `ADR-029` (release `0.1.0` to real PyPI via Trusted Publishing from a
  published GitHub Release — no token anywhere, since two have already leaked
  here; a bad release is yanked and superseded, never re-uploaded, because PyPI
  forbids reusing a version; `0.1.0` claims the commands and the three file
  formats are stable within 0.1.x, **not** that B6's gate is met) — accepted;
  together they are the spec. **`ADR-030`** (the `factual` boolean: accepted,
  implemented, measured and **reverted** the same day — §9 carries the result and
  is the part worth reading; ADR-024 §4 stands unamended because the code
  enforcement that would have justified amending it is gone with the revert).
- `MODEL-COVERAGE.md` — which models have actually been run, at what size, as
  debater or judge, with the artifact behind each. **No large (24B+) model has
  ever produced a token here**; every quality finding in this repo comes from
  models between roughly 3B and 12B, and only `qwen3:8b`'s judging is validated
  at all. Read it before trusting any claim about debate or judging quality.
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
  design (ADR-015 §2), so those runs never tested the gate at all. The cross-side check was
  **not a wiring fault** — the run had a contradiction available (`am-3`
  against `am-4`), `build_fact_check_request` sends the whole transcript plus
  every evidence id from both sides, and the prompt says verbatim "read every
  listed passage from BOTH sides". The cause was a definition: ADR-015 §2 gave
  `supported` and `contradicted` the same test with no precedence, so on a
  two-sided corpus `supported` was always defensible. **ADR-019 fixes that and
  clause (2) fires in every warm run** (2026-09-14, artifacts in `probe/b6/`):
  20 claims — 15 `supported`, 3 `contradicted`, 2 `unsupported` — all three
  contradictions cross-side, including the con's own `am-4` claim contradicted
  by the pro's `am-3`.
  **That "met and reproducible" status is now UNSETTLED (2026-09-16,
  OPEN-QUESTIONS 16).** Asked about the *cited passage alone*, all four models
  tested — **including `qwen3:8b` itself** — say two of those three are not
  contradictions; `am-3` reads "turns **a regressive tax** into a progressive
  transfer", which presupposes the regressivity the claim asserts. Adding the
  opponent's **turn text** flips three of four cells to YES, with reasons that
  name it ("the record *argues* that…"). So these verdicts are driven by what
  the opponent **argued**, while the citation must name a **passage** — only
  passages have ids, and `_evidence_citations` refuses `contradicted` without
  one — and nothing checks that the cited passage is what contradicted. ADR-015
  §2's record includes turns; the gate clause asks for the opponent's
  *evidence*, cited. The two do not agree, which is a decision to make rather
  than a bug to fix. Not ADR-019's emphasis block: prepending `CONTRADICTION
  WINS` verbatim flips nothing, six of six.
  **"Reproducibly" needed a condition that was not known when it was written.**
  Seventeen runs on that one saved transcript have produced exactly **two**
  outputs, byte-identical within each group, and a pre-registered test
  (`probe/b6/statetest-{cold,warm}.json`) confirmed what selects between them:
  whether the model was already resident when the call arrived. Warm gives the
  20-claim ledger every time; **cold gives 11 claims and zero
  `contradicted`** — a cold judge silently under-reports. So the audit is
  deterministic *within* a load state and not across one, ADR-017 §6's
  reproducible re-judging holds under that condition, and any comparison must
  hold the state constant. A claim on this line that the audit was "not
  reproducible" was itself wrong and is withdrawn; it rested on misreading a
  `ps` line for a vision model's runner as this one's.
  **Clause (3) is the only one missing, and it has never fired** — zero
  `not_checkable` in all seventeen runs, in both states. Not a filtering
  failure: the opinions *are* listed, and land in `unsupported`, one verdict
  over. The prompt splits those two by a question — is this a factual claim at
  all? — that it never told the model to ask first, and listed `not_checkable`
  last, after an `unsupported` whose definition already presupposes the answer.
  **ADR-024 decides that checkability gates the other three verdicts.** Its §1
  and §2 stand; **its §3 — that the prompt's verdict *order* was the cause — was
  measured on its own and is falsified.** Condition B (four draws, both states,
  `probe/b6/condition-b-*.json`) produced zero `not_checkable` and **lost all
  three cross-side `contradicted` verdicts in the warm state**, the regression
  ADR-024 §5 named in advance. The reorder is reverted; the artifacts stay.
  **Condition C then rewrote the user turn** — it said "Audit this debate's
  factual claims", pre-filtering from the last position the model reads, against
  the system prompt's "Filter nothing out" — and was **also reverted**: still
  zero `not_checkable`, and the warm ledger collapsed from 20 claims to 5.
  **Clause (3) has now never fired in 25 runs**, across three prompt variants
  and both load states, all on `qwen3:8b`.
  **That second reading is now confirmed, and it settles the question**
  (2026-09-15, `probe/b6/README.md`, seven judges on the gate transcript with
  load state held constant). **Clause (3) fires on `qwen3:4b` and `qwen3:14b`,
  on the exact two assertions `qwen3:8b` mis-files as `unsupported`.** So the
  prompt was never broken, and three reverted prompt conditions were tuning
  wording against a defect that moves with the judge. It is also **not a size
  threshold**: 4b does it, 8b does not, 14b does.
  **The obstacle has inverted.** No judge tested produces all three clauses —
  every working one returns exactly two, and which two varies by model *and by
  generation*: `qwen3:8b` warm and `qwen3.5:4b` get (1)+(2); `qwen3:4b` and
  `qwen3:14b` get (1)+(3); `qwen3:0.6b` and `1.7b` return one claim and cannot
  do the task; `qwen3:32b-16k` returned unparseable JSON twice, cold and warm.
  **Generation moves this more than size does**: `qwen3:4b` and `qwen3.5:4b`,
  identical parameter counts, return *opposite* clause pairs — and the newer
  one needed **five times the budget**, failing at 6000 with 23,149 characters
  of thinking and no answer. See `MODEL-COVERAGE.md`, which now carries
  generation as a column and the warning that **`JUDGE-VALIDATION`'s Tau-C
  result is pinned to `qwen3:8b` and does not transfer across generations**.
  The structural fix — a `factual` boolean in the claim schema, ADR-024 §2 as
  schema rather than prose — was built and measured on 2026-09-16 as **ADR-030,
  and is REVERTED**. Four draws under the protocol (`probe/b6/adr030-*.json`):
  **zero `not_checkable`, all three cross-side `contradicted` lost, and the
  ledger down from 20 claims to 16.** The prediction ADR-030 §7 recorded before
  the run was wrong on all three counts. The value judgement it targeted was not
  reclassified — it **vanished from the ledger**; one lost contradiction became
  `supported` citing the speaker's *own* passage. **That is now three channels
  and three identical failures** — verdict-list order (B), user-turn framing (C),
  and a required schema field (ADR-030): on `qwen3:8b` every change that
  foregrounds the checkability question trades away clause (2) and shrinks the
  ledger. **Clause (3) is not reachable on `qwen3:8b` by changing what we ask
  for**, and the option this file previously called "the live one" is closed.
  One real side effect, established by a **paired control** rather than
  inferred across days: all four ADR-030 draws were **byte-identical across the
  cold/warm boundary** (16 claims either way), while a cold draw on the
  *reverted* prompt the same day returned 11 claims hashing
  `2fddcc93b6f8afc0` — **byte-identical to the 2026-09-14 cold draw**. So
  nothing drifted, the 11/20 split persists on the unchanged prompt, and the
  reply schema is what removed the state sensitivity. It also makes the
  determinism result above stronger than stated: this audit reproduces **to the
  byte across two days**, not merely within a session.
  **The most promising route left is `qwen3:14b`**, which already produces
  clause (3) stably in both states and needs only clause (2). Its failure is now
  characterised (`probe/b6/ladder-qwen3-14b.json`): it lists *both* halves of the
  `am-3`/`am-4` contradiction pair, cites both ids correctly, and marks each
  `supported`. The citation mechanics are exact; it never weighs a claim against
  the **opposing** side's passage — an ADR-019 precedence failure on a model
  ADR-019 was never measured on, and uninvestigated.
  **The gate FAILED at condition A** under the N=5 standard fixed before the
  runs (`probe/b6/baseline-a-d1..d5.json`): clause (1) 5/5, clause (2) 4/5 (the
  one miss is the cold draw), clause (3) 0/5. That result also retired the
  standard — five draws in an uncontrolled state is one cold draw and four
  identical warm ones, so B6's protocol is now two draws per state, cold and
  warm, which enumerates the space instead of sampling it. **An earlier claim here that ADR-019
  "traded clause (3) for clause (2)" is withdrawn**: the run that produced a
  `not_checkable` used a different transcript and its score file was not
  saved, so no before/after on one input exists and no trade was measured.
  The malformed-JSON problem that *did* vary was fixed separately by having
  the audit cite a turn number instead of transcribing coordinates. See
  `BUILD-GUIDE.md` B6 and `probe/b6/README.md` for the full ledger. **Open question 6 is answered for
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
  by default. **Published to TestPyPI on 2026-09-14**, version `0.1.0.dev0`
  (wheel + sdist): <https://test.pypi.org/project/debatebench/>. Verified by
  installing *from the index* into a fresh venv — `pip install debatebench`
  with `--index-url` pointing at TestPyPI and `--extra-index-url` at real PyPI,
  since TestPyPI does not mirror `httpx` or PyYAML — and then running a full
  debate and judge from that install, which is the gate clause that could not
  be tested until the package was on an index. **It reproduced the source-tree
  run's output exactly** (pro 100/100, con 91/100, winner `pro` on total, 15
  claims): same seed, same config, same scores across a packaging boundary,
  which is the first end-to-end determinism evidence this project has that
  spans build and publish rather than just two local runs. **Released to real PyPI as `0.1.0` on
  2026-09-16** per ADR-029: <https://pypi.org/project/debatebench/>. `pip
  install debatebench` works with no index flags. Published by **Trusted
  Publishing** from `.github/workflows/release.yml`, triggered by a *published*
  GitHub Release — **no PyPI token exists anywhere**, which is deliberate, two
  having already leaked here. The release built from the tagged commit, ran the
  suite there, uploaded, then installed from real PyPI into a clean virtualenv
  and ran both commands; verified again independently afterwards (wheel + sdist,
  `httpx>=0.28` and `pyyaml>=6.0` resolved, both console scripts, `0.1.0`
  reported by `package_version()`). A version can never be re-uploaded, so a bad
  release is yanked and superseded — never replaced (ADR-029 §6). The sdist deliberately ships the whole internal
  record — every ADR, this file, `BUILD-GUIDE`, `OPEN-QUESTIONS`,
  `JUDGE-VALIDATION`, both probe write-ups — decided knowingly, on the grounds
  that the ADRs *are* the spec. It was scanned for personal data first: no home
  paths, no hostname, no private addresses; the only email is the package
  author field.
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
  `prep` takes no suffix; no space after the colon; **a bare entry asks for
  `medium`** and is resolved to it at load, so `opening` and `opening:medium`
  are the same run and every non-prep turn records a length — ADR-022),
  per-team
  **`side` (`pro` or `con`, required, one of each — ADR-007 §7)**, `model`,
  **`base_url` (required, no default — see ADR-007)**, `budget`
  (per-phase cap, completion tokens), `prep_budget` (required iff `"prep"`
  is in `phases`; a validation error either way if it's set without `prep`
  present, or missing while `prep` is present), `sources`, `seed` (optional —
  generated and recorded in the transcript if omitted, never silently
  guessed-and-hidden), and a **required** `output` path. Exactly two entries
  in `teams:`. An **optional `judge:` block** (ADR-020) carries the judge's
  `model`, `base_url`, `budget`, `output`, an optional `fact_check`, and an
  optional **`transcript`** naming what it reads (ADR-020 §7; defaults to the
  run's `output:`) — read by `judge`, validated but never acted on by `debate`.
  Its `output` may equal neither its own `transcript` nor the run's `output`
  (ADR-020 §6). ADR-007 removed a `judge:` block on the
  grounds that nothing read it; this one is read.
- `teams/*.yaml` — durable persona files (`id`, `name`, `voice`, `stance`,
  `corpus`, `values`), **hand-authored for now** (see ADR-006 — no
  PersonaForge/PersonaKit dependency exists yet; the earlier "compatible"
  claim was checked and found false). **No `model` or `budget` field here,
  ever** — that's a run-time concern, not identity.

Validation is strict (ADR-007 §6): unknown or duplicate keys are errors, phase
names come from a fixed list, and paths resolve from `run.yaml`'s directory.
Load YAML only through the package's strict loader, never plain `safe_load`
(ADR-008 lists the YAML 1.1 coercions it blocks).

`debate` takes the path to a `run.yaml`, plus ADR-021's override flags:
`--model` and `--budget` set both sides, `--pro-model`/`--con-model`/
`--pro-budget`/`--con-budget` set one. Giving both forms of one setting is an
error — there is no precedence rule. **Nothing else is overridable**: no
`--output` (Hard Rule 7 names its absence), no `--seed` (omit `seed:` and one is
generated and recorded), no `--base_url`, `--topic` or `--phases` (those make it
a different debate). An override changes the loaded config before the run, so
ADR-005's snapshot records what actually spoke. `judge` takes **either** that same `run.yaml`, reading its
`judge:` block and taking the transcript from `output:`, **or** a transcript
path plus `--model`, `--base-url`, `--budget` and `--output`, with
`--fact-check` / `--no-fact-check` (default on). The two are told apart by
extension, and **flags override the block** (ADR-020 §3–4), so an A/B needs no
edit: `judge run.yaml --model phi4-mini:latest`. The overridden value is what
the score file records, never the file's.

**ADR-007 §1's "the asymmetry is deliberate" no longer describes the tool.**
It was argued when `judge` had one flag; it now has four, and ADR-020 records
why that reversed. `debate` still has no override flags — adding them would
touch Hard Rule 7 and needs its own ADR.

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
test, and live-model tests opt-in behind `DEBATEBENCH_LIVE_TESTS=1`. Python ≥
3.11 (ADR-008). **CI exists as of 2026-09-16** — `.github/workflows/tests.yml`
runs the default suite on 3.11 and 3.12 against the fake backend, which
discharges ADR-004's "deferred to B7" clause while keeping its reason: a hosted
runner has no Apple Intelligence and no Ollama, so live tests never run there.
The repository is <https://github.com/robert-e-roy/debatebench> (public, MIT),
with `box` kept as a second remote for backup per the workspace convention.
