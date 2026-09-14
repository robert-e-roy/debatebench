# Backend Probe — Results (session 1, complete but for A11)

**Status:** **Part A is complete for all three servers on the same model**,
except A11, which is **deferred to the operator by decision (2026-09-14)**
rather than left blank — see "A11 — the operator's check" below. **Part B is
complete**, including B5 under `mlx_lm`. The exit gate in `BACKEND-PROBE.md`
("every row in A and B filled in for all three servers") is **met with that one
stated exception**, which the gate itself now records.

An earlier version of this line also excepted A8 on `vllm-mlx` as "abandoned
when it wedged the engine". That was stale: A8 was re-run with the corrected
~37k prompt and is in the table below.

**No recommendation is made here.** It lives in **ADR-018**, which cites this
file — the shape the exit gate asks for, rather than a silent switch.

**Not** written to `RESULTS.md`: that file is B0's and would have been
destroyed.

**Date:** 2026-09-13. **Machine:** Mac14,12 (M2 Pro), 32 GiB unified memory,
macOS 27.0. At baseline: load ~2.2, 91% memory free, Claude Code + Terminal +
a chat app running. B0's own caveat applies — a busier or quieter machine
gives different numbers.

---

## Part Zero — what was tested

| | Identity | Version | Licence |
|---|---|---|---|
| `vllm-mlx` | **`github.com/vllm-mlx/vllm-mlx`** | 0.4.1 (wheel) | Apache-2.0 |
| `mlx_lm.server` | `github.com/ml-explore/mlx-lm` | mlx-lm 0.31.3, mlx 0.32.2 | MIT |
| Ollama | Ollama.app | 0.34.0 | MIT (confirmed by the maintainer of this repo) |

**Finding for ADR-003's amendment:** the installed `vllm-mlx` is a **fourth**
project, not one of the three that amendment lists (`vllm-project/vllm-metal`,
`waybarrios/vllm-mlx`, `vllm-swift`). It is its own org, `vllm-mlx/vllm-mlx`,
Apache-2.0. Anyone reproducing this must pin that, not "vllm-mlx".

**`mlx_lm.server` says it is not production software, in its own words.** Every
start prints `UserWarning: mlx_lm.server is not recommended for production as it
only implements basic security checks` (`mlx_lm/server.py:1723`). Neither of the
other two emits such a warning. That is a vendor self-assessment rather than a
measurement, but it bears on any decision to run real work through it,
independently of any row in this file: its own authors scope it to development
use. (No ADR ever made it the default — see ADR-018's opening correction.)

Ollama's licence is **MIT**, confirmed by this repo's maintainer. Worth noting
how it was *not* established: the only licence file this probe found in the app
bundle was `MLX_C_LICENSE` (MIT), which covers a **bundled dependency** rather
than Ollama itself, and reading that as Ollama's own licence would have been
wrong. Recorded here as attested, not as measured.

Models: `mlx-community/Qwen3-8B-4bit` on both Python servers. **Ollama could
not serve it** — it has only `phi4-mini` and `ornith-coder` locally, and
pulling would need network, which contradicts the offline posture A11 tests.
Ollama's rows therefore ran on **`phi4-mini`** and are *not* like-for-like.

---

## Part A — API compatibility

All three columns are **Qwen3-8B 4-bit**: `mlx-community/Qwen3-8B-4bit` on both
Python servers, `qwen3:8b` on Ollama (Q4_K_M GGUF — same family and bit-width
class, not byte-identical weights). Ollama's earlier `phi4-mini` pass is kept in
`probe/backend/probe-a-ollama.json`; it is not comparable and is not used here.

| # | `vllm-mlx` | `mlx_lm.server` | Ollama |
|---|---|---|---|
| A1 `max_tokens` | **honoured** — exactly 20 | **honoured** — exactly 20 | **honoured** — 20, `length` |
| A1 `max_completion_tokens` | **ignored** — 305 tokens | **honoured** — exactly 20 | **ignored** — 1287 tokens, `stop` |
| A2 `json_object` | **honoured** — `{"answer": "four"}` unprompted | **NOT honoured** — answered in prose | **honoured** — JSON unprompted |
| A3 `json_schema` | **honoured, conforms** | **NOT honoured** — returned prose, "Two plus two is **4**." | **honoured, conforms** |
| A4 `stream: false` | one JSON object | one JSON object | one JSON object |
| A5 seed 42 + temp 0, twice | **identical** | **identical** | **identical** |
| A6 usage | present, non-zero | present, non-zero (+`prompt_tokens_details`) | present, non-zero (+`prompt_tokens_details`) |
| A7 tiny budget, `finish_reason` | `stop` at **713** tokens (cap ignored, truncation unsignalled) | **`length`** at exactly 10 | **`length`** at exactly 10 |
| A8 over-context | **no rejection**; wedges the engine. 160k-token prompt: still generating at 260 s. **Re-run at ~37k, a modest overage: same result** — timeout at 180 s, engine wedged again, free memory to 12% | **no rejection**; ballooned to **23 GB**, client timeout at 180 s (~160k-token prompt) | **no rejection**; client timeout at 180 s (~37k-token prompt) |
| A9 reasoning field | **no separate field** — `<think>` inside `content`, despite `--reasoning-parser qwen3` | **separate `reasoning` field**, alongside `content` | **separate `reasoning` field**, alongside `content` |
| A10 bind address | `127.0.0.1` | `127.0.0.1` | **`*:11434` — wildcard, reachable off-box** |
| A11 offline start | **operator check** — started clean under `HF_HUB_OFFLINE=1` and `--offline`, which is the weak evidence the row rules out | **operator check** — started clean under `HF_HUB_OFFLINE=1`, same caveat | **a different question** — no `huggingface_hub` anywhere; its levers are `OLLAMA_NO_CLOUD` and `disable_ollama_cloud` |

**A2 and A3 together are the rows ADR-013's open question needed, and they
divide 2–1.** `mlx_lm.server` **ignores `response_format` entirely**, in both
modes: prose for
"What is two plus two?" under `json_object` *and* under a strict `json_schema`.
`vllm-mlx` and Ollama honour both, returning JSON unprompted and conforming to
the schema when given one.

That distinction is the whole point. `json_object` is only a hint — the model
may still emit the invalid `\'` escapes and mangled keys that cost most of
2026-09-12/13. **`json_schema` constrains decoding to the grammar**, which
would retire that failure class rather than repairing around it. The default
backend offers neither.

### Why the gaps

- **mlx_lm A2/A3/A5: re-run and now measured** — see the table. The first pass
  failed for two compounding reasons, and only one was a parsing bug. The probe
  fell back to printing the response envelope when extraction failed (fixed),
  but the *reason* extraction found nothing was **budget starvation**: at 60–120
  tokens, Qwen3 through `mlx_lm` spent the whole budget thinking and returned a
  message with a `reasoning` key and no `content` at all. That is
  OPEN-QUESTIONS 13, and it is the same trap the judge hit before its budget
  went to 6000. The rows were re-run at 2000 tokens
  (`probe-a-mlx_lm-budgeted.json`). Calling it "an instrument failure" was half
  right and is corrected here.
- **vllm-mlx A9:** blocked during the first pass — A8's prompt wedged the
  generation route, two attempts returned HTTP 503 `text_generation_busy`, and
  ~20 minutes later it still had not cleared. **Measured after the server was
  restarted**, and the answer is in the table above.
- **mlx_lm A9:** the first run died at A8 and never reached it. **Measured on
  the re-run**, and the answer is in the table above.
- **A11 everywhere:** deferred to the operator by decision, not skipped — the
  procedure and the per-server levers are in the next section. Both Python
  servers did start clean under offline flags, which is exactly the evidence
  the row says is insufficient.

### A11 — the operator's check (not run here)

The row asks for zero network calls at startup, "confirmed via a packet capture
or a firewall block, **not just absence of an error**." That standard is right,
and this probe did not meet it: both Python servers were started with
`HF_HUB_OFFLINE=1` (and `--offline` on `vllm-mlx`) and raised no network error,
which is precisely the weaker evidence the row rules out.

It is **deferred to whoever operates the machine**, for two reasons: the check
needs the network cut for the duration of a start, which a probe sharing a
machine with live work should not do — and it takes about two minutes.

1. **Turn Wi-Fi off** (or unplug the cable). *This is the firewall block the row
   asks for* — nothing needs installing.
2. Start the server the way a run starts it, with the levers below set.
3. Serve one request against a model that is already local.
4. **A clean start and a served reply is a pass.** A hang, a timeout, or any
   `huggingface.co` error in the log is a fail — and the error text is the
   finding, so capture it rather than just noting that it failed.

To *see* the absence rather than infer it, with the network still up, any one of:

- `nettop -m tcp -p <pid>` — that process's sockets, live, nothing to install
- `sudo lsof -i -nP -p <pid>` — what the pid has open right now
- `sudo tcpdump -n host huggingface.co` — the packet capture the row names

**The lever differs by server, which is why "not applicable" was the wrong entry
for Ollama** — the row's premise simply doesn't reach it:

| | What reaches the network at start | Lever |
|---|---|---|
| `vllm-mlx` 0.4.1 | `huggingface_hub` resolving the repo id | `HF_HUB_OFFLINE=1`, plus its own `--offline` |
| `mlx_lm` 0.31.3 | the same `huggingface_hub` path | `HF_HUB_OFFLINE=1` (ADR-002 already requires it) |
| Ollama 0.34.0 | **no `huggingface_hub` at all** — its own registry, and a pulled model is already on disk | `OLLAMA_NO_CLOUD=1`, and `disable_ollama_cloud` in `~/.ollama/server.json` |

Read off the installed versions rather than assumed: `huggingface_hub` **1.31.0**
exposes `HF_HUB_OFFLINE` (default `False`) beside `ENDPOINT =
'https://huggingface.co'`, and Ollama **0.34.0**'s `ollama help serve` lists
`OLLAMA_NO_CLOUD` and no Hugging Face variable of any kind. **Re-check after any
upgrade** — these are the projects' own release notes, not ours:
`github.com/huggingface/huggingface_hub/releases`,
`github.com/ollama/ollama/releases`, `github.com/ml-explore/mlx-lm/releases`.

### Method corrections made during the run

- **A1's first Ollama reading was wrong and was redone.** "Name three colours"
  answers in 6–7 tokens, so a 20-token cap never bound and both fields looked
  honoured. Re-run with a 400-word essay prompt, which is what produced the
  table above. The vllm-mlx A1 reading was decisive on the original prompt
  (20 vs 305) and was not affected.
- **A2's first reading was confounded for all three servers and was redone.**
  The prompt was *"Reply with a JSON object mapping 'answer' to the number 4"* —
  a model emits JSON there whether or not the server honours `response_format`,
  so a pass proved nothing. Re-run with *"What is two plus two?"*, a question
  that would not naturally produce JSON, the row separates cleanly: `vllm-mlx`
  and Ollama return JSON unprompted, `mlx_lm` answers in prose. Same class of
  error as the A1 prompt above: testing a cap, or a mode, with an input that
  never exercises it.
- **`ps -o rss` is the wrong instrument** on Apple Silicon and its readings
  (8 MB for a process holding an 8B model) were discarded. B0 used macOS
  `footprint -p <pid>`, and that is what Part B below uses.

---

## Part B — performance

Taken with `footprint(1)`, B0's instrument, on a settled machine (88% free,
load 1.59, `vllm-mlx` the only resident model server). The instrument refuses
to record a timing row below 60% free rather than publish a figure that
measures swap.

| # | Measured | Result |
|---|---|---|
| B2 | `vllm-mlx`, Qwen3-8B-4bit, **at rest after a clean start** | **5.0 GB** `phys_footprint` (B0: 4.8 GiB, same weights) |
| B2 | `vllm-mlx`, same model, **while wedged on a ~160k-token prompt** | 12 GB (see correction below) |
| B2 | `mlx_lm`, same model, during a ~160k-token prompt | **23 GB**, peak 23 GB |
| B3 | `vllm-mlx` decode, short prompt, warm | **36.6 tok/s** — two samples, both 36.6 (B0: 33.9 under `mlx_lm`) |
| B4 | `vllm-mlx`, 3,313-token prompt | 16.1 s to last token, **~205 tok/s** prefill — an **upper bound**, see below |
| B6 | `vllm-mlx` concurrency | **serialized** — the second call returned **HTTP 503 in 0.08 s and was never served**; Part A's error text says `blocking_serialized … waiters=0` |
| B2 | `mlx_lm`, Qwen3-8B-4bit at rest | **5,118 MB** — the same as `vllm-mlx`'s 5,011 MB and B0's 4.8 GiB |
| B3 | `mlx_lm` decode, short prompt, warm | **33.5 tok/s** (samples 33.5, 32.2) — B0 measured **33.9** for these weights |
| B4 | `mlx_lm`, 3,313-token prompt | 17.0 s to last token, **~195 tok/s** prefill (upper bound, as above) |
| B6 | `mlx_lm` concurrency | **serialized but queued** — the second call *was* served (200, 120 tokens), taking 1.78× a single call |
| B1 | both Python servers | **not comparable to B0 — see below** |
| B3 | Ollama decode, short prompt, warm | **29.1 tok/s** (samples 29.1, 29.1) — slowest of the three |
| B4 | Ollama, 3,315-token prompt | 13.6 s to last token, **~243 tok/s** prefill — fastest of the three (upper bound, as above) |
| B6 | Ollama concurrency | **serialized but queued** — second call served (200, 120 tokens), 1.91× a single call |
| B2 | Ollama | not measured — its model runs in a child `runner` process that is absent at rest, so `footprint` has no stable target |
| B5 | `mlx_lm`, Qwen3-8B **+** Mistral-Small-24B co-resident | **18.0 GiB, both held** — no critical pressure, floor never approached |
| B5 | `vllm-mlx`, Ollama | **not testable as invoked** — see below |

**B5 is the row B0 never finished, and the pair fits.** `mlx_lm` held both
models at **18.0 GiB** (Qwen3-8B alone 4.95, Mistral-Small-24B 13.0, both
18.0). Alongside `vllm-mlx`'s resident 5.0 GB that is ~23 GB on a 32 GB
machine, and it ran at **78–79% free with swap flat at 4.86 GB**, never nearing
the instrument's 10% floor. B0 estimated the pair at ~19.6 GiB and hit critical
pressure before completing the stage; this run did not. The difference is not
that B0 was wrong — B0 measured alongside a working desktop and said so — but
it does mean **the pair is viable on a quiet machine**, which B0 left open.

**Mid-run I concluded the opposite and had to correct it.** After the large
model loaded, the process sat at 13.0 GiB — Mistral's own size — which looked
like eviction rather than co-residence. Re-requesting Qwen3-8B took 6.2 s and
took the footprint to 18.0 GiB, and a second call returned in 0.3 s with the
footprint unchanged: both retained. The run had simply ended before the pair
were simultaneously resident, and the "17 GiB peak" was that transition, not a
swap.

**Not testable elsewhere, which is itself the finding.** `vllm-mlx` was invoked
as `vllm-mlx serve <one model>`, so a single process cannot hold two; testing
it needs a second server instance and twice the overhead. Ollama has no 24B
pulled, and fetching one needs network, which A11's offline posture excludes.

**`mlx_lm`'s B3 reproduces B0's headline almost exactly — 33.5 against 33.9 —
which is the best evidence the instrument is sound.** Read together, the three
servers are far closer than any single reading suggested today, and no one of
them wins outright:

| | decode (B3) | prefill (B4, upper bound) | second simultaneous request (B6) |
|---|---|---|---|
| `vllm-mlx` | **36.6 tok/s** | ~205 tok/s | **refused**, HTTP 503, never served |
| `mlx_lm` | 33.5 tok/s | ~195 tok/s | queued and served, 1.78× |
| Ollama | 29.1 tok/s | **~243 tok/s** | queued and served, 1.91× |

Decode and prefill rank in opposite orders: `vllm-mlx` decodes fastest and
prefills slowest, Ollama the reverse. Memory is within 2% across all three and
against B0's 4.8 GiB. **None of them runs two requests in parallel** — the
difference is only whether the second is queued or refused, and `vllm-mlx` is
the one that refuses.

**Amended 2026-09-14: for Ollama that sentence describes a setting, not the
server.** Ollama's row was measured against whatever slot count it chose for
itself, and it was never asked what that count was. It is `-np 1`: the app's
`llama-server` is launched with a single slot, and `OLLAMA_NUM_PARALLEL` was
unset. So "Ollama does not run two requests in parallel" is true of the machine
as configured and says nothing about Ollama.

Re-measured on the app server, `phi4-mini`, 120 completion tokens per call,
one warm-up call discarded: two single calls at 2.24 s and 2.22 s, two
simultaneous calls finishing at 2.22 s and 4.44 s for a 4.44 s wall —
**1.99×, serialized**, with 120 tokens returned by every call. The original row
reproduces exactly, and now names its cause.

**What raising the slot count does is still unmeasured, and is recorded here as
unmeasured.** Launching a second `ollama serve` with `OLLAMA_NUM_PARALLEL=4`
does reach `llama-server` — its argv carries `-np 4` against the app's `-np 1`,
so the setting takes effect. But that server answered every generation with
`"model": ""`, `"content": ""`, `created: -62135596800` and zero tokens: its
blob store is incomplete (`failed to refresh model list cache … no such file or
directory`). A ratio computed from those replies came out at 1.08× and would
have been published as "parallel". **It is two empty responses racing, which is
the same mistake as the `vllm-mlx` 503 below** — a fast answer that was never
a generation. No parallel-throughput number is claimed here.

Testing it properly means `OLLAMA_NUM_PARALLEL=4` on the *app's* server, which
is a restart of the app, and a model whose weights are actually present. Until
that is run, treat the serialization as a property of this machine's default
and not a reason to prefer or reject Ollama. ADR-018 chose Ollama partly
because it queues a second request where `vllm-mlx` refuses one; that
comparison is unaffected, since it is about what happens when the slots are
full either way.

**B1 is reported as not comparable, deliberately.** Launch to first
`/v1/models` answer was 5 s, and the first *generation* 1.1 s — but that means
the weights were already in the OS file cache after a day of loading them, not
that a cold start takes 5 s. B0's 37.6 s was measured on a genuinely cold
machine. Publishing 5 s against 37.6 s would claim a 7× improvement that is
really a warm page cache, so both numbers are recorded and neither is compared.

Observations that bear on the rows above:

- **B3 nearly went in wrong, and the correction is the point.** The first
  sample read **9.3 tok/s**, which would have published `vllm-mlx` as 3.6×
  slower than B0's figure for identical weights. It was a cold first generation
  on an idle server; re-taken warm it is 35.7 then 36.6. The instrument now
  discards a warm-up call and reports two samples, because a single unrepeated
  sample has produced a false headline three times in this session.
- **B6's "ratio 1.0" was a rejection, not concurrency.** The second call
  returned in 0.08 s, and the first version of that row timed it and called it
  parallelism. Checking the status shows **503, no tokens, never served**. The
  row now records status and token count and will not call anything concurrent
  that was turned away.
- **B4 is non-streaming**, so it times the *last* token. B0 had a streaming
  client for true time-to-first-token and this does not; ~205 tok/s is an upper
  bound on prefill, not a like-for-like figure.

- **Correction (same session).** An earlier version of this file said
  "vllm-mlx's 12 GB is roughly double B0's figure for the same model," and that
  was wrong. The 12 GB was measured while the server was wedged holding the KV
  cache for a ~160k-token prompt — my own A8 row — not at rest. Measured again
  after a clean restart, it is **5.0 GB**, against B0's 4.8 GiB after load for
  the same weights on the same machine: **the same, not double.** The claim was
  also asserted in a commit message, which this corrects. It is a good example
  of why a footprint reading has to record what the server was *doing* when it
  was taken.
- **mlx_lm's 23 GB is consistent with B0's KV-cache measurement** of
  144 KiB/token for Qwen3-8B: a ~160k-token prompt is ~23 GB of cache. It does
  not refuse an over-context prompt; it tries to allocate for it.
- **B6 is answered for `vllm-mlx` by its own error text**, not by a timing
  test: the route is explicitly serialized. The vLLM name does not imply
  vLLM's concurrency here. Not yet tested on the other two.

**Part B's timings (B1/B3/B4) must be taken on a recovered machine.** Free
memory was 12–13% at the end of this session with `vllm-mlx` still holding
12 GB, so any latency number taken now would measure swap, not the server.

---

## Operational findings (not rows, but they bind the tool)

1. **A client timeout does not cancel server-side generation.** Confirmed on
   both `vllm-mlx` and `mlx_lm`. On `vllm-mlx` one oversized prompt made the
   server unusable for ~20 minutes — every later request, including a trivial
   one, got 503. On `mlx_lm` the 23 GB was still held after both the client and
   the driving process had exited; only killing the server released it.
   For `debatebench` this means a single bad `budget`/prompt can take a backend
   out of service for the rest of a run.

   **This is not an artefact of an absurd prompt.** The first A8 sent ~160k
   tokens, 5× the context window, which invited the objection that nobody would
   do that. Re-run at **~37k — a modest overage on a ~32k window** — the result
   was identical: no rejection, timeout at 180 s, engine wedged again, free
   memory down to 12%. A prompt only slightly too long does the same damage as
   one grossly too long, and neither is refused up front.
2. **No single budget field works everywhere**, now confirmed on identical
   weights rather than inferred across different ones. `max_tokens` is honoured
   by all three servers here and ignored by AFM (ADR-003).
   `max_completion_tokens` — **which is what the adapter currently sends**
   (ADR-003, ADR-009) — is honoured by `mlx_lm` and AFM and **ignored by
   `vllm-mlx` and Ollama**: against a cap of 20 they returned 305 and 1287
   completion tokens respectively, both with `finish_reason: "stop"`. On those
   two the orchestrator's budget never reaches the server at all; Hard Rule 5
   catches the overshoot after the fact, which is how the 646-token overshoot
   on 2026-09-12 was caught.
3. **`json_schema` is honoured by two of the three, and not by `mlx_lm`.** An
   earlier draft of this finding said "both servers that could be tested",
   written while `mlx_lm`'s rows were still unmeasured; all three were tested
   later and it ignores `response_format` in both modes. This is
   the row ADR-013's open question needed. Structured output would remove the
   malformed-JSON failures that cost most of this session, rather than
   validating around them.
4. **Ollama binds a wildcard address here.** `*:11434`, reachable from the
   network, where both Python servers bind loopback. **Re-verified 2026-09-14**
   with `lsof -nP -iTCP:11434 -sTCP:LISTEN` (`*:11434 (LISTEN)`), and a request
   to this machine's own en0 address answered 200. Two details worth carrying:
   `ollama help serve` on 0.34.0 documents the default as `127.0.0.1:11434`,
   and `OLLAMA_HOST` is unset on this machine — yet the app-launched server is
   on the wildcard anyway. **Check a bind with `lsof`; never infer it from a
   documented default.**
5. **The judge's fact-check audit produces malformed JSON on every backend
   tried — four of them.** `mlx_lm` (Qwen3-8B), Ollama (phi4-mini), `vllm-mlx`
   (Qwen3-8B) and Ollama (qwen3:8b) have each broken it, in four distinct ways:
   a Python-style `\'` escape, a lone string where a key belongs (`"ver/Cited
   by the CON's opening passage"`), a phase index pointing at a turn that does
   not exist, and a truncated key (`"phase, 1,` where `"phase_index": 1,`
   belongs). The *scoring* call parses reliably on all of them. Only the audit
   fails, which points at the audit prompt — longer, more items, more
   coordinates to copy — rather than at any server.

   On Ollama it is **deterministic, not flaky**: two runs of the same command
   failed identically, same fault at the same character offset. On `vllm-mlx`
   it varied between runs. So retrying is not a fix on either.

   **Largely fixed 2026-09-13 without `response_format`.** Three of the four
   corruptions were in the coordinate fields, not the prose — the model was
   mis-transcribing `phase_index`/`side_index`. The audit now cites the `turn`
   number the rendering already prints, and the coordinates are mapped back in
   code; the recorded claim and the score file still carry both (ADR-015 §4).
   On Ollama, where the corruption had been *deterministic* — two runs failing
   identically at the same character offset — two consecutive runs afterwards
   parsed cleanly. Removing what the model had to transcribe fixed what
   instructing it more firmly had not.

   Sending `response_format` remains the stronger guarantee, and remains
   deliberately not done: it weakens ADR-013's parse-failure rule and ADR-017
   §8's reported/absent distinction, and making a failing gate pass by removing
   the check it fails is the move this project refuses. It needs its own
   decision, after open question 6.

   **What is left is not a JSON problem.** B6's gate still fails, on both
   `vllm-mlx` and Ollama, for one narrow reason: the audit does not list the
   opinion ("This is the most important moral question of our time") at all, so
   no claim is ever marked `not_checkable`. The prompt says "list every
   assertion … Filter nothing out" and the model overrides it — the prior that
   a fact-check audits *facts* beats the instruction. Two prompt attempts have
   not shifted it. That is a classification problem, not a format one, and it
   is the only thing between B6 and its gate.
6. **A5 never tested the request this tool actually sends, and the gap is now
   closed.** The row reads "seed 42 **+ temperature 0**, twice → identical" —
   but `GenerationRequest` (ADR-009) carries only `messages`,
   `max_completion_tokens` and `seed`. **`debatebench` never sends
   `temperature` at all**, so A5 measured a shape the adapter does not produce,
   and "seeded runs are reproducible" was an inference rather than a
   measurement.

   **Measured directly on Ollama 0.34.0 / `qwen3:8b`, 2026-09-14:** two
   identical seeded calls with **no** `temperature` field returned
   byte-identical text (sha `7f08cbca…`, 472 chars, twice). The control, seed
   plus `temperature: 0`, was also self-identical (sha `88468b7a…`, 571 chars,
   twice) and — as expected — differs from the no-temperature output, since the
   sampling parameter differs. **Seed alone pins output here**; no
   `temperature` field is needed for reproducibility on this backend.

   This closes a question that came up while chasing B6's gate, where an audit
   returning 11, 18 and 20 claims from identical input looked like unpinned
   sampling. It was not: three consecutive audits later reproduced each other
   exactly. Worth noting how the measurement nearly went wrong too — the first
   call in each group returned empty because it was **queued behind a
   concurrent judge run and timed out waiting**. That is Part B's B6 result
   ("none of them runs two requests in parallel"; Ollama queues rather than
   refusing) biting the instrument rather than the subject. Run one thing at a
   time against one server, or both the timing and the payload are suspect.

7. **`vllm-mlx` leaves thinking inside `content`, even with
   `--reasoning-parser qwen3`.** The reply carries only a `content` key — no
   `reasoning` or `reasoning_content` — and it opens with `<think>`.
   `mlx_lm.server` separates it into its own field (OPEN-QUESTIONS 13). Two
   consequences: a reasoning model's thinking is charged to the same budget
   *and* returned inline, and any JSON extraction that scans from the first
   `{` to the last `}` can be misled by a brace inside a thinking block. That
   is a risk this probe surfaces, not a diagnosis of any particular failure.

---

## What would finish this

**Part A is complete for all three servers on the same model.** A8 was re-run
on `vllm-mlx` with the corrected ~37k prompt and answered (it wedges the engine
at a modest overage too). **Part B is complete for all three except B5**, with
B1 recorded but explicitly not comparable to B0.

**B5 is done** — the pair fits, at 18.0 GiB, without critical pressure. One row
is genuinely outstanding, and two are closed as not-testable rather than unmet:

- **A11 (offline start) — closed as an operator check, not left unmet.** The
  row's standard is unchanged; what changed is who runs it. Two minutes with
  Wi-Fi off closes it, and the procedure, the per-server levers and the
  release-notes pages to re-check after an upgrade are under "A11 — the
  operator's check". Ollama's column there is a different question rather than a
  missing cell: it has no `huggingface_hub` to put offline.
- **B5 under `vllm-mlx` — not testable as invoked.** `vllm-mlx serve <one
  model>` gives one model per process, so co-residency there means a second
  server instance and twice the fixed overhead. That is a different question
  from the one B5 asks.
- **B5 under Ollama — not testable offline.** No 24B is pulled, and fetching
  one needs network, which A11's own offline posture excludes.

**Every timing row needs a settled machine, and this session kept unsettling
it.** An earlier draft of this line claimed the machine was "quiet again
(~90% free)" — it was not: probing had driven it to 28%. Take these one server
at a time.
