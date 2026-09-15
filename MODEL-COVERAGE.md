# Model Coverage — what has been run, at what size, and what it did

`debatebench` exists to compare models, so the first thing worth knowing about it
is **which models it has actually been run against**. This file is that ledger.
Every row points at the artifact or the ADR that measured it; anything with no
pointer is not a result.

Compiled 2026-09-15 from `RESULTS.md` (B0), `BACKEND-PROBE-RESULTS.md`,
`JUDGE-VALIDATION.md`, `probe/b6/`, `probe/mirror/` and `probe/scale/`.

## The ladder, and the honest summary

| class | model | params | on disk | debater | judge | verdict |
|---|---|---|---|---|---|---|
| small | **AFM** via `fm serve` | ~3B on-device | n/a (system process) | ✅ B1–B4 gates | ❌ **cannot** | plumbing only |
| small | **phi4-mini** | ~3.8B | 2.5 GB | ✅ probe | ⚠️ scores, audit breaks | weakest tested |
| medium | **qwen3:8b** | 8B, reasoning | 5.2 GB | ✅ extensively | ✅ **validated for ordering** | the workhorse |
| medium | **gemma4:12b** | 12B, reasoning | 7.6 GB | ✅ 5 debates | ⚠️ works, slow, hungry | newest, least characterised |
| large | **Mistral-Small-24B-4bit** | 24B | ~13 GB | ❌ **never ran** | ❌ never ran | aborted at load |
| large | **deepseek-r1:32b** @128K | 32B | 19 GB | ❌ never ran | ❌ never ran | 55 GB resident, OOM |
| large | **deepseek-r1:32b-16k** | 32B | 19 GB | untried | ⚠️ **runs, 7.4 tok/s** | fits at 23 GB, thinking can't be disabled |

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

## The gaps, in the order they matter

1. **No large model has ever run.** Every quality finding is 3B–12B.
2. **Only one model's judging is validated**, and only for ordering.
3. **LM Studio is claimed as supported and has never been tested.**
4. **`gemma4:12b` has judged four debates and been characterised in none** — no
   Tau-C, no B6 gate run, no position-bias baseline of its own.
