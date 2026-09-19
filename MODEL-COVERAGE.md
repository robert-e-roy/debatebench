# Model Coverage — what has been run, at what size, and what it did

`debatebench` exists to compare models, so the first thing worth knowing about it
is **which models it has actually been run against**. This file is that ledger.
Every row points at the artifact or the ADR that measured it; anything with no
pointer is not a result.

The **What to use** section below is the answer most readers want; the ledger
after it is the evidence. The `debater` column was ground-truthed against the
run store on 2026-09-19 — four rows said `untried` and were wrong.

Compiled 2026-09-15 from `RESULTS.md` (B0), `BACKEND-PROBE-RESULTS.md`,
`JUDGE-VALIDATION.md`, `probe/b6/`, `probe/mirror/` and `probe/scale/`.

## What to use — the short answer, 2026-09-19

**Debating and judging are different jobs and the evidence for them is
different.** A model that argues well has not been shown to score well, and the
reverse. Pick per role.

### As a debater

| class | pick | measured | why |
|---|---|---|---|
| small | **`qwen3:4b-16k`** | 2.5 GB file; **cap required** | The floor for a real debate. `0.6b` and `1.7b` run but lose by 17–20 points on a factual motion once anything can check their claims. 4b won its mirror. |
| medium | **`qwen3:14b-16k`** | 9.3 GB file, **12.2 GB resident at 16k** | The current workhorse: 18 side-appearances, finishes a prep note in ~1,350–2,100 tokens, no budget surprises once sized properly. |
| large | **none** | — | See below. Nothing in this class has earned a recommendation. |

### As a judge

| class | pick | measured | why |
|---|---|---|---|
| small | **none for fact-check** | — | `phi4-mini` produces a parseable *score* sheet and a broken *audit*; `qwen3:4b` gives a full ledger but is unvalidated. Use small models to exercise the pipeline, not to grade. |
| medium, for **ordering** | **`qwen3:8b`** | 5.2 GB, 33.9 tok/s | **The only judge here validated against human ratings at all** — Tau-C **+0.547** over 631 speeches, 631/631 parsed (`JUDGE-VALIDATION.md`). Only its *ordering* passes; its absolute numbers are 0.95–1.52 low on machine text. |
| medium, for **fact-check** | **`phi4:14b`** with `--strict-json` | 9.1 GB, `trained_ctx` 16,384 — **fits as shipped** | The only judge that uses all four verdicts on the same ledger (3 of 3 transcripts), and lineage-distant from qwen3 debaters. **Fails outright on ~1 transcript in 3** — expect a failed cell. |
| large | **none** | — | See below. |

### Why there is no large-model pick

Every 24B+ candidate has been tried and each failed differently:

| model | what happened |
|---|---|
| `qwen3:32b-16k` | fits at 24 GB, 100% GPU — **unparseable JSON on all four attempts** |
| `command-r:35b-8k` | ran, but marked **25 of 27 claims `not_checkable`** — declines to judge |
| `deepseek-r1:32b-16k` | answers at **7.4 tok/s**, ~1 hour per judged transcript, thinking cannot be switched off |
| `Mistral-Small-24B-4bit` | **never produced a token** — aborted at load (B0) |

**No large model has produced a usable ledger or a single debate turn here.**
That is a statement about this 34 GB machine and these four models, not about
large models in general — but it is the state of the evidence, and the intended
8B-against-24B pairing that motivated this tool has still never run.

### Three operational rules that matter more than the pick

1. **Cap `num_ctx` before running anything.** Earned five times now. The disk
   size tells you nothing about the resident size: `mistral-nemo` is a 7.1 GB
   file that wanted **51.8 GB**; `qwen3:4b` wanted ~43 GB; `qwen3:14b` took the
   machine to 0 GiB free at its default 40,960 context and **12.2 GB at 16k**.
   Capping is **output-neutral** — verified, 8/8 turns byte-identical across a
   capped/uncapped pair. Check `ollama ps` for `SIZE` and `CONTEXT`.
2. **Size `prep_budget` for the largest model in the run, not the smallest.**
   `prep_budget: 1500` truncated `qwen3:14b` in 8 of 11 prep turns and never
   touched `qwen3:0.6b`, so every mixed run handicapped the *larger* model.
   See `debates/PREP-BUDGET.md`. 6000 is the current derived value.
3. **Check `hit_budget` before reading any result.** It is in every turn of
   every transcript and always has been. A truncated prep once produced an
   apparent persona effect that was entirely the token cap.

### The gap a reader should know about

**Only `qwen3` models have ever debated in the run store.** `gemma4:12b` debated
five times in `probe/mirror/` and AFM carried the B1–B4 gates; nothing else has
argued at all. So every claim on this page about *debate* quality is a claim
about one family, and the judge picks above are the only place cross-family
evidence exists.

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
| small | **qwen3:0.6b** | 3 | 0.6B | 522 MB | ✅ 10 appearances | ❌ 1 claim | debates, but loses 17–20 once claims are checkable |
| small | **qwen3:1.7b** | 3 | 1.7B | 1.4 GB | ✅ 2 appearances | ❌ 1 claim | below the floor as a judge |
| small | **phi4-mini** | — | ~3.8B | 2.5 GB | ✅ probe | ⚠️ scores, audit breaks | weakest usable |
| small | **qwen3:4b** | 3 | 4B | 2.5 GB | ✅ 4 appearances | ✅ clauses (1)+(3) | **the small pick**; cap `num_ctx` |
| small | **qwen3.5:4b** | **3.5** | 4B | 3.4 GB | untried | ✅ clauses (1)+(2) | needs ~5× the budget |
| medium | **qwen3:8b** | 3 | 8B | 5.2 GB | ✅ extensively | ✅ **validated for ordering** | the workhorse; state-sensitive |
| medium | **gemma4:12b** | — | 12B | 7.6 GB | ✅ 5 debates | ⚠️ works, slow, hungry | judged the mirror runs |
| medium | **qwen3:14b** | 3 | 14B | 9.3 GB | ✅ 24 appearances | ✅ clauses (1)+(3) | **the medium debater pick**; 12.2 GB at 16k |
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

## Judges outside the qwen3 family, 2026-09-17

Every judging result before this date came from `qwen3:8b` judging `qwen3`
debaters — same family, which is the bias an LLM judge is most prone to. Four
more judges were run against the same transcripts. **Each family broke a
different part of the reply contract**, and none broke the same part twice:

| judge | size | family | failure mode | usable |
|---|---|---|---|---|
| `qwen3:8b` | 8B | qwen3 | malformed JSON on richer debates (3 of 6) | mostly |
| `gemma4:12b` | 11.9B | gemma4 | **32,076 chars of reasoning, no answer**, 14 min | **no** |
| `phi4-mini` | 3.8B | phi3 | invents evidence ids (`am-255`, never recorded) | scores only |
| `mistral-nemo:12b` | 12B | llama | invents hit-ledger statuses (`partially rebutted`) | 2 of 6 |
| `phi4:14b` | 14.7B | phi3 | doubled quotes inside justifications (4 of 10) | best unconstrained |

`gemma4`'s failure is **not** a grammar problem and `--strict-json` does not fix
it: it never reaches an answer at all. That needs `reasoning_effort`, which is
OPEN-QUESTIONS 13's unwired half.

### `--strict-json` (ADR-032) changes this picture completely

Constraining the reply to a JSON schema, measured across three judges and three
transcripts both ways:

- **parse failures 5 of 9 → 0 of 9**;
- **ledgers grew rather than thinned** (15→16, 11→12, 9→12, 17→36);
- **two families then produce all four verdicts in one ledger** — `phi4:14b`
  3 of 3, `mistral-nemo` 2 of 3 — where unconstrained neither ever did.

**`qwen3:8b` still never emits `not_checkable`, even constrained (0 of 3).** That
is a fourth independent channel confirming ADR-031: clause (3) is a property of
that model, not of the request.

Labels appearing reliably is not labels being correct. An isolation test on
`phi4:14b`'s cross-side contradictions found one confirmed by four models, one
contested and one false positive; and `phi4:14b` marks over half its claims
`not_checkable` (24 of 44), which may be a distortion in the other direction from
`qwen3:8b`'s zero.

### Ollama's context default is a bigger memory hazard than parameter count

Measured on this machine (**32.0 GiB M2 Pro** — an earlier revision of this
line said 34.4 GB, which was B0's *demand* arithmetic, 14.8 baseline + 19.6 for
the pair, not the installed memory) while selecting judges:

| model | file | trained context | resident |
|---|---|---|---|
| `mistral-nemo:12b` | 7.1 GB | **1,024,000** | **51.8 GB** |
| `mistral-nemo:12b-8k` | 7.1 GB | 8,192 | 8.3 GB |
| `qwen3:4b` | 2.5 GB | 262,144 | ~43 GB |
| `qwen3:32b` | 20.2 GB | 40,960 | 24 GB |
| `phi4:14b` | 9.1 GB | 16,384 | fits as shipped |

A **7.1 GB model wanted 51.8 GB** — more than the 20 GB `qwen3:32b`. One
`PARAMETER num_ctx` line takes it to 8.3 GB with identical weights. **Check
`trained_ctx` before pulling a model into a memory-constrained comparison**; it
varies by family and predicts footprint better than size does.

## Purpose-built judges exist, and run locally as GGUF

Ollama runs GGUF straight from Hugging Face (`ollama pull hf.co/{repo}`), which
reaches a much larger pool than its own library — including models **trained to
be judges** rather than general instruct models:

| model | base | licence | note |
|---|---|---|---|
| **`AtlaAI/Selene-1-Mini-Llama-3.1-8B-Q4_K_M-GGUF`** | Llama-3.1-8B | llama3.1 | **tested, below** — also the only Llama-family model this project has run |
| `prometheus-eval/prometheus-7b-v2.0-GGUF` | Mistral-7B | apache-2.0 | rubric-and-reference evaluator; untested |
| `flowaicom/Flow-Judge-v0.1-GGUF` | Phi-3.5-mini | apache-2.0 | untested; same family as phi4-mini, so a controlled judge-tuned-vs-not comparison |
| `mradermacher/Selene-1-Llama-3.3-70B-i1-GGUF` | Llama-3.3-70B | — | too large for this machine |

### Selene-1-Mini, measured 2026-09-18

**The context hazard, a fourth time:** `trained_ctx` is 131,072 and the 4.9 GB
model sat at **22.5 GB resident**. Capped to 16k (`selene:8b-16k`) it is 7.3 GB.
Checking `trained_ctx` before use has now paid for itself four times.

No reasoning tax (0 chars thinking, 1.5 s). It **scores** cleanly and is the most
*discriminating* judge tested that does not look broken — it separated the two
sides on `argument_quality` 24 vs 17 and `steelman_fidelity` 19 vs 12, where
`qwen3:8b` compresses everything near the top.

**But it fails the fact-check with a sixth distinct failure mode**, and this one
is outside ADR-032's reach: `claims[0] is supported but cites no passage`. That
is a **semantic** violation — a cross-field rule ("supported implies a citation")
that JSON Schema can only express with conditionals, which llama.cpp's
constrained decoding does not enforce. Constrained decoding closed four failure
modes; it cannot close this one, and `_evidence_citations` catching it is
ADR-032 §6 earning its keep.

### `llama3.1:8b` and `command-r:35b`, 2026-09-18

Both needed capping — `trained_ctx` 131,072 each. Capped: `llama3.1:8b-16k`
7.0 GB, `command-r:35b-8k` 20.3 GB. Neither was loaded uncapped: a 32B model
with a 131k window would very likely have exceeded this 34 GB machine, and two
memory kills this week were enough. Both are clean of reasoning tax.

**`llama3.1:8b` fails identically to Selene — and Selene is judge-tuned
Llama-3.1-8B.** Both return `claims[0] is supported but cites no passage`. That
is an accidental but clean controlled comparison: **Atla's judge tuning did not
fix the failure mode its own base model has.** Whatever Selene gained, schema
discipline on this contract was not it.

**`command-r:35b` is the opposite extreme from `qwen3:8b`.** It is the one
candidate trained for grounded generation with citations, and on the same
transcript:

| judge | supported | contradicted | not_checkable |
|---|---|---|---|
| `qwen3:8b` | 13 | 2 | **0** |
| `command-r:35b` | 2 | 0 | **25 of 27 (93%)** |

`qwen3:8b` never declines to judge; `command-r` declines almost always. A model
trained to ground claims in citations, given a real corpus, refuses to certify
25 of 27 claims as checkable — which is either admirable calibration or a refusal
to engage, and this evidence cannot tell which. It is the strongest argument yet
that **`not_checkable` counts say more about the judge than about the debate.**

### Six judges on one transcript

`healthcare-14b-pro`, 14b pro against 0.6b con:

| judge | family | pro | con | gap |
|---|---|---|---|---|
| `phi4-mini` | phi3 | 80 | 76 | **+4** |
| `qwen3:8b` | qwen3 | 91 | 86 | **+5** |
| `selene:8b-16k` | llama3.1 | 83 | 63 | **+20** |
| `command-r:35b-8k` | command-r | 97 | 77 | **+20** |
| `gemma4:12b` | gemma4 | 93 | 44 | **+49** |

**Five judges, five families, same winner every time — margin from +4 to +49.**

### Four families agree on the winner and disagree wildly on the margin

Same transcript, `healthcare-14b-pro`, 14b pro against 0.6b con:

| judge | family | pro | con | gap |
|---|---|---|---|---|
| `qwen3:8b` | qwen3 | 91 | 86 | **+5** |
| `phi4-mini` | phi3 | 80 | 76 | **+4** |
| `selene:8b-16k` | llama3.1 | 83 | 63 | **+20** |
| `gemma4:12b` | gemma4 | 93 | 44 | **+49** |

**Every judge picks the same winner; the margin ranges from +4 to +49.** So an
ordering is worth quoting and a *margin* is not — it is a statement about the
judge. This is `JUDGE-VALIDATION`'s "only its ordering passes" generalising to
every judge here, and it is the single most reusable result on this page.

## The judge chosen as the prompt-track instrument, 2026-09-19 (ADR-035)

Picking a judge to *run debates through* and picking one to **hold fixed while
the prompt varies** are different problems, and the second one has a
disqualifying criterion the first does not: the instrument must not be the model
the hypothesis was built on.

All five data points in the emphasis finding — ADR-019's emphasis block,
condition B, condition C, ADR-030, ADR-034 — are `qwen3:8b`. So `qwen3:8b`
cannot test whether "foregrounding a question shrinks the ledger" is a fact about
prompts or a fact about `qwen3:8b`. **ADR-035 makes `phi4:14b` the standing
judge for that track**, with `qwen3:8b` kept as back-reference.

Measured on the three prep transcripts, `--strict-json` on:

| transcript | `qwen3:8b` claims / labels | `phi4:14b` claims / labels |
|---|---|---|
| `healthcare-0.6b-pro` | 12 / 2 | **21 / 4** |
| `healthcare-14b-pro` | 16 / 2 | **44 / 4** |
| `medicaid-14b-pro` | 12 / 3 | **36 / 4** |

`phi4:14b` returns 2–3× the claims and uses **all four verdicts on 3 of 3**;
`qwen3:8b` emits **zero `not_checkable` on all three**, so a quarter of the space
a prompt change could move a verdict into is dead on it.

**`phi4:14b` reproduces.** Two independent draws on `medicaid-14b-pro`,
`judged_at` 16:19:59Z and 20:12:34Z on 2026-09-17 — **three hours fifty-three
minutes apart**, other models loaded in between — gave a byte-identical
`fact_check` object, `68d29c1aba455515`. Load state was *not* controlled, so this
is not the cold/warm result `qwen3:8b` has; B6's two-draws-per-state protocol
should be run on it before the first A/B is quoted.

It is also the only judge tested this week that needed **no `num_ctx` capping** —
`trained_ctx` 16,384, 9.1 GB, fits as shipped — against four that did.

**What it does not have:** a Tau-C. Ordering claims stay `qwen3:8b`'s. And its
24-of-44 `not_checkable` on `healthcare-14b-pro` leans the same way
`command-r:35b` does, with one of its cross-side contradictions already shown to
be a false positive.

### `phi4:14b` fails the citation rule too — 2026-09-19, one day after ADR-035

The standing instrument, `--strict-json` on, judging three transcripts of one
motion. Two succeeded (24 and 28 claims). The third **failed**:

```
judge: judging failed: claims[23] is contradicted but cites no passage,
       so nothing can check it
```

That is the **same failure mode as Selene and `llama3.1:8b`** — a verdict with
no citation — which `MODEL-COVERAGE` had recorded as their distinctive defect and
as the one thing constrained decoding cannot reach (ADR-032 §6: a cross-field
rule JSON Schema can only express with conditionals, which llama.cpp does not
enforce). It is **three families, not two**, and `phi4:14b`'s previously
recorded failure — doubled quotes — is the one `--strict-json` closed. The
semantic one was underneath it all along.

**This is a caveat on ADR-035, not a retraction of it.** The choice rested on
`phi4:14b` being the only judge that uses all four verdicts and on the emphasis
finding being unfalsifiable on `qwen3:8b`; neither depends on this. But the
instrument fails on roughly 1 transcript in 3, so a prompt A/B must expect a
failed cell and say so rather than quietly comparing the two that worked.

`_evidence_citations` catching it is ADR-032 §6 earning its keep for the third
time, and the failure named the claim index, the verdict and what was missing —
which is the working rule about a failure carrying its own diagnosis.

### `qwen3:8b`'s frozen baselines, so ADR-034's closing test has a target

`--strict-json` on, before and after ADR-034:

| transcript | claims | `contradicted` |
|---|---|---|
| `healthcare-0.6b-pro` | 12 → 7 | 3 → **0** |
| `healthcare-14b-pro` | 16 → 13 | 2 → 2 |
| `medicaid-14b-pro` | 12 → 10 | 4 → **0** |
| **total** | **40 → 30** | **9 → 2** |

The recorded headline was the ledger, 40 → 30. The sharper number is the second
column: **ADR-034 cost seven of nine `contradicted` verdicts.**

### The score file cannot tell you which arm produced it

Recovering the two columns above meant reading **filenames**. A score file stores
`judge_model`, `judge_budget` and `fact_check_enabled` — and records neither
`strict_json` nor the prompt, both of which demonstrably move the ledger
(ADR-032: parse failures 5 of 9 → 0 of 9, ledgers growing). This is the confound
that spoiled ADR-034's first measurement, and it is why the prompt track starts
by recording the **request shape**, not the prompt alone.

## Families worth testing next, and what to check before pulling one

Five families have been run here (`qwen3`, `qwen3.5`, `gemma4`, `phi3` via
phi4-mini and phi4:14b, and `llama` via mistral-nemo). **Notably absent: Meta's
own Llama**, the most widely used open family, which nothing here has ever
touched.

Selection criteria, learned the hard way this week rather than assumed:

1. **Reasoning or not.** A reasoning model spends `budget` on thinking, which is
   OPEN-QUESTIONS 13. `thinking: false` (ADR-033) now fixes it on Ollama and
   `mlx_lm` — but **not on AFM, which rejects the field** — so a non-reasoning
   model is still the simpler citizen.
2. **`trained_ctx`, checked before pulling.** This predicted memory footprint
   better than parameter count did: `mistral-nemo` is a 7.1 GB model that wanted
   **51.8 GB** resident. Check it, and cap with `num_ctx` if it is large.
3. **Structured-output reliability** matters much less since ADR-032 — constrained
   decoding took parse failures from 5 of 9 to 0 of 9 — but a model that needed
   constraining to be usable is worth noting as such.
4. **Lineage distance from the debaters**, which is the whole point of a
   cross-family judge.

| candidate | size | why it is interesting | notes |
|---|---|---|---|
| **`llama3.1:8b`** | 4.9 GB | **The biggest gap.** Meta's family is untested here and is the most widely deployed open model; non-reasoning | start here |
| `gemma2:9b` | 5.4 GB | Google's **pre-reasoning** generation — controls generation *within* a vendor, the way `qwen3:4b` vs `qwen3.5:4b` did | pairs with `gemma4:12b` |
| `granite3.3:8b` | 4.9 GB | IBM, explicitly tuned for enterprise structured output | may be the most schema-reliable |
| `command-r:35b` | 18.7 GB | Cohere, **trained for grounded RAG with citations** — which is exactly what the fact-check pass does | large; check memory |
| `olmo2:13b` | 8.4 GB | AI2, fully open training data — a genuinely different data distribution | |
| `mistral-small:24b` | 14.3 GB | Mistral proper, where `mistral-nemo` is an NVIDIA collaboration | |
| `deepseek-r1:14b` | 9.0 GB | Reasoning-first; was removed for disk earlier, and ADR-033 now makes it testable | reasoning |

**The two most valuable, for different reasons:** `llama3.1:8b` because its
absence is the largest hole in the cross-family evidence, and `command-r:35b`
because it is the only candidate specifically trained for the thing the
fact-check is bad at — grounding a claim in a cited passage. That would test
whether OPEN-QUESTIONS 16's borrowed-citation problem is a general LLM failing
or a property of models not trained for it.

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
