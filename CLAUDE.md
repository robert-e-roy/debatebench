# CLAUDE.md — debatebench

Read `ADR-001` and `ADR-002` in full before making any architectural decision.
This file is the quick-reference; the ADRs are the actual spec, and take
precedence if anything here seems to conflict.

## What this project is

An open-source Python CLI (`debate`, `judge`) for running structured, multi-turn,
adversarial LLM debates and scoring them against a fixed rubric with real-time
fact-checking. Built to evaluate MLX model + dataset choices for a companion Mac
app, but scoped and built as a standalone, general-purpose tool — not app-specific
code. See ADR-002 for full scope.

## Documents and where work stands

- `ADR-001`, `ADR-002`, `ADR-003` (AFM via `fm serve`), `ADR-004` (test
  framework), `ADR-006`, `ADR-007` (`run.yaml` schema and CLI invocation),
  `ADR-008` (Python 3.11+, `httpx`, PyYAML), `ADR-009` (backend request and
  result types) — accepted; together they are the spec.
- `ADR-005` (transcript format) — **Proposed**, not yet accepted. Don't build on
  it until it is.
- `BUILD-GUIDE.md` — the session-by-session build plan (B0–B7), each session with
  an exit gate. **B0 is done** for the machine as used (`RESULTS.md`: the 8B+24B
  pair can't co-reside alongside normal workload; no concurrency was measured).
  The pair is unmeasured, not ruled out: a quiet-machine B0 rerun comes before
  anything trusts it. **B1 is done** (2026-09-11): config loading and
  validation, the backend seam (ADR-009) and the `openai-compatible` adapter,
  with its exit gate met, including a live reply from AFM. **Next: B2**, which
  first needs ADR-005 accepted, OPEN-QUESTIONS item 11 settled, and ADR-003's
  overshoot policy decided.
- `OPEN-QUESTIONS.md` — every undecided design question, with the build session
  each one blocks. Check it before starting a session, and don't pick a default
  for anything listed there.
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

## Hard rules (non-negotiable)

Rules 1–6 each trace to a real defect found in a reviewed competing project (see
ADR-001). Rule 7 predates that review (ADR-002, "CLI shape"); R0 found nothing
against it.

1. **Never let a phase fail silently.** Every configured phase must get a
   response from every side, or the run aborts and no file is written to
   `run.yaml`'s `output:` path. No default-to-first-side fallback, no
   `continue`-past-a-failure with just a log line.
2. **Key all transcript/state by `(round, side)`, never by side alone.**
   Overwriting per-round state is a real bug we found and are explicitly
   avoiding.
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
  for whether `prep` runs — no separate `prep`/`rounds` flags), per-team
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
- send budgets as `max_completion_tokens`, never `max_tokens`;
- check `usage.completion_tokens` against the budget yourself — `finish_reason`
  doesn't signal truncation.

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
