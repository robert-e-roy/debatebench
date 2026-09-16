# Model Coverage — what has been run, at what size, and what it did

`debatebench` exists to compare models, so the first thing worth knowing about it
is **which models it has actually been run against**. This file is that ledger.
Every row points at the artifact or the ADR that measured it; anything with no
pointer is not a result.

Compiled 2026-09-15 from `RESULTS.md` (B0), `BACKEND-PROBE-RESULTS.md`,
`JUDGE-VALIDATION.md`, `probe/b6/`, `probe/mirror/` and `probe/scale/`.

## The ladder, and the honest summary

**Generation is a dimension, not a detail.** It was added on 2026-09-15 after
`qwen3:4b` and `qwen3.5:4b` — same parameter count, same prompt — produced
*opposite* fact-check behaviour, and after the newer generation needed roughly
**five times the budget** to answer at all. Anything pinned to a model is pinned
to its generation: **`JUDGE-VALIDATION`'s Tau-C +0.547 is a result about
`qwen3:8b` specifically** and does not transfer to `qwen3.5` or `qwen3.6`, which
would each need their own 631-speech run.

| class | model | gen | params | on disk | debater | judge | verdict |
|---|---|---|---|---|---|---|---|
| small | **AFM** via `fm serve` | — | ~3B on-device | n/a | ✅ B1–B4 gates | ❌ **cannot** | plumbing only; ~4,096-token ceiling |
| small | **qwen3:0.6b** | 3 | 0.6B | 522 MB | untried | ❌ 1 claim | below the floor |
| small | **qwen3:1.7b** | 3 | 1.7B | 1.4 GB | untried | ❌ 1 claim | below the floor |
| small | **phi4-mini** | — | ~3.8B | 2.5 GB | ✅ probe | ⚠️ scores, audit breaks | weakest usable |
| small | **qwen3:4b** | 3 | 4B | 2.5 GB | untried | ✅ clauses (1)+(3) | cheapest working judge |
| small | **qwen3.5:4b** | **3.5** | 4B | 3.4 GB | untried | ✅ clauses (1)+(2) | needs ~5× the budget |
| medium | **qwen3:8b** | 3 | 8B | 5.2 GB | ✅ extensively | ✅ **validated for ordering** | the workhorse; state-sensitive |
| medium | **gemma4:12b** | — | 12B | 7.6 GB | ✅ 5 debates | ⚠️ works, slow, hungry | judged the mirror runs |
| medium | **qwen3:14b** | 3 | 14B | 9.3 GB | untried | ✅ clauses (1)+(3) | state-**in**sensitive |
| large | **qwen3:32b-16k** | 3 | 32B | 20 GB | ❌ never | ❌ **unparseable ×4** | fits at 24 GB, 100% GPU; cannot emit the format |
| large | **Mistral-Small-24B-4bit** | — | 24B | ~13 GB | ❌ **never ran** | ❌ never ran | aborted at load (B0) |
| large | **deepseek-r1:32b** | — | 32B | *removed* | ❌ never | ❌ never | 7.4 tok/s; thinking not disableable |

**The large class has produced exactly two tokens' worth of evidence, and it
arrived today.** `deepseek-r1:32b` at Ollama's default 131,072-token context
reported 55 GB resident, drove the machine to 0.1 GiB free with swap nearly
exhausted, and had its probe killed by the OS. Rebuilt at a **16K context** it
fits in 23 GB at 100% GPU and answers — at **7.4 tok/s**, about a fifth of
`qwen3:8b`, with thinking that cannot be switched off. Mistral-Small-24B still
has never run at all.

So every *quality* finding in this repo still comes from models between roughly
3B and 12B. What changed is that a large-model reading is now possible rather
than blocked — at roughly an hour per judged transcript.

## What each size class actually does here

### Small (~3–4B) — the harness works, the judging doesn't

**AFM** is the development default by decision (ADR-002, ADR-003): fastest to
first token of anything measured (server ready in 0.04 s, 38.6 tok/s) and free of
model-management work. It carried B1, B2, B3 and B4's live gates.

It **cannot be a judge**, and this is a hard limit rather than a quality
judgement: ~4,096 tokens per session covers instructions, context and reply
together (ADR-003), and a full transcript does not fit. A request over the
ceiling fails with HTTP 500. B7's exit gate names this explicitly.

**phi4-mini** is the smallest model that has judged anything. It produces a
parseable *score* sheet and a malformed *fact-check* audit — measured, and the
same split `qwen3:8b` showed through `mlx_lm` (ADR-017 §4). ADR-018 records its
scores as poor next to a like-for-like `qwen3:8b` run.

**What the class tells you:** the plumbing is model-agnostic and cheap to
exercise. Scoring quality is not.

### Medium (8–12B) — everything the project actually knows

**`qwen3:8b`** is the only model whose judging has been validated at all:
Tau-C **+0.547** against human ratings over 631 speeches, 631/631 replies parsed
(`JUDGE-VALIDATION.md`). **Only its ordering passes** — calibration fails, and
it is 0.95–1.52 low on machine-generated text, which is what this tool judges.

It is also the model behind every B6 gate run — 25 of them — and every claim
about the fact-check pass. Its known behaviours:

- **Deterministic within a model load state, not across one.** Cold gives an
  11-claim ledger with zero `contradicted`; warm gives 20 claims with three.
  A cold judge silently under-reports (`probe/b6/README.md`).
  **Reproducible to the byte across two days** (2026-09-16): a cold draw on the
  unchanged prompt hashes identically to the 2026-09-14 cold draw,
  `2fddcc93b6f8afc0`. Determinism here spans sessions, not just a session.
- **The load-state sensitivity is a property of the prompt, not only the model.**
  Under ADR-030's reply schema all four draws were identical *across* the
  cold/warm boundary — 16 claims either way — while the unchanged prompt, run
  cold the same day as a paired control, still gave 11. So a sufficiently
  constraining reply shape removed the state sensitivity on this model. ADR-030
  was reverted for unrelated reasons (below); the effect is recorded because it
  is the only thing that has ever moved this behaviour.
- **A reasoning model**: `budget` counts its thinking (OPEN-QUESTIONS 13).
- Malformed JSON at a measured rate — 2 of 6 calls in one batch.

**`gemma4:12b`** is the newest and least characterised. It has run five full
debates and judged four of them (`probe/mirror/`), and it scored the weak-debate
control. What is measured about it:

- **A reasoning model too**, and hungrier: a scoring call at `budget: 6000`
  returned an empty answer and 1,563 characters of thinking. 10,000–16,000 works.
- **Slow enough to hit the old 600-second read timeout** on a cold load at
  `--budget 20000`, which is what produced ADR-025.
- `reasoning_effort: "none"` turns its thinking off on Ollama — 99 completion
  tokens to 6, same answer (OPEN-QUESTIONS 13).

**What the class tells you:** it works, it is affordable, and one model in it has
a validated ordering. Everything else about judge quality is still open.

### Large (24B+) — two attempts, zero tokens

#### `deepseek-r1:32b` — measured 2026-09-15, and it does not fit

Pulled at 19 GB and loaded through Ollama. It never answered a single prompt:
the probe process was **killed by the OS for low memory** before its first call
returned. What `ollama ps` reported while it was resident:

```
NAME               SIZE     PROCESSOR          CONTEXT
deepseek-r1:32b    55 GB    54%/46% CPU/GPU    131072
```

Machine state at that moment: **0.1 GiB free** and **14.6 GB of 15.3 GB swap
used**. Unloading it returned 21.7 GiB of free memory immediately.

**The 55 GB is mostly context, not weights.** The weights are 19 GB; Ollama
loaded the model at its default **131,072-token** context, and the KV cache for
that on a 32B model accounts for the rest. The `54%/46% CPU/GPU` split is the
symptom: it did not fit in unified memory, so half of it ran on CPU.

**This is not "a 32B model cannot run here" — it is "this model at a 128K
context cannot".** `debatebench`'s judge needs a context that holds one
transcript and one reply, which is tens of thousands of tokens, not 131,072.

#### At a 16K context it fits, and answers — measured 2026-09-15

`deepseek-r1:32b-16k`, a two-line Modelfile (`FROM deepseek-r1:32b`,
`PARAMETER num_ctx 16384`). The first large model in this project to produce a
token:

```
NAME                   SIZE     PROCESSOR    CONTEXT
deepseek-r1:32b-16k    23 GB    100% GPU     16384
```

55 GB to 23 GB, and the CPU spill is gone — **100% GPU**. So the context was the
whole problem.

Three results, and only the first is good:

- **It fits, barely.** Resident it leaves **0.1 GiB free** with 5.6 GB of swap in
  use. It runs, but there is no headroom: anything else substantial starting
  during a run risks the same OOM kill that ended the 128K attempt.
- **It is slow: 7.4 tok/s**, against `qwen3:8b`'s 33.9 and AFM's 38.6 (B0). A
  judge call at `--budget 16000` is therefore roughly **35 minutes of generation
  alone**, before prompt processing, and `judge` makes two calls when
  fact-checking. Budget 60–90 minutes for one judged transcript.
- **`reasoning_effort: "none"` is ignored.** Control produced 1,513 characters of
  thinking; with the flag, 1,380. That is noise, not obedience — and it breaks
  the mitigation measured on `gemma4:12b`, which went from 318 characters of
  thinking to zero. **On `deepseek-r1` the thinking cannot be switched off**, so
  every budget must clear it.

For scale: a trivial prompt — *answer with one JSON object, `{"ok": true}`* —
cost **325 completion tokens**, of which about 310 were thinking, for a 14
character answer.

Thinking arrives in the separate `reasoning` field, not inline as `<think>`, so
the adapter's all-reasoning-no-answer guard (ADR-025 era) covers it correctly.

**Verdict: usable as a judge, expensive as one.** It is the only path this
project has to a large-model reading, and it costs about an hour per transcript
with no way to make it cheaper.

**Operational note, learned the expensive way:** check `ollama ps` for `SIZE`
and `CONTEXT` after loading a large model and before committing to a run. The
disk size tells you nothing about the resident size, and the gap here was 19 GB
against 55 GB. A model that loads can still take the machine into swap
exhaustion and get an unrelated process killed.

#### `Mistral-Small-24B-4bit` — B0's blank row



`mlx-community/Mistral-Small-24B-Instruct-2501-4bit` is the only large model
attempted. **It never produced a token.** B0 loaded it, watched weights go from
0.3 to 13.0 GiB in about five seconds, saw free memory reach 0.0 GiB with memory
pressure **critical**, and aborted (`RESULTS.md`).

That measurement was taken on the machine *as actually used*, with a browser, an
IDE and a chat app open. **B0's own caveat stands: the pair is unmeasured, not
ruled out**, and a quiet-machine rerun comes before anything trusts it.

**What this means for every quality claim in this repo:** the intended
8B-against-24B pairing that motivated the tool has never been run. Whether a
larger judge fixes the calibration failure, the fact-check gap, or the 85–100
score compression is **entirely unknown**, and each of those is a live suspect.

## What we would expect a larger model to change — stated as predictions, untested

Written down so they can be checked rather than assumed later:

1. **Clause (3) of B6 might simply be a capability limit.** Zero `not_checkable`
   in 25 runs, all `qwen3:8b`, across three prompt variants. A second model has
   never successfully produced that ledger. If a 24B judge produces the verdict
   on the first try, three conditions of prompt-tuning were chasing the wrong
   variable.
2. **The malformed-JSON rate should fall.** ADR-017 §4 measured that the *audit*
   call breaks where the *scoring* call does not, on two models and two backends,
   and attributed it to prompt length and item count — which is a capability
   story.
3. **Score compression at the top may not change.** `probe/scale/` showed the
   rubric reaching 45 of 100 for a genuinely weak debater, so the scale
   discriminates; what it does poorly is separate two competent sides. A larger
   judge might or might not.

## Backends, since model and backend are separable here

| backend | models run | notes |
|---|---|---|
| **Ollama** (recommended, ADR-018) | `qwen3:8b`, `phi4-mini`, `gemma4:12b` | honours `response_format`, queues concurrent calls, prefills fastest, ~20% slower decode than `vllm-mlx` |
| **`mlx_lm.server`** | Qwen3-8B-4bit | reads `seed` and `max_completion_tokens`; reports thinking separately; honours `response_format` in neither mode |
| **`vllm-mlx`** | Qwen3-8B-4bit | fastest decode; refuses a second concurrent request with 503; leaves thinking inside `content` |
| **AFM** via `fm serve` | the system model | ~4,096-token session ceiling |
| **LM Studio** | **none** | named in ADR-002 as a target; never run against |

## What the ladder established, 2026-09-15

Seven judges on one transcript, same prompt, load state held constant:

- **There is a floor.** `qwen3:0.6b` and `qwen3:1.7b` return a single claim.
  They cannot perform this task.
- **The cheapest working judge is 4B**, not 8B. `qwen3:4b` produces a full
  ledger with correct opinion classification.
- **Capability here is not monotonic in size.** 4b finds opinions, 8b does not,
  14b does. That rules out "too small to tell an opinion from a fact".
- **No judge has produced all three B6 clauses.** Every working model returns
  exactly two, and *which* two varies by model and generation.
- **Context defaults are a live hazard.** Ollama gave `qwen3:4b` a
  262,144-token context (43 GB resident, CPU spill) and `deepseek-r1:32b` a
  131,072 one (55 GB, OOM kill). Cap `num_ctx` before running anything large.

## The fact-check clause gap, and what closing it now depends on

`qwen3:8b` is the only judge here whose ordering is validated, and it produces
B6 clauses (1) and (2) warm and has **never** produced clause (3) — zero
`not_checkable` in 29 draws now. Three changes have attacked that through three
independent channels and all three were measured and reverted:

| condition | channel | `not_checkable` | claims | cross-side `contradicted` |
|---|---|---|---|---|
| baseline | — | 0 | 20 | 3 |
| B | verdict-list order | 0 | fewer | **0** |
| C | user-turn framing | 0 | **5** | — |
| ADR-030 | required `factual` field in the reply schema | 0 | **16** | **0** |

**`qwen3:14b` is not budget-limited.** Warm at 16,000 is **byte-identical** to
warm at 6,000 — a 2.7x increase changing nothing. That is the opposite of
`qwen3:32b`, where changing the budget demonstrably changed the reply, and it
rules out OPEN-QUESTIONS 13 as the reason 14b returns no contradictions.

**And clause (2) itself is now in question** (2026-09-16, OPEN-QUESTIONS 16).
Asked about the cited passage alone, all four models — including `qwen3:8b`
itself — reject two of the three contradictions `qwen3:8b` reports in its audit.
Adding the opponent's *turn text* flips three of four cells to YES. So those
verdicts are driven by what the opponent **argued**, not by the passage they
cite, and B6 clause (2) asks specifically for the opponent's *evidence* with a
citation pointing at it. Treat "clause (2) met" as unsettled.

**Read this before attributing a fact-check result to a prompt.** Every attempt
to make `qwen3:8b` answer the checkability question costs clause (2) and shrinks
the ledger. `qwen3:4b` and `qwen3:14b` produce clause (3) unprompted on the same
transcript, so the variable is the judge, not the wording.

**`qwen3:14b`'s missing clause (2) is a different defect**, characterised
2026-09-16 and not yet fixed: it lists both halves of a contradiction pair,
cites both ids correctly, and marks each `supported`. Its citation mechanics are
exact; it never weighs a claim against the *opposing* side's passage. That is
ADR-019's precedence rule failing on a model ADR-019 was never measured on — and
since 14b already has clause (3) in both states, it is the shortest remaining
route to a passing gate.

## The gaps, in the order they matter

1. **No model produces all three fact-check clauses.** This is now B6's whole
   problem, and it is a model property rather than a prompt one.
2. **Only one model's judging is validated**, only for ordering, and **only for
   that generation**.
3. **No large model has produced a usable ledger.** `qwen3:32b` fits and runs
   but returned unparseable JSON on **all four attempts** — three byte-identical
   across both load states, and a fourth that differed only because the budget
   changed. Two distinct defects: a key emitted inside a string value, and
   unescaped inner quotes. The large rung's verdict is that it cannot emit this
   format on this input.
4. **LM Studio is claimed as supported and has never been tested.**
5. **`gemma4:12b` has judged five debates and been characterised in none** — no
   Tau-C, no B6 gate run, no position-bias baseline of its own.
