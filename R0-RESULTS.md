# Session R0 Results: Debate-Orchestration Repo Review

**Date:** 2026-09-10
**Scope:** Research/decision only. No package code written, no dependencies installed.
**Method:** PyPI JSON API + sdist download, GitHub API (metadata, trees, commit history,
issue sampling), and direct reading of orchestration source. Clones/sdists were extracted
to a scratchpad, not into this repo.

---

## Headline

**Recommendation: BUILD OUR OWN orchestration layer.**
In the brief's GO/NO-GO/HYBRID vocabulary this is a **HYBRID, at the weak end** — and the
distinction matters, so it is worth one sentence. It is NO-GO on both adoption
mechanisms the brief offered: nothing is worth taking as a dependency, and nothing is
worth forking as a base. What survives is three small attributed MIT lifts (~250 lines,
none of them the turn loop) plus three design ideas. Every architectural decision, and
the orchestration loop itself, is ours.

The single most important finding: **all four projects are built to make agents agree.**
Three of the four treat consensus as the *goal* of the debate, and the fourth has no
orchestration library at all. Our requirement is sustained, non-converging adversarial
debate with per-side asymmetry. That is not a configuration difference — it is the
opposite objective, and it sits in the middle of every turn loop reviewed.

---

## Repo-by-repo findings

### 1. aragora-debate — the only serious candidate

**Provenance — the PyPI/GitHub question, resolved.**

The brief asked which GitHub repo backs the PyPI package, and whether the two GitHub
URLs are the same project. Answer:

- `github.com/an0mium/aragora` returns **HTTP 301 → `github.com/synaptent/aragora`**.
  They are one repo; `an0mium` is a stale owner slug that GitHub still redirects.
  The GitHub API resolves `repos/an0mium/aragora` to `full_name: synaptent/aragora`.
- PyPI `aragora-debate` declares `Repository = .../an0mium/aragora/tree/main/aragora-debate`
  — i.e. the package is **a subdirectory of the monorepo**, not a standalone repo.
  That subdirectory still exists and still declares `version = "0.2.3"`.
  So: same project, no fork, no name squatting.
- **Verified by diff, not by version string.** Four commits touched `aragora-debate/`
  *after* 0.2.3 shipped with no version bump, so "same version" would not have implied
  "same code". Diffing the published sdist against monorepo HEAD: `debate.py`,
  `agents.py` and `arena.py` are **byte-identical**, and `pyproject.toml` differs in
  **only the five project URLs** (`an0mium` → `synaptent`). So `pip install
  aragora-debate==0.2.3` does give you the code on GitHub today, and the
  `claude-sonnet-4-5-20250929` default cited below is current — the April
  "Opus 4.6 → 4.7" sweep did not reach this package's source.
- Minor tell: the monorepo fixed the stale slug in June 2026
  (`fix(public): correct legacy an0mium/aragora slug in Python packaging metadata` #7708),
  but PyPI 0.2.3 still carries the old URLs — confirming no release since.

**License.** Verified full text, not the badge: the `aragora-debate/` subdirectory
carries **its own unmodified MIT LICENSE** ("Copyright (c) 2026 Aragora Contributors").
`dependencies = []`; all four provider SDKs are optional extras. Clean for an
open-source tool and for a later Swift reimplementation — MIT permits both, and there is
no vendored third-party code in the package tree to complicate it.

**Health — the 1051 open issues, characterized.**

This is the "broader commercial platform" risk the brief asked about, and it is real,
but it is not what the raw numbers suggest:

| Signal | Value |
|---|---|
| Repo age | Created 2026-01-01 (~8 months) |
| Pull requests | **10,053** |
| Peak commit rate | **2,338/week**; current ~13–79/week |
| Open issues | 1,051, sampled 100: **99 from just two accounts** (`scarmani`, `an0mium`) |
| Issue labels | `triage:protected`, `stage-gate-drift`, `contract-drift`, `research-intake`, `governance` |
| Languages | Python 221 MB, TypeScript 31 MB, **Go, Solidity, HCL/Terraform, PLpgSQL** |

~37 PRs/day from two accounts, with issue titles like *"Salvage: settlement preflight
verdict taxonomy (from PR #8992)"* and *"EPIC: Receipt-First Mission"*, is an
**autonomous-agent-driven development process on a broad commercial platform** —
enterprise metering, governance gates, dashboards, smart contracts, infrastructure.
The 1051 issues are not a human community backlog; they are machine-generated work
tracking. Treat the number as a signal of *churn velocity*, not of neglect.

**The twist: the subpackage itself is dormant.** Commits touching `aragora-debate/`:

```
2026-06-04  docs: scrub hardcoded private paths and legacy repo slug
2026-06-04  fix(public): correct legacy an0mium/aragora slug in packaging metadata
2026-04-22  test(aragora-debate): avoid tests package collision
2026-04-17  chore(models): replace Claude Opus 4.6 with 4.7 throughout the codebase
```

Last substantive change: **2026-04-22**. Last PyPI release: **2026-02-24**. So the
package has been frozen for ~5 months while the surrounding platform ran at thousands of
commits per month. That cuts both ways: low churn risk if we pin, but **no responsive
maintainer** for a subpackage nobody has touched, and the one change that did reach it
(`replace Claude Opus 4.6 with 4.7 throughout the codebase`) was platform-roadmap churn
sweeping through, not debate-engine work — exactly the failure mode the brief flagged.

**Architecture — read from source, not the README.**

The turn loop (`arena.py::run`) is genuinely clean:

```
for round in 1..N:
    propose  (all agents, asyncio.gather)
    [convergence check]  [trickster check]
    critique (each agent critiques every other's proposal, O(N²))
    vote     (all agents)
    evaluate_consensus -> early-stop if reached
```

- **Phase-aware, but the wrong phases, and hardcoded.** A `Phase` enum exists
  (`PROPOSE/CRITIQUE/REVISE/VOTE/CONSENSUS`) but the loop body ignores it — the sequence
  is literal control flow in `run()`. `REVISE` and `CONSENSUS` are dead enum members.
  There is no way to express opening/rebuttal/closing without editing `run()`.
- **Agent abstraction is good.** `Agent` is an ABC with three async methods
  (`generate`, `critique`, `vote`), documented as pluggable for "local models". Each
  agent carries `stance` (`affirmative`/`negative`/`neutral`), injected as a system-prompt
  suffix.
- **Per-side model and budget: supported, but it leaks.** `max_tokens` and `temperature`
  are per-agent constructor args — genuine asymmetry. **But `vote()` hardcodes a 512-token,
  0.3-temperature budget in all four provider classes** (`max_tokens=512` in Claude/OpenAI/
  Mistral, `max_output_tokens=512` in Gemini), so a configured
  budget silently does not hold across every phase. Design lesson for us below.
- **Event system: excellent and genuinely decoupled.** `events.py` is a standalone,
  stdlib-only `EventEmitter` — typed `EventType` enum, `DebateEvent` dataclass, sync
  *and* async callbacks, per-callback exception isolation. It imports nothing from the
  rest of the package. This is directly reusable for our live fact-check panel and
  hardware dashboard.
- **Consensus is NOT separable.** `_run_vote` runs unconditionally every round;
  `_evaluate_consensus` and `_pick_winner` determine `final_answer`. There is no
  "run the debate, give me the transcript" path. Setting `early_stopping=False` stops
  the early exit but still pays for a full vote phase every round — with 2 agents × 3
  rounds that is **6 discarded LLM calls, one-third of all calls in the debate**.
  (Convergence and trickster *are* cleanly separable, and this was import-verified rather
  than assumed: `evidence.py` imports **stdlib only**, `cross_analysis.py` imports only
  `evidence`, and `trickster.py` imports only those two. Nothing in that subtree imports
  `arena` or `types`, and arena passes the trickster plain arguments
  (`responses`, `convergence_similarity`, `round_num`). It is a genuinely self-contained
  subtree behind two opt-in flags.)

**Three defects found by reading the source:**

1. **The async is fake, and it blocks.** All four agents construct *synchronous* clients
   (`anthropic.Anthropic`, `openai.OpenAI`, `Mistral`, `genai.Client`) and call them
   directly inside `async def` with no `await` and no `asyncio.to_thread`. There is no
   `AsyncAnthropic`/`AsyncOpenAI` anywhere in the file. The `asyncio.gather` in
   `_run_propose` therefore delivers **zero concurrency and blocks the event loop** — a
   "parallel" propose phase runs fully serially. For a tool that also drives a live
   dashboard, this would stall the UI.
2. **Silent side-dropping.** `_run_propose` and `_run_vote` use `return_exceptions=True`
   and `continue` past failures with a `logger.warning`. A debate can proceed — and
   produce a confident-looking receipt — with one side missing entirely.
   `_pick_winner` then falls back to `self.agents[0].name`, so side A silently "wins".
   For a benchmark tool this is worse than crashing.
3. **Convergence detection is lexical, not semantic.** `ConvergenceDetector` uses
   `difflib.SequenceMatcher.ratio()`. Two proposals that agree in substance but differ in
   wording score *low*; two that differ in substance but share boilerplate score *high*.
   It is stdlib-only (consistent with zero-dep) but a weak proxy for the "hollow
   consensus" it advertises, and `ratio()` is O(n²) on multi-KB proposals.

**Fit scores**

| Axis | Score | Note |
|---|---|---|
| Agent/turn abstraction | **4/5** | Clean ABC + stance + per-agent budgets; phases hardcoded, 3 methods to implement |
| Event system | **5/5** | Standalone, stdlib-only, sync+async — best artifact in this review |
| Separation from consensus | **2/5** | Vote phase unconditional; `final_answer` derived from voting |
| License compatibility | **5/5** | Own MIT file verified; zero required deps; SDKs optional |
| Maintenance health | **2/5** | Subpackage dormant 5 months inside a 10k-PR agent-driven platform |

**Verdict: read-for-ideas-only, with two narrow lifts (`events.py`, `evidence.py`).**
The best-engineered code here, and the only one whose *stated* goal (adversarial debate,
hollow-consensus detection) matches ours. But adoption would mean inheriting a hardcoded
propose/critique/vote loop we would have to fight, paying for a vote phase we discard,
writing a full three-method `Agent` subclass for MLX anyway (see below), and depending on
a dormant subdirectory of a platform churning at thousands of commits a month on an
unrelated enterprise roadmap. Lift `events.py`'s design; leave the rest.

**MLX blocker worth stating plainly:** `OpenAIAgent` hardcodes
`openai.OpenAI(api_key=...)` with **no `base_url` parameter** (`**kwargs` goes to
`super().__init__`, not to the client). So we could not simply point it at
`mlx_lm.server`, Ollama or LM Studio. MLX support would require a custom `Agent`
subclass implementing `generate`, `critique` *and* `vote`, including parsing structured
`Critique` and `Vote` objects out of a local model — real work, not configuration.

---

### 2. arbgjr/multi-agent-debate — clean protocol, wrong objective, abandoned

**Provenance & health.** MIT verified (unmodified, "Copyright (c) 2025 Armando Jr").
**A single commit, ever** (2025-12-29, `feat: initial Multi-Agent Debate package
implementation`). Single author. **Not on PyPI — `/pypi/multi-agent-debate/json` returns
404**, despite the README presenting it as a package; adopting it would mean a git
dependency or vendoring. ~52 KB of source. Tests exist for `bayesian`, `config` and
`models` — **but not for `orchestrator.py` or `argument.py`**, the two files that
actually matter.

**Architecture.** The genuinely good part is `protocols.py`:

```python
class LLMProviderProtocol(Protocol):
    async def generate(self, prompt: str, *, system_prompt: str | None = None,
                       temperature: float = 0.7, max_tokens: int = 2048) -> str: ...
```

A `runtime_checkable` Protocol, `dependencies = []`, and **no provider imports anywhere
in the package** (grep for `openai|anthropic|litellm|ollama|mlx|httpx` returns nothing).
This is the cleanest MLX-compatible seam of the four — one method to implement, versus
aragora's three.

Everything else is anti-aligned with our requirements:

- **Consensus is the purpose, not a mode.** `should_trigger_debate()` only debates when
  confidence is *low*; the round loop breaks early on `has_reached_consensus()`;
  `_calculate_round_agreement()` *rewards* synthesis and concessions; and
  `_synthesize_final_answer()` merges everything into one answer with the instruction
  *"Do not mention the debate process itself."* Adversarial non-convergence would require
  deleting the reason the code exists.
- **Not phase-aware.** Round 0 is a hardcoded claim→counter→rebuttal; rounds 1+ are
  generic "new claim + counter". `ArgumentType` (CLAIM/COUNTER/REBUTTAL/CONCESSION/
  SYNTHESIS) is an argument taxonomy, not a phase schedule. No opening or closing.
- **No per-side anything.** One `self._llm` serves every agent. Agent identities are
  hardcoded strings (`advocate-1`, `critic-1`, `advocate-2`). Config exposes temperature
  per *role*, not per *side*; `max_argument_length` is global. Asymmetric 1v1 is a
  rewrite, not a setting.
- **No event system at all** — `logger.info` only.

**Latent defects:** votes are keyed on `position=arg.text[:100]` — truncated free text as
a tally key, so votes essentially never match and the Bayesian layer is built on a key
that cannot collide meaningfully. `consensus_result if "consensus_result" in dir() else None`
is a fragile idiom that can leave the name unbound. `datetime.utcnow()` is deprecated on
the Python ≥3.12 it requires. `DebateRole.JUDGE` is defined and never used;
`config.get_temperature_for_role()` is dead code the orchestrator bypasses with
hardcoded literals.

| Axis | Score | Note |
|---|---|---|
| Agent/turn abstraction | **3/5** | Protocol is the best MLX seam here; turn loop unusable |
| Event system | **1/5** | None |
| Separation from consensus | **1/5** | Consensus *is* the product |
| License compatibility | **5/5** | MIT verified, zero deps |
| Maintenance health | **1/5** | One commit ever, not on PyPI, core files untested |

**Verdict: read-for-ideas-only.** Take the shape of `LLMProviderProtocol` (~20 lines,
and we would write something equivalent regardless). Take nothing else.

---

### 3. paolodalprato/agent-discussion-arena — right phase model, no library

**Provenance & health.** MIT verified ("Copyright (c) 2026 Paolo Dalprato"). Single
author, **11 commits over 8 days** (2026-03-24 → 2026-04-01), silent for 5 months. No
package, no PyPI, no tests.

**Architecture.** GitHub reports the repo as HTML for a reason: **the entire application
is one 78 KB `index.html`** containing a React app, plus `proxy-server.py` (15 KB) which
is purely a loopback-bound CORS relay and PDF extractor — it contains **no orchestration
whatsoever**. There is nothing importable from Python. As a dependency or fork base for a
Python CLI, this is a non-starter.

Two ideas in it are nonetheless the most relevant in the whole review:

- **The phase model is the closest to our plan.** `Opening Statements` → `Round 1..N` →
  `Verdict`, with `parallelPhaseCount = 1 + rounds`. Openings fire in parallel
  (`Promise.all`), rounds run sequentially, and the verdict is a distinct terminal phase —
  not a vote folded into the loop. This is the shape we described, implemented by
  someone else, and it validates separating the judge from the debate.
- **One `openai-compatible` provider with a configurable `base_url` covers all local
  models.** The UI offers `OpenAI-Compatible (Ollama, LM Studio...)` with a
  `http://localhost:11434` placeholder, and `call_openai(..., base_url=None)` simply
  swaps the host. Since `mlx_lm.server` also speaks the OpenAI chat-completions shape,
  **a single adapter can serve MLX, Ollama, LM Studio and OpenAI itself.** This is the
  most useful transferable idea for our MLX-first requirement, and it is exactly the
  parameter aragora omits.

**Limitations against our requirements:** a **single global `config.model`** drives every
participant (`model: config.model` at both call sites) — participants differ only by
persona and system prompt, so **per-side models are impossible**. `max_tokens: 4096` is
hardcoded in the proxy, so no per-side budgets. It is N-participant multi-perspective
discussion (the demo runs three personas), not 1v1. And it has no event system — just
React `setPhases` state.

| Axis | Score | Note |
|---|---|---|
| Agent/turn abstraction | **1/5** | React inside a single HTML file; nothing importable |
| Event system | **1/5** | React state, not an event system |
| Separation from consensus | **4/5** | No consensus machinery to tangle — but nothing to reuse either |
| License compatibility | **5/5** | MIT verified |
| Maintenance health | **2/5** | 11 commits in 8 days, then 5 months silent; no tests |

**Verdict: read-for-ideas-only.** Take the phase model and the `openai-compatible
base_url` adapter idea. There is no code to take.

---

### 4. rd-serendipity/ai-debate-arena — right shape, wrong stack, two years dead

**Provenance & health.** MIT verified ("Copyright (c) 2024 rd-serendipity").
**Two commits**, 2024-09-07 and 2024-09-12 — dead for two years. ~12.5 KB of Python
total. No tests. `requirements.txt` pins `langchain==0.2.16` and five `langchain_*`
provider packages at September-2024 versions.

**Architecture.** The smallest codebase in the review, and structurally the **closest to
what we actually want**:

- **True 1v1 adversarial, with no consensus logic anywhere.** `Debate(model_a, model_b,
  judges, topic, fighter_a_view, fighter_b_view)` — two fighters, each with an explicit
  assigned position. Nobody votes, nobody synthesizes, nobody is asked to agree.
- **Alternating initiative** — `if round_number % 2:` A argues then B counters; on even
  rounds B argues then A counters. A two-line fix for first-mover advantage, and a
  genuinely good idea we should adopt.
- **Per-side model, provider and temperature** — `model_a` and `model_b` are independent
  `AIModel` instances. Asymmetric by construction.
- **Judges are separate objects with their own model/provider/temperature**, as a panel
  whose scores are averaged. This is a direct precedent for our `judge` command.

**Why it is still unusable as a dependency:**

- **LangChain in every path.** `ai_model.py` and `judge.py` both import five
  `langchain_*` packages. Adopting this means adopting LangChain and its 2024 pins —
  the direct opposite of a zero-dependency, MLX-first tool.
- **Fully synchronous** (`chain.invoke()`), no concurrency, no streaming, no events.
- **`self.context` is an ever-growing string.** The entire transcript is re-sent as one
  blob every turn, with no truncation and no budget — token cost grows quadratically
  with round count and will eventually exceed the context window.
- **The judge is a per-round scorer, not an end-of-debate judge**, and its scoring is
  fragile in two specific ways worth recording: the prompt asks for a *single* 0–100
  number blending relevance + coherence + fact-check (no per-dimension breakdown), and
  `RegexParser(regex=r"(\d+)")` captures the **first integer anywhere in the output** — so
  a reply beginning "Criteria 1..." scores 1. On a parse failure `return_score` returns
  **0**, which is indistinguishable from a genuinely terrible argument.

| Axis | Score | Note |
|---|---|---|
| Agent/turn abstraction | **2/5** | Right shape (1v1, per-side, alternating) but LangChain-bound and sync |
| Event system | **1/5** | None |
| Separation from consensus | **5/5** | No consensus logic exists; adversarial by design |
| License compatibility | **5/5** | MIT verified |
| Maintenance health | **1/5** | 2 commits, dead 2 years, 2024-pinned LangChain, no tests |

**Verdict: read-for-ideas-only.** Take alternating initiative and the separate-judge
shape. Take none of the code.

---

## Summary scoring

| Repo | Agent/turn | Events | Consensus separation | License | Health | Verdict |
|---|---|---|---|---|---|---|
| **aragora-debate** | 4 | **5** | 2 | 5 | 2 | read-for-ideas + lift `events.py` |
| **arbgjr/multi-agent-debate** | 3 | 1 | 1 | 5 | 1 | read-for-ideas-only |
| **paolodalprato/agent-discussion-arena** | 1 | 1 | 4 | 5 | 2 | read-for-ideas-only |
| **rd-serendipity/ai-debate-arena** | 2 | 1 | **5** | 5 | 1 | read-for-ideas-only |

Note the diagonal: the repo with the best engineering (aragora) has the worst objective
fit on consensus separation, and the repo with the best objective fit (rd-serendipity)
has the worst engineering. Nothing scores well on both. That is the whole decision.

---

## Does adopting save meaningful time vs. writing our own?

Answered concretely, as the brief asks — what would we actually reuse?

**Only aragora is even a candidate**, so the comparison is against it specifically.

| Component | Reusable? | Our cost from scratch |
|---|---|---|
| `EventEmitter` | **Yes** — genuinely decoupled, stdlib-only | ~120 lines; we lift the design instead |
| Turn loop (`arena.py::run`) | **No** — hardcoded propose/critique/vote, wrong phases | ~150 lines for our phase-driven loop |
| `Agent` ABC | Partly — but no `base_url`, so MLX needs a full 3-method subclass | ~60 lines for a 1-method protocol |
| Voting / consensus / `_pick_winner` | **No** — must be bypassed, still costs ~⅓ of all LLM calls | n/a — we do not want it |
| `DecisionReceipt` / `to_markdown` | Ideas only — shape of the `--output` artifact | ~80 lines |
| `ConvergenceDetector` | Marginal — lexical similarity is a weak signal | ~40 lines if we want it |
| Provider agents | **No** — sync clients in `async def`; four copy-pasted classes | ~80 lines for one OpenAI-compatible adapter |

**The honest arithmetic:** adopting aragora saves us writing the event emitter and gives
us four cloud providers we mostly do not want. It costs us: an MLX `Agent` subclass with
three methods including structured `Critique`/`Vote` parsing (more work than our whole
provider seam), a vote phase we pay for and discard every round, a hardcoded phase
sequence we cannot express our debate structure in, a blocking-async defect to work
around, and a dependency on a dormant subdirectory of a 10,000-PR platform.

Our own thin loop is roughly **400–500 lines** of straightforward, fully-owned Python
with zero dependencies. Adoption does not save meaningfully more time than that, and it
imports risk we would carry indefinitely. **Build our own.**

---

## What to take (with attribution)

All four are MIT, so lifting is permitted with attribution retained.

**Two core code lifts:**
1. **aragora-debate `events.py` design** — typed `EventType` enum, `DebateEvent`
   dataclass, sync+async dispatch, per-callback exception isolation. Feeds the live
   fact-check panel and hardware dashboard directly. (~120 lines, MIT, attribute.)
2. **arbgjr `LLMProviderProtocol` shape** — a single `async generate(...)` Protocol as
   the backend seam, rather than a multi-method ABC. Keeps an MLX backend to one method.

**One qualified third lift:**
2b. **aragora-debate `evidence.py`** — stdlib-only, LLM-free, five separately-reported
   dimensions. Take it as a fast per-turn *evidence-hygiene* signal for the live panel,
   under an honest name. See flag #5: it does not verify facts and must not be presented
   as doing so. (MIT, attribute.)

**Three design ideas, no code:**
3. **paolodalprato's phase model** — `Opening → Round 1..N → Verdict`, with the verdict
   as a distinct terminal phase rather than a vote inside the loop.
4. **paolodalprato's `openai-compatible` + `base_url` adapter** — one adapter serves
   `mlx_lm.server`, Ollama, LM Studio and OpenAI. The highest-leverage idea for
   MLX-first, and precisely the parameter aragora omits.
5. **rd-serendipity's alternating initiative** — swap who opens each round so neither
   side keeps first-mover advantage. Two lines, real fairness gain for a benchmark.

**Four anti-patterns to design against**, each observed in code:
- Never let a phase failure be silent (aragora drops a side and still emits a confident
  receipt; `_pick_winner` then defaults to `agents[0]`). Our loop must hard-fail.
- Never key transcript state by side alone (aragora's `_proposals` dict is overwritten
  each round, so `result.proposals` holds only the final round). Key by `(round, side)`.
- Never blend judge dimensions into one number, and never return 0 on a parse failure
  (rd-serendipity does both). Score dimensions separately; make parse failure an error.
- Never call a sync SDK client inside `async def` (all four aragora agents). Either use
  the async client or `asyncio.to_thread`.

---

## Flags against the already-settled CLI/package plan

Per the brief, these are raised explicitly rather than assumed silently.

**1. Two commands (`debate` / `judge`) — no change; evidence strengthens the split.**
aragora fuses judging into the debate loop (a vote phase every round plus a receipt), and
that fusion is exactly what forces the ~⅓ wasted LLM calls when you do not want
consensus. rd-serendipity keeps `Judge` as a separate class with its own model and
temperature — closer to our plan. Nothing found argues for merging the two commands.

**2. `debate` writes to `--output` file only — no change.**
No reviewed project does this: aragora's `python -m aragora_debate` prints a formatted
report to stdout (flags `--topic/--rounds/--trickster/--convergence`, no `--output`), and
the others are a Streamlit app and a browser app. No conflict. Two useful inputs for the
artifact's *schema*: aragora's `DebateResult.to_dict()` + `DecisionReceipt.to_markdown()`
are a reasonable precedent for machine- and human-readable views of one run — and its
`proposals`-overwritten-per-round bug is a concrete warning to key our transcript by
`(round, side)`.

**3. Phase structure — no change; one design constraint sharpened.**
paolodalprato independently arrived at `Opening → Rounds → Verdict`, which validates our
structure. But both aragora and arbgjr **hardcode their phase sequence as control flow in
the loop body** (aragora even has a `Phase` enum its loop ignores, with two dead members).
Recommendation: make phases **data** — a list the loop iterates — not `if round == 0:`
branches. This is the single most reusable structural lesson from the review.

**4. Per-side model + budget — no change; one enforcement point moved.**
Supported by aragora and rd-serendipity, absent from arbgjr and paolodalprato. The
important finding is *how aragora's leaks*: budgets are constructor args on each agent,
but every provider's `vote()` hardcodes a 512-token, 0.3-temperature budget, so a
configured per-side budget silently fails to hold across every phase. **Enforce budgets
in the orchestrator, per phase, not in each backend's constructor** — otherwise our
per-side budget claim is unverifiable, which matters for a benchmarking tool.

**5. Fast fact-checker vs. slow end-of-debate judge — no change; the split is vindicated,
with one naming warning.**
**No reviewed project implements this separation.** The nearest analogue is aragora's
`evidence.py`, and having now read it rather than its export list, it needs a precise
description: `EvidenceQualityAnalyzer` is **pure regex over the response text with zero
LLM calls** — citation patterns (`[1]`, `(Author 2024)`, URLs), data patterns
(percentages, currency, timings), example markers, vague-vs-specific phrase lists, and a
year-based `temporal_relevance`. It scores five dimensions *separately*
(`citation_density`, `specificity_score`, `evidence_diversity`, `temporal_relevance`,
`logical_chain_score`) and only then combines them via an explicit weight map.

Two consequences for our plan:

- **It is a good precedent for dimension separation** and a genuinely cheap per-turn
  signal — stdlib-only and instant, which is the right cost profile for the live panel.
- **It is not a fact-checker, and we must not label it one.** It measures the *surface
  form* of evidence, not its truth. A confidently fabricated citation with a recent year
  and a percentage scores **high**. Adopting it under a "fact-check" label would put a
  reassuring number next to a false claim — the exact failure our two-tier design exists
  to prevent. If we use it, it belongs in the panel as an "evidence hygiene" score
  sitting *alongside* a real fact-checker, never as the fast tier itself.

The counter-example is instructive in the other direction: rd-serendipity's judge folds
fact-checking *into* a single 0–100 score alongside relevance and coherence, making a
factual error indistinguishable from an inelegant sentence. Our two-tier split is the
right call and nothing here challenges it.

**One item not in the plan, worth adding.** Nothing reviewed hard-fails when a side goes
missing. For a tool whose output is a benchmark, a silently one-sided debate that still
emits a confident verdict is the worst failure mode available. Recommend an explicit
invariant: every phase must produce a response from every configured side, or the run
aborts and `--output` is not written.

---

## Out-of-scope items confirmed untouched

No package code written; no dependencies installed into this project (the aragora sdist
and raw source files were fetched to a scratchpad for reading only). No naming/licensing
decisions revisited. No UI or dashboard work.

**Overall call: NO-GO on adoption and NO-GO on forking — a weak HYBRID in the brief's
terms. Build our own orchestration layer, taking the three attributed lifts and three
design ideas listed above.**
