# ADR-002: DebateBench — Project Scope and Architecture

**Status:** Accepted
**Date:** 2026-09-11
**Supersedes:** nothing. **Depends on:** ADR-001 (orchestration build vs. reuse)
**Amended:** 2026-09-11 — cross-references, dataset facts and wording corrected. B0's
hardware findings added to "Hardware", withdrawing the `free` offload option. An
offline requirement for model servers added to "Backend abstraction".

## What this is

`debatebench` is an open-source Python CLI for running structured, multi-turn,
adversarial LLM debates and scoring them against a fixed rubric with real-time
fact-checking. It generalizes into a broader pattern (see the MetaTool notes,
`~/Projects/metatool.md`, outside this repo) but this ADR scopes the concrete first
implementation.

A Swift port, `DebateKit`, is a later, separate effort once this design stops
changing session to session (see "Language split" below). Not started yet.

## Why it exists

Built to evaluate MLX model + grounding-dataset combinations for a debate-format
Mac app, but scoped from the start to be generally useful for comparing LLMs on
structured, verifiable, multi-turn tasks — not tied to the app.

## Language split: Python first, Swift later

- **Python** owns everything exploratory: model/dataset evaluation, retrieval,
  rubric iteration, fact-checking logic. Mature ML tooling (`mlx-lm`, `datasets`,
  dataset ecosystem) makes iteration fast here.
- **Swift** (`DebateKit`, future) owns the shipped product: privacy-first,
  on-device, no bundled Python runtime, consistent with the rest of the
  HomesteadAI portfolio. Ported only once the CLI's design has stabilized —
  porting a moving target wastes the port.
- Publish both source repos on GitHub. Python side is a genuine standalone
  open-source tool (MIT). Swift side's license is a separate, later decision —
  likely source-available/non-commercial rather than MIT, since its purpose is
  auditability and trust for the paid app, not general reuse.

## Naming

- Python package: `debatebench` (PyPI name confirmed unclaimed as of this
  session). `bench` was chosen over `-cli` because it correctly signals
  "measures and compares models," matching existing conventions in this space
  (`lm-eval-harness`, similar `*-eval`/`*-bench` tools).
- Swift library (future): `DebateKit`, consistent with existing `Kit`-suffixed
  libraries (CorpusKit, JsonHelpKit).
- Neither collides with any of the ten-plus adjacent "debate"-named projects
  checked this session (`debate`, `aragora-debate`, `arbiter-debate`,
  `ai-debate-chat`, `multi-model-debate`, `autodebater`, `debating-machine`,
  and the four in the R0 review).

## CLI shape: two commands, not one

- **`debate`** — generates a transcript. Writes structured JSON to an explicit
  output file only — the required `output:` path in `run.yaml`, since `debate`
  takes no flags (ADR-007 "CLI invocation"). All logging/errors go to stderr, never to the
  output file — the file must always be valid, parseable JSON, never relying on
  shell redirection to keep it clean.
- **`judge`** — scores a transcript (from a file, not a pipe requirement) against
  the rubric plus fact-check. Kept separate from `debate` deliberately: lets the
  same transcript be re-judged with a different judge model, or re-scored after
  a rubric change, without regenerating the debate. (Aragora's fused
  debate+judge loop is a cautionary example — it burns a mandatory vote-phase
  call every round even when unwanted, precisely because judging isn't
  separable from generation in its design.)

## Config: two file types, different lifespans

**`run.yaml`** — one per debate run, ephemeral (schema finalized in ADR-007):
```yaml
topic: "..."
format:
  phases: [prep, opening, rebuttal, retort, rebuttal, conclusion]
teams:
  - team: teams/liberal.yaml
    side: pro
    model: qwen3-8b
    base_url: http://127.0.0.1:8080/v1
    budget: 2000
    prep_budget: 1500
  - team: teams/conservative.yaml
    side: con
    model: mistral-small
    base_url: http://127.0.0.1:8081/v1
    budget: 2000
    prep_budget: 1500
sources: [args-me, debatesum]
seed: 42
output: transcript.json
```

**`teams/*.yaml`** — durable, reusable, hand-authored for now (see ADR-006 —
the earlier "PersonaForge-compatible, zero conversion step" claim here was
checked against PersonaKit's actual schema and found false; aligning the two
is real future work, not started):
```yaml
id: liberal-climate
name: "Progressive Climate Advocate"
voice: "direct, urgency-driven, cites institutional consensus"
stance: liberal
corpus: sources/liberal-climate-corpus/
values: [collective-action, precaution, equity]
```

**Deliberately no `model` field in team files.** A team file defines identity
(voice, corpus, stance, values), not runtime execution. Keeping `model`/`budget`
in `run.yaml` as per-side overrides means the same team can debate under
different hardware/model constraints across different runs without editing its
identity file — that reasoning holds regardless of PersonaForge (see ADR-006).

## Phase structure

Phases are **data, not control flow** — the orchestration loop iterates a
configured phase list; it does not branch on round number in the loop body (both
`aragora-debate` and `arbgjr/multi-agent-debate` hardcode their phase sequence as
control flow — see ADR-001).

Default phase list: `[prep(optional), opening, rebuttal, retort, rebuttal,
conclusion]`. `prep` is a bounded-budget research phase — analogous to real
debate prep time — that produces a recorded, per-side evidence set *before* any
argument is written. This sharpens fact-checking: a claim is checked against what
a side actually gathered during its own prep, not an open-ended post-hoc search,
making "cited something you never had" a distinct, catchable failure mode from
"cited something real but misrepresented it."

Initiative (who goes first each round) alternates by design, so neither side
keeps a first-mover advantage across the whole debate.

## Asymmetry is a first-class feature, not an edge case

Different teams may run different models under different reasoning/token budgets
(chess-clock analogy). This is core to the product's value, not a config nicety
— it's what makes "does a bigger, slower model beat a faster, leaner one" a real,
answerable, watchable question. Budgets are **enforced by the orchestrator, per
phase** — never left to a backend's own constructor defaults, which is exactly
how Aragora's budget claims silently failed to hold across every phase (see
ADR-001).

## Backend abstraction

Single-method `async` `Protocol` as the LLM seam (lifted design from
`arbgjr/multi-agent-debate`), not a multi-method ABC. One `openai-compatible`
adapter with a configurable `base_url` (idea from `agent-discussion-arena`)
covers MLX (`mlx_lm.server`), Ollama, LM Studio, and OpenAI itself through one
code path.

**Dev default model is Apple Foundation Models (AFM)**, or another very small
model — instant, free, no MLX load overhead, no memory pressure. Used while
building and testing the CLI plumbing itself (config parsing, phase loop,
output-file discipline, judge scoring format). Real MLX candidate models are
reserved for once the harness is proven and the actual question becomes "is this
debate any good," not "does the pipe work."

**Never call a synchronous SDK client inside `async def`** without
`asyncio.to_thread` — observed as a real, unnoticed bug (fake concurrency) in all
four of `aragora-debate`'s cloud-provider agents (see ADR-001).

**Model servers run offline — a requirement, not an option.** Every model server
runs with `HF_HUB_OFFLINE=1`, and anything else that fetches from the Hugging
Face Hub (such as `datasets` for `sources`, later) uses its equivalent offline
setting. B0 found `mlx_lm.server` contacts huggingface.co on every start to check
the model revision. That contradicts the offline-capable, privacy-first
positioning this tool is built around. In offline mode, already-downloaded
models resolve from the local cache (verified 2026-09-11). Downloading a model is
a separate, explicit step.

## Judge design

Five independently-scored rubric dimensions, never blended into one number:
argument quality & logic (30), evidence grounding (25), steelman fidelity (20),
rebuttal effectiveness (15), clarity (10). Steelman fidelity is the explicit
tiebreaker, given the app's core premise.

Rebuttal effectiveness is tracked via a **structured hit-ledger**
(open/conceded/rebutted/dodged per point — idea from `arbiter-debate`), not a
subjective number alone.

A narrow, separate **fallacy-detector** check (idea from `autodebater`'s
"Bullshit Detector" judge) is a candidate fast signal, same tier as the
fact-checker — not yet decided whether it's folded into fact-checking or kept as
its own pass.

A candidate **stance-consistency** check (idea surfaced reviewing
`mlburnham/Political_DEBATE_large_v1.0`, a 0.4B DeBERTa NLI classifier — name
is a backronym, "DeBERTa Algorithm for Textual Entailment," unrelated to
adversarial debate) is a second candidate fast signal: cheap enough to run
after every turn without competing for resources with the debater models,
verifying a side's turn still entails its assigned stance rather than drifting
or conceding. Not yet decided whether this is a third fast pass alongside
fact-checking and the fallacy detector, or folded into one of them.

**Validation data for the rubric itself, before trusting any judge model
choice:**
- `ibm-research/argument_quality_ranking_30k` (IBM-Rank-30k; CC-BY-3.0) — 30,497 crowd-written
  arguments across 71 genuinely contested policy topics (same domain as this
  app, not academic claims or trivia), each with a human quality score (WA and
  MACE-P methods) and stance label. Use to correlate a candidate judge's
  argument-quality scores against real human judgment before trusting it.
- `ibm-research/debate_speeches` (CDLA-Permissive-2.0) — the HF release
  (`opening_speeches` config) holds 948 opening speeches across 114 topics from
  nine sources, human-written and machine-generated, each rated by crowd
  annotators (5–30 per speech, mean ≈15). 81 of them are "mixed stance control"
  speeches used as annotator test questions; exclude those before correlating.
  (The 631-speech / 76-topic figure previously cited here matches neither; if it
  is the paper's subset, record that.) Purpose-built for benchmarking whether an LLM judge's scores track human
  judgment at the speech/turn level (closer to our unit of judging than
  Rank-30k's isolated arguments). A recent paper, "Benchmarking LLM Judges via
  Debate Speech Evaluation," used this exact dataset for this exact task — read
  it for methodology before designing our own validation pass.
- `tasksource/logical-fallacy` (Jin et al. 2022) — 3,761 labeled examples
  across 13-14 fallacy types, real naturalistic argument text, includes a
  `LogicClimate` challenge subset specifically for climate-policy claims. Real
  train/test/dev splits; multiple independent models already fine-tuned on it.
  Candidate training/validation set for the fallacy-detector check above.
  **License: none found, but the authors' README explicitly says "Feel free to
  access our data in the `data/` folder."** No LICENSE file, HF lists
  `unknown`. Treat this as two separate permissions, not one: sufficient for
  private use (downloading it ourselves to validate a fallacy-detector or judge
  against) but not for redistribution — nothing grants the right to bundle or
  republish the data as part of a `debatebench` release. Keep for validation
  use; do not ship any of it in this repo without a clearer grant.

## Fact-checking is separate from judging, and runs on a different clock

- **Fact-check**: fast, narrow, per-claim, runs at the end of every turn in real
  time (UI requirement, driving the CLI's design even before UI exists) —
  verifies a claim against the side's own recorded Prep evidence.
- **Judge**: slower, holistic, runs once over the complete transcript at the end.
- Regex/heuristic "evidence hygiene" (citation density, specificity — as in
  Aragora's `evidence.py`) is not a substitute for either of the above and, if
  used at all, must be labeled "evidence hygiene," never "fact-check" — it scores
  surface form, not truth, and a confidently fabricated citation with a
  plausible-looking year and percentage would score *high* on it.

## Hard invariant

Every configured phase must produce a response from every side, or the run
aborts with nothing written to the `output:` path (ADR-007). A silently one-sided debate producing a
confident-looking verdict is the worst failure mode for a benchmarking tool
(observed as a real, unflagged bug in a reviewed competitor — see ADR-001).

## Hardware

MLX-first. Running two debater models plus a judge/fact-checker concurrently on
one Mac (target dev machine: M2 Pro, 32GB unified memory) is a real memory- and
compute-contention risk, not just a capacity question — Apple Silicon's GPU and
memory bandwidth are shared, so three "simultaneous" models likely serialize
rather than truly parallelize. Options on the table, not yet decided: offload the
judge/fact-checker to a remote host already running inference (`free`, via
Ollama) — **withdrawn by B0, see below** — or load/unload models per turn rather
than keeping all three resident.
**Needs its own M0-style hardware probe (real peak memory + turn latency
measurement) before any assumption here is trusted.** ("M0" is the MLXProbe
session-M0 throwaway probe; results at `~/Projects/MLXProbe/RESULTS.md`.)

### B0 findings (2026-09-11)

B0 measured this on the dev machine (`RESULTS.md`). What it changes here:

- **`free` is not a separate host: it's the dev machine itself.** The "offload
  to `free`" option above offloads nothing, so it's withdrawn unless a genuinely
  separate host is named. This isn't a minor correction. It invalidates a
  specific option this ADR proposed, and it would have been silently
  load-bearing for the rest of the build if nobody had tried to reach the host.
  Two earlier reachability checks during B0 got it wrong before it was
  confirmed.
- **The judge never needs to be co-resident.** The judge runs once, post-hoc,
  over the finished transcript (see "Fact-checking is separate from judging"),
  so it can load after the debaters unload. That decision now does real
  load-bearing work: the "three models at once" concern applies only to a
  fact-checker that has to run live. This follows from the design; B0 didn't
  measure it.
- **The fact-checker is the one genuinely open hardware problem**, and its
  designated offload target doesn't exist. Either it stays scoped to AFM-sized
  checks, capped at about 4,096 tokens per request (ADR-003), which may be enough
  for a single claim plus its evidence; or a real second machine has to be
  found. That must be decided explicitly, not assumed (tracked in
  OPEN-QUESTIONS).
- **The debater pair is doubtful and unmeasured, not ruled out.**
  Mistral-Small-24B alone tripped B0's safety cut-off (critical memory pressure
  alongside normal desktop use) before the pair and concurrency stages ran. A
  quiet-machine rerun comes before anything downstream trusts the pair.
- **Load/unload per turn looks expensive at long contexts**, but that's inferred:
  a cold 4,000-token prompt took about 25 s on the 8B model, and a full swap cycle
  wasn't measured.

Prep and argument phases may warrant different inference engines — MLX
generally wins decode-heavy short-turn work, but long-document Prep ingestion is
a prefill-heavy workload where llama.cpp/Ollama have shown faster prompt-eval in
some benchmarks. Worth benchmarking separately, not assumed to inherit the same
engine choice.

## Scope discipline

Stay narrow: structured multi-turn comparison + rubric scoring + fact-checking.
No consensus/voting logic anywhere in the design — consensus-seeking built into the
turn loop is what ruled out `aragora-debate` and `arbgjr/multi-agent-debate` (see
ADR-001). No formal
verification (Z3/SymPy-style, as in `arbiter-debate`) — domain-mismatched for
non-formalizable topics like policy debates. Resist becoming "the debate app's
backend" — frame and build it as a general-purpose structured-comparison tool
that the debate app happens to be the first real user of. Aragora's own
self-documented scope creep (~25% of its codebase admitted by its own authors
not to serve its core thesis) is the cautionary example to actively design
against. (The source for the ~25% figure isn't recorded yet — R0's aragora health
section documents the platform's breadth but not this number. Cite it or drop the
number.)

## Data sourcing — no scraping user-generated debate platforms

Reviewed several live consumer debate platforms (DebateWise.org, DebateArt.com,
VersyTalks.com) as competitive-landscape research — genuinely useful for
understanding the market (all three determine a winner via crowd voting, not a
rubric judge, which remains a real point of difference for this project) but
**none of their content is a candidate data source.** Unlike the academic
datasets used elsewhere in this ADR (IBM-Rank-30k, DebateSum, args.me, etc.,
all released under explicit open licenses for reuse), these are user-generated
content platforms whose terms of service almost certainly prohibit scraping and
bulk reuse, with no indication any of them hold rights to sublicense user
content for training or grounding purposes. Quality or topical relevance never
overrides this — a dataset failing the licensing gate is disqualified
regardless of how well it would otherwise fit. Any future dataset candidate
gets checked for an explicit reuse license before anything else, same as every
dataset actually adopted so far.

## Attribution

Two design lifts (`events.py` shape from `aragora-debate`, `Protocol` shape from
`arbgjr/multi-agent-debate`) and a conditional third (`evidence.py`-derived
evidence-hygiene scorer, if adopted) require attribution in a `NOTICE` file — all
source projects are MIT.
