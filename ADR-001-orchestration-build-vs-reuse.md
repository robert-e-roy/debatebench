# ADR-001: Debate Orchestration Layer — Build vs. Reuse

**Status:** Accepted
**Date:** 2026-09-10
**Amended:** 2026-09-11 — rationale wording and cross-references corrected against
the R0 results; the decision itself is unchanged.
**Context session:** R0 repo review (aragora-debate, arbgjr/multi-agent-debate,
paolodalprato/agent-discussion-arena, rd-serendipity/ai-debate-arena). The brief and
full results are in this repo, as `R0-repo-review-session.md` and `R0-RESULTS.md`
(moved from `~/Projects/DebateKit/` on 2026-09-11); scores cited below come from
the latter.

## Decision

Build our own orchestration layer from scratch (~400–500 lines, zero required
dependencies). Do not adopt or fork any of the four reviewed projects. Lift three
narrow, attributed pieces; take three design ideas; design against four observed
anti-patterns.

"Zero required dependencies" applies to the orchestration layer itself — the phase
loop, event dispatch and backend `Protocol` that R0 sized at ~400–500 lines. Config
parsing sits outside that layer and can't be stdlib-only (ADR-002's config is YAML,
and Python's standard library has no YAML parser). The HTTP adapter can stay
stdlib-only (`urllib` under `asyncio.to_thread`, which anti-pattern 4 below permits)
or take an async client; ADR-003 leaves that open.

## Why

None of the four reviewed projects fits, and not for one shared reason. Two
(`aragora-debate`, `arbgjr/multi-agent-debate`) are built to make agents converge
toward agreement, and in both that objective is hardcoded into the turn loop
itself, not exposed as a setting (R0 consensus-separation scores 2/5 and 1/5).
`rd-serendipity/ai-debate-arena` has no consensus logic at all (5/5) but engineering
we can't build on. `agent-discussion-arena` has no importable orchestration code at
all. Our requirement — sustained, non-converging adversarial debate with per-side
model/budget asymmetry — is not a configuration difference from consensus-seeking;
it's the opposite objective.

The clearest single data point: the project with the best engineering
(`aragora-debate` — clean `Agent` ABC, excellent standalone event system, verified
MIT license) has the worst fit on the one axis that matters most, separation from
consensus machinery (2/5). The project with the best fit on that axis
(`rd-serendipity`, true 1v1, no consensus logic anywhere) has the worst engineering
— LangChain-bound to September 2024 pins, fully synchronous, dead two years, no
tests. Nothing scored well on both. That is the whole decision.

## What we take (with attribution — all four repos are MIT)

| From | What | Form |
|---|---|---|
| `aragora-debate/events.py` | Typed `EventType` enum + `DebateEvent` dataclass, sync+async dispatch, per-callback exception isolation | Design lift, ~120 lines, reimplemented |
| `arbgjr/multi-agent-debate` `protocols.py` | Single-method `async generate(...)` `Protocol` as the LLM backend seam (not a multi-method ABC) | Design lift, ~20 lines |
| `aragora-debate/evidence.py` | Stdlib-only, LLM-free, five separately-scored dimensions (citation density, specificity, evidence diversity, temporal relevance, logical chain) | Conditional lift — see the fact-checker bullet under "Decisions this locks in" on naming (R0 flag #5) |
| `paolodalprato/agent-discussion-arena` | Phase model: `Opening → Round 1..N → Verdict`, verdict as a distinct terminal phase, not a vote folded into the loop | Idea only, no code |
| `paolodalprato/agent-discussion-arena` | One `openai-compatible` adapter with configurable `base_url` serves MLX (`mlx_lm.server`), Ollama, LM Studio, and OpenAI itself | Idea only, no code |
| `rd-serendipity/ai-debate-arena` | Alternating initiative — swap who opens each round so neither side keeps first-mover advantage | Idea only, ~2 lines when implemented |

## Anti-patterns to design against (each observed as a real bug in a reviewed repo)

1. **Never let a phase failure be silent.** Aragora's `_run_propose`/`_run_vote` use
   `return_exceptions=True` and `continue` past a failed side with only a log
   warning; `_pick_winner` then defaults to `agents[0]`, so a one-sided debate
   still emits a confident-looking result. **Our rule: every phase must produce a
   response from every configured side, or the run hard-fails and `--output` is
   not written.**
2. **Never key transcript state by side alone.** Aragora's `_proposals` dict is
   overwritten each round, so `result.proposals` only ever holds the final round.
   **Our rule: key all transcript state by `(round, side)`.**
3. **Never blend judge dimensions into one number, and never return 0 on a parse
   failure.** rd-serendipity's judge asks for a single 0–100 score blending
   relevance, coherence, and fact-check, parsed by `RegexParser(r"(\d+)")`, which
   grabs the *first* integer anywhere in the output — a reply starting "Criteria
   1..." scores 1 — and returns 0 on any parse failure, indistinguishable from a
   genuinely terrible argument. **Our rule: score rubric dimensions separately;
   treat a parse failure as an error, never a score.**
4. **Never call a synchronous SDK client inside `async def`.** All four of
   Aragora's provider agents construct sync clients (`anthropic.Anthropic`,
   `openai.OpenAI`, etc.) and call them directly inside `async def` with no
   `await` and no `asyncio.to_thread` — so `asyncio.gather` across agents
   delivers zero real concurrency and blocks the event loop. For a tool also
   driving a live dashboard, this would stall the UI. **Our rule: use a real
   async client, or wrap sync calls in `asyncio.to_thread`.**

## Decisions this locks in (changes/sharpens the prior plan)

- **Two commands (`debate` / `judge`) stays as designed.** Aragora's fusion of
  judging into the debate loop is exactly what forces its wasted vote-phase calls.
  No reviewed project argues for merging the two.
- **`debate` writes to `--output` file only stays as designed.** No conflicts
  found. Aragora's `DebateResult.to_dict()` + `DecisionReceipt.to_markdown()` is a
  reasonable precedent for pairing a machine-readable and human-readable view of
  one run in the output schema.
- **Phases must be data, not control flow.** Both Aragora and arbgjr hardcode
  their phase sequence as literal branches in the loop body — Aragora even has a
  `Phase` enum its own loop ignores, with two dead members. **Our loop iterates a
  list of phases; it does not branch on round number.**
- **Per-side budgets are enforced by the orchestrator, per phase — not by each
  backend's constructor.** Aragora's `max_tokens`/`temperature` are genuine
  per-agent constructor args, but every provider's `vote()` hardcodes its own
  512-token, 0.3-temperature budget regardless of what was configured, so the
  configured budget silently doesn't hold across every phase. For a benchmarking
  tool, an unenforced budget claim is worse than no budget claim.
- **Fast fact-checker vs. slow end-of-debate judge split is vindicated.** No
  reviewed project implements this separation. Aragora's `evidence.py` is the
  nearest analogue but is pure regex over surface form (citation patterns, data
  patterns, vague-vs-specific phrasing) with zero LLM calls and zero verification
  of truth — a confidently fabricated citation with a recent year and a
  percentage scores *high*. **If adopted, it is labeled "evidence hygiene," not
  "fact-check," and sits alongside a real fact-checker, never in place of one.**
- **New invariant, not previously in the plan:** every phase must produce a
  response from every configured side, or the run aborts and no output file is
  written. (See anti-pattern 1.)

## Consequences

- We own and maintain the full orchestration loop (~400–500 lines). No external
  dependency risk from a project whose roadmap has nothing to do with ours.
- We do not get Aragora's four cloud-provider integrations for free, but we didn't
  want them as the primary path anyway (MLX-first).
- Building the `Agent`/backend seam as a single-method protocol (per arbgjr's
  shape) keeps an MLX implementation to one method rather than three, avoiding the
  work an Aragora-based `Agent` subclass would require (structured `Critique`/
  `Vote` parsing out of a local model).
- Attribution required in our source/NOTICE file for the two design lifts
  (`events.py` shape, `LLMProviderProtocol` shape) and the conditional
  `evidence.py`-derived evidence-hygiene scorer, per each project's MIT license.
