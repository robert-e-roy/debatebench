# ADR-018: Ollama for Real-Model Runs, and Send Both Budget Fields

**Status:** Accepted
**Date:** 2026-09-13
**Depends on:** ADR-001 (one `openai-compatible` adapter), ADR-002 ("Backend
abstraction", the AFM dev default, the offline requirement), ADR-003 (`fm serve`
and the adapter rules its probe fixed), ADR-009 (request/result types), ADR-013
and ADR-017 (the judge's structured output and the repairs it needed),
`BACKEND-PROBE.md`, `BACKEND-PROBE-RESULTS.md`
**Amends:** ADR-003, rule 2 (see §4)

## A correction this ADR has to make first

`BACKEND-PROBE.md`'s exit gate says a recommendation "changes ADR-003's current
default (`mlx_lm.server`)". **No ADR makes `mlx_lm.server` the default.**
ADR-002 names it twice — once as one of the servers the single adapter covers,
once as the server that contacts huggingface.co at start, which is where the
`HF_HUB_OFFLINE` requirement comes from. ADR-003 is about AFM via `fm serve` and
mentions `mlx_lm.server` only in passing. The one stated default is **AFM as the
*dev* default** for plumbing work (ADR-002), and this ADR does not change it.

So this is not an amendment to a default that never existed. It is the first
decision about **which server real-model runs should use**, a question the ADRs
left open. `BACKEND-PROBE-RESULTS.md` repeated the same mistaken framing and is
corrected alongside this.

## Decision

### 1. Ollama is the recommended server for real-model runs

AFM via `fm serve` remains the dev default for plumbing (ADR-002, unchanged):
instant, free, no load overhead. When a run needs a real model — a genuine
debate, a judge scoring a transcript — use Ollama unless there is a reason not
to. `mlx_lm.server` and `vllm-mlx` remain supported: they go through the same
adapter and nothing here removes them.

### 2. Why, from the measurements

Every row below is in `BACKEND-PROBE-RESULTS.md`, taken on one machine in one
session on Qwen3-8B 4-bit.

- **Structured output, which is the deciding row.** Ollama honours
  `response_format` in both modes — `json_object` and a strict `json_schema`,
  returning conforming JSON. `mlx_lm.server` **ignores both**, answering in
  prose. `vllm-mlx` honours both. This is what ADR-013's open question needed:
  `json_schema` constrains decoding to the grammar, and would **retire** the
  malformed-JSON failures that ADR-017 §4's escape repair exists to paper over,
  rather than repairing them after the fact.
- **Behaviour under a second request.** Ollama queues it and serves it (1.91× a
  single call). `vllm-mlx` **refuses** it — HTTP 503, `blocking_serialized`,
  `waiters=0`. `debatebench` points two debaters and a judge at one machine, so
  a backend that turns away concurrent work is the wrong shape for it.
- **Prefill, which is what a judge call actually costs.** Ollama is fastest at
  ~243 tok/s, against ~205 (`vllm-mlx`) and ~195 (`mlx_lm`). A judge ingests a
  whole transcript; prefill dominates, not decode.
- **One server, many models.** Ollama serves any pulled model by name.
  `vllm-mlx` as invoked (`vllm-mlx serve <one model>`) is one model per process,
  so ADR-002's asymmetric pairing needs two servers and twice the fixed
  overhead.
- **Reasoning is separated.** Ollama returns `reasoning` alongside `content`, as
  `mlx_lm` does. `vllm-mlx` leaves `<think>` inside `content` even with
  `--reasoning-parser qwen3`, which is a hazard for any JSON extraction that
  scans for braces (OPEN-QUESTIONS 13).
- **Licence:** MIT.

### 3. What choosing it costs, stated plainly

- **Decode is ~20% slower** than `vllm-mlx`: 29.1 tok/s against 36.6. Accepted,
  because prefill dominates transcript-sized prompts and this tool is not
  latency-bound — it is a benchmark harness, not an interactive UI. If a long
  debate proves otherwise, revisit with numbers.
- **It does not refuse an over-context prompt.** Neither does any other server
  measured; all three simply grind. Not a discriminator.
- **Weights are not byte-identical across servers.** Ollama's `qwen3:8b` is
  Q4_K_M GGUF where the MLX servers load 4-bit MLX. Cross-server comparisons are
  same-family, not same-file.
- **Model naming differs.** A team's `model` must be what `ollama list` shows
  (`qwen3:8b`), not a Hugging Face repo id. The "exact repo id" rule is
  `mlx_lm`-specific.

### 4. The adapter must send **both** budget fields (amends ADR-003 rule 2)

ADR-003 rule 2 says: send the budget as `max_completion_tokens`, **never**
`max_tokens`. That was correct for AFM and is wrong for everything else:

| | `max_tokens` | `max_completion_tokens` |
|---|---|---|
| AFM (`fm serve`) | ignored | **honoured** |
| `mlx_lm.server` | honoured | honoured |
| `vllm-mlx` | **honoured** | ignored |
| Ollama | **honoured** | ignored |

No single field works everywhere. Against a cap of 20, `vllm-mlx` returned 305
completion tokens and Ollama 1287 — the orchestrator's budget never reached
either server, and Hard Rule 5 caught the overshoot only after the fact.

**The adapter sends both fields, set to the same value.** Each server reads the
one it understands and ignores the other; because the value is identical there
is no conflict to resolve. ADR-003's "never `max_tokens`" is superseded — it
described AFM's quirk as if it were a rule for all servers.

**Implemented 2026-09-13** in `openai_compat.py`, and verified live rather than
assumed: the same request that previously drew 1287 completion tokens from
Ollama now returns 20 with `finish_reason: "length"`, and AFM — which honours
only `max_completion_tokens` and was the real regression risk — still returns
exactly 20 with no objection to the extra field. 272 offline tests and all 7
live AFM tests pass. `vllm-mlx` was not re-checked; its process had exited by
then, and the Ollama result already demonstrates the fix on a server that
ignored the old field.

### 5. Network binding is a run-time requirement, not a defect

Ollama binds `*:11434` — a wildcard, reachable off-box — where both Python
servers bind loopback. **This is deliberate on the dev machine**: the maintainer
toggles Ollama's network access on and off because the same install serves
remote work. It is a configuration choice, not a misconfiguration, and this ADR
does not ask for it to change.

What `debatebench` requires is narrower: **a run must not depend on network
reachability, and the operator must know which mode is active when a run
starts.** For runs where remote access isn't wanted, `OLLAMA_HOST=127.0.0.1`
matches the loopback posture of the other servers. The privacy-first positioning
in ADR-002 is about the tool not reaching out; it says nothing about whether the
operator may reach in.

### 6. Offline

`HF_HUB_OFFLINE=1` (ADR-002) does not apply to Ollama, which doesn't use the
Hugging Face Hub. Its equivalent is that **a run pulls nothing**: models are
pulled in a separate, explicit step beforehand, the same posture ADR-012 §5
takes for `sources` datasets. A11 — proving zero network calls at start with a
packet capture — is unmeasured for every server and stays open.

## Why

The probe was commissioned because "vllm-mlx seems better" needed testing rather
than repeating. It turned out that on raw speed the three servers are close
enough that speed shouldn't decide it — memory within 2% of each other and of
B0, decode spanning 29–37 tok/s, prefill ranking in the opposite order to decode.

What separates them is behaviour, and behaviour maps onto this tool's actual
shape: it makes concurrent calls, it feeds a judge whole transcripts, and its
hardest recurring failure all through 2026-09-12/13 was a model emitting
not-quite-JSON. Ollama is the only server that queues concurrent work *and*
constrains output to a schema *and* prefills fastest. `vllm-mlx` wins decode and
loses the two rows that matter more here.

## Consequences

- **ADR-003 rule 2 is superseded** (§4): send both budget fields. `CLAUDE.md`'s
  backend section repeats the old rule and is updated with it.
- **`openai_compat.py` sends both fields** as of 2026-09-13 (§4). Budgets now
  reach all four servers; before the change they were advisory on two of them.
- **`BACKEND-PROBE.md`'s exit-gate wording is corrected** — it asserts a default
  that no ADR sets.
- **`CLAUDE.md`'s Ollama paragraph is replaced.** It describes only the
  `phi4-mini` pass and its poor scores, which predates the like-for-like
  `qwen3:8b` run.
- **Nothing is removed.** `mlx_lm.server` and `vllm-mlx` still work through the
  same adapter; this is a recommendation with reasons, not an exclusion.

## Open questions

- **Should `debate` and `judge` actually *send* `response_format`?** This ADR
  says Ollama honours it; it does not say the tool uses it. Doing so is a code
  change with its own trade-offs (a schema constrains the judge's output shape,
  which interacts with ADR-013's five-dimension contract) and deserves its own
  decision.
- **LM Studio** has still never been run against.
- **A11** (offline start, verified by packet capture) is unmeasured everywhere.
- **The decode gap** may matter for long multi-phase debates. Revisit with a
  real run, not a probe.
- Whether Ollama's GGUF quantisation changes *debate quality* versus MLX 4-bit
  is untested and is a different question from throughput.
