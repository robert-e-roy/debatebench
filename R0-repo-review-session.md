# Session R0: Debate-Orchestration Repo Review

## Purpose

Before writing any orchestration code for the debate app's Python CLI
(`debate` / `judge`), determine whether any existing open-source project
is worth depending on or forking from, versus building the orchestration
layer from scratch. This is a research/decision session — no package
code gets written yet. Output is a `RESULTS.md` with a clear
recommendation per repo and an overall GO/NO-GO/HYBRID call.

## Repos to review

1. **aragora-debate** (PyPI) — https://pypi.org/project/aragora-debate/
   - Also check both of these, they may or may not be the same project:
     - https://github.com/an0mium/aragora
     - https://github.com/synaptent/aragora
   - Confirm which GitHub repo (if either) actually backs the PyPI package.
2. **multi-agent-debate** — https://github.com/arbgjr/multi-agent-debate
3. **agent-discussion-arena** — https://github.com/paolodalprato/agent-discussion-arena
4. **ai-debate-arena** — https://github.com/rd-serendipity/ai-debate-arena

## For each repo, determine

**Provenance & health**
- Actual license (full text, not just the badge) — is it MIT/Apache-2.0
  compatible with an open-source tool we intend to publish, and with a
  paid App Store app that may embed a ported Swift version later?
- Last commit date, commit frequency over the last 6 months, single
  maintainer vs. team, open issue/PR backlog — is this alive or
  abandoned-looking?
- Any indication of a broader commercial platform behind it (as with
  Aragora) that could mean API churn driven by a roadmap unrelated to
  our use case.

**Architecture**
- Read the actual orchestration loop source (not just the README).
  How is a "turn" or "round" represented? Is it phase-aware (opening/
  rebuttal/etc.) or just N generic rounds?
- Is there an `Agent`-style abstraction that cleanly wraps an arbitrary
  LLM backend (including a local MLX model), or is it tied to specific
  cloud providers?
- Is there an event/streaming system for real-time updates per turn?
  If so, is it decoupled enough to reuse just for our live fact-check
  panel and hardware dashboard, without pulling in unrelated features?
- Is consensus/voting/convergence logic (if present) cleanly separable
  from the turn-taking and agent-wrapping code, or tangled throughout?
  We need adversarial, non-converging debate — anything that nudges
  toward agreement needs to be strippable or ignorable.
- Does it support independent per-side constraints (different models,
  different token/reasoning budgets per side)? Most of these are
  built for N-agent consensus, not asymmetric 1v1 — note if this
  requires real rework.

**Fit assessment**
- Score each repo 1-5 on: reusability of Agent/turn abstraction,
  reusability of event system, cleanliness of separation from
  consensus-specific logic, license compatibility, maintenance health.
- Explicit note: does using this as a dependency (or fork base) save
  meaningfully more time than writing our own thin orchestration loop
  from scratch, given our requirements are fairly specific (phases,
  per-side budgets, steelman scoring, fact-checking, MLX-first)?

## Output

Produce `RESULTS.md` with:
- One section per repo: provenance/health findings, architecture
  findings, fit score, and a one-paragraph verdict (reuse-as-dependency /
  fork-and-strip / read-for-ideas-only / avoid).
- A final recommendation: build our own orchestration layer from
  scratch, adopt one repo as a dependency, or fork+strip one repo as a
  starting point — with reasoning.
- Flag anything that changes the CLI/package plan already settled
  (two commands, `debate` writes to `--output` file only, phase
  structure, per-side model+budget, separate fast fact-checker vs.
  slower end-of-debate judge) rather than assuming it silently.

## Out of scope for this session

- No package code, no dependency installation into our own project yet.
- No naming/licensing decisions for our own package (`debatekit` /
  `debatebench`) — that's already settled separately.
- No UI or dashboard work.
