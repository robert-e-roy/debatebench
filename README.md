# debatebench

A command-line tool for running structured, multi-turn, **adversarial** debates
between two LLMs, then scoring the transcript against a fixed rubric.

Two commands:

- **`debate`** — runs the debate, writes a transcript as JSON.
- **`judge`** — reads that transcript, writes a score file as JSON.

Both are thin wrappers over one public module, **`debatebench.api`**, which you
can call directly and give your own backend — see
[*Using it from Python*](#using-it-from-python).

It is built for a narrow job: comparing models, prompts, or personas on
sustained argument, where the interesting signal is how a position survives
contact with a good opponent. There is no consensus, voting, or convergence
logic anywhere in it, and that is deliberate — see *Not in scope*.

## Not the DebateBench benchmark

There is an existing, unrelated **DebateBench**
([arXiv 2502.06279](https://arxiv.org/abs/2502.06279), Feb 2025): a benchmark
*dataset* of British Parliamentary debate transcripts with official adjudication
scores. This project is not it, is not derived from it, and does not include it.

This `debatebench` is a *tool* that generates and scores debates. The name
collision is real and was kept knowingly; if you are looking for the benchmark,
follow the link above.

## Status

Pre-1.0, released on PyPI:

```bash
pip install debatebench
```

Or from a checkout: `pip install .`

**What `0.1.0` claims:** the two commands, their flags, and the three JSON
formats are stable within the 0.1.x line — each file carries a `schema_version`,
and that is the thing to check against. The Python API (`debatebench.api`) is
pre-1.0 on its own terms and may change with a minor version. It does **not**
claim the tool is finished — see the known gap below.

Built and gated so far: config and validation, the backend seam, the phase loop,
transcript writing, prep retrieval, judge scoring, and the fact-check pass.
**One known gap**, stated plainly because it affects a default: see
[`--fact-check`](#fact-check) below.

## Quickstart

You need a running OpenAI-compatible model server. [Ollama](https://ollama.com)
is the recommended one (see *Backends*):

```bash
ollama pull qwen3:8b
ollama serve                      # if it isn't already running
```

Then save this as `run.yaml`, alongside a `teams/` directory holding the two
team files shown under [Team files](#team-files):

```yaml
topic: "A federal carbon tax would do more good than harm."
format:
  phases: [opening:medium, rebuttal:medium, conclusion:short]
teams:
  - team: teams/advocate.yaml
    side: pro
    model: qwen3:8b
    base_url: http://127.0.0.1:11434/v1
    budget: 2000
  - team: teams/skeptic.yaml
    side: con
    model: qwen3:8b
    base_url: http://127.0.0.1:11434/v1
    budget: 2000
seed: 42
output: transcript.json

judge:
  model: qwen3:8b
  base_url: http://127.0.0.1:11434/v1
  budget: 6000
  output: scores.json
```

```bash
debate run.yaml
judge  run.yaml
```

> **Where `examples/` lives.** The wheel installs the package only, so a
> `pip install` gives you no `examples/` directory — paste the config above
> instead. The ready-made `examples/run.yaml` and its team files are in the
> source tree and in the sdist, not in the wheel. If you have them,
> [`examples/README.md`](examples/README.md) walks through running them, turning
> prep on, and what each error means; every key in those files is commented.

`debate` takes the path to a `run.yaml`. Every setting, including where the
transcript goes, lives in that file — and `--model` / `--budget` override it for
a single run, so an A/B needs no second config:

```bash
debate run.yaml --model phi4-mini:latest            # both sides
debate run.yaml --pro-model qwen3:8b --con-model phi4-mini:latest
```

The override changes the config before the run, so the transcript records the
model that actually spoke. There is no `--output` and no `--seed`: see ADR-021
§6 for why each is deliberate.

`judge` takes either the same `run.yaml`, reading its optional `judge:` block
and taking the transcript from `output:`, or a transcript plus flags. The two
are told apart by extension. Flags override the block, so a one-off comparison
needs no edit:

```bash
judge run.yaml --model phi4-mini:latest     # same config, a different judge
```

The transcript-plus-flags form is the only one that works for a transcript with
no `run.yaml` beside it, and it is unchanged:

```bash
judge transcript.json \
  --model qwen3:8b \
  --base-url http://127.0.0.1:11434/v1 \
  --budget 6000 \
  --output scores.json
```

`judge:` is optional — a `run.yaml` without it is valid, and is what every
config written before ADR-020 looks like.

Both commands write **only** their JSON output to the given path. Everything
they say about progress goes to stderr, so the file is never polluted by logs
and you never need shell redirection to keep it clean.

## `run.yaml`

```yaml
topic: "A federal carbon tax would do more good than harm."

format:
  phases: [opening:medium, rebuttal:medium, conclusion:short]

teams:
  - team: teams/advocate.yaml
    side: pro
    model: qwen3:8b
    base_url: http://127.0.0.1:11434/v1
    budget: 2000
  - team: teams/skeptic.yaml
    side: con
    model: qwen3:8b
    base_url: http://127.0.0.1:11434/v1
    budget: 2000

seed: 42
output: transcript.json
```

| Key | |
|---|---|
| `topic` | The motion. Required. |
| `format.phases` | The whole debate, in order. **The only** thing that decides what runs — there are no separate `prep`/`rounds` flags. Repeat a name to repeat a phase. A `:length` suffix is optional and defaults to `medium`. |
| `teams` | Exactly two. One must be `side: pro`, the other `side: con`. |
| `model`, `base_url` | Per team, both required. `base_url` has no default. The two sides may point at different servers. |
| `budget` | Per-phase cap in completion tokens, enforced by the orchestrator. |
| `prep_budget` | Required **if and only if** `prep` is in `phases`. An error either way round. |
| `sources` | Shared retrieval pools. Optional, and only meaningful with `prep`. |
| `seed` | Optional. If omitted, one is generated, logged, and recorded in the transcript — never silently guessed. |
| `output` | Required. The transcript path, resolved relative to the `run.yaml`. |
### Watching a run from another program

`debate --events` writes one JSON object per line to **stdout**, flushed as it
goes, while the human log continues on stderr (ADR-027):

```bash
debate run.yaml --events | my-viewer      # events on stdout, log on stderr
```

The first line is a `run` header carrying the topic, seed, phases, each side's
label/team/model, and a `schema_version`. After it come `phase_started`,
`turn_started`, `turn_completed` (with the speech text, usage and timing),
`phase_completed`, and finally `run_completed` — or `run_failed` with the error.

**The stream is not a transcript.** It is not rotated, not atomic, and a failed
run leaves a partial stream describing turns that were never written anywhere.
Read the `output:` file for the durable record, and **wait for `run_completed`
before you do** — on a failed run, the file sitting at that path belongs to the
*previous* run.

That is the seam for a consumer in another process or another language. In
Python, subscribe to the same events in-process instead: see
[*Using it from Python*](#using-it-from-python).

| `timeout` | Optional, seconds to wait for a reply. Default 600. Raise it for a large reasoning model at a big budget — a 12B model thinking through a long prompt can exceed ten minutes on a cold load. `--timeout` overrides it. |

Response length is a suffix on the phase, `name:length` — `short` (2 sentences),
`medium` (5), `long` (10). No space after the colon. **A phase with no suffix
asks for `medium`**, so `opening` and `opening:medium` are the same run. `prep`
takes no suffix and gets no length instruction — it is bounded by `prep_budget`
alone.

Validation is strict: unknown keys, duplicate keys, an unknown phase name, or
two teams on the same side are all errors, and each one names what it found and
what it expected.

### Team files

Durable identity, referenced by path from `run.yaml`. The Quickstart's
`run.yaml` points at two of them, so create both.

`teams/advocate.yaml`:

```yaml
id: carbon-tax-advocate
name: "Climate Policy Advocate"
voice: "direct, urgency-driven, cites institutional consensus"
stance: progressive
values: [collective-action, precaution, equity]
```

`teams/skeptic.yaml`:

```yaml
id: free-market-skeptic
name: "Free-Market Conservative"
voice: "measured, cost-focused, cites economic evidence"
stance: conservative
values: [limited-government, cost-benefit, individual-liberty]
```

One optional key is omitted above because the Quickstart does not use it:
`corpus: my-corpus.jsonl` points a team at its own private retrieval pool, and
only matters when `prep` is in `phases` — see [Prep](#prep). Naming a corpus
file that does not exist will fail the run.

A team file never carries `model` or `budget`. Those are properties of a run,
not of a persona, and putting them here is rejected.

## Phases

`opening`, `rebuttal`, `retort`, `conclusion`, and the optional `prep`. Phases
are data: the loop iterates the list you configured.

Every configured phase must get a response from **both** sides or the run aborts
and no transcript is written. There is no fallback to one side, no skipping a
failed turn with a log line. A partial debate is not a debate, and a benchmark
that quietly drops turns is worse than one that stops.

### Prep

`prep` gives each side private research before it argues. It is off unless you
put it in `phases`.

Retrieval is deterministic, runs in the orchestrator, and costs no tokens: two
JSONL pools are filtered and ranked in plain Python, and only the *synthesis* of
what came back is a model call, capped by `prep_budget`.

Two pools, filtered differently:

- **Shared pools** (`sources:`) hold both sides' material mixed together, so
  they are filtered on topic **and** side.
- **A team's own `corpus:`** holds only its own material, so it is filtered on
  topic alone.

Rows are JSONL. A shared pool carries `side`; a team corpus does not:

```json
{"id": "am-1", "topic": "carbon tax", "side": "pro", "source": "args-me", "text": "..."}
{"id": "lc-1", "topic": "carbon tax", "source": "my-corpus", "text": "..."}
```

Top 10 per pool. Each side's prep is private to that side — the opponent never
sees it, though the judge does, because scoring evidence grounding requires it.

**Nothing downloads anything.** Pools must already be on disk at
`~/.cache/debatebench/sources/<name>.jsonl`, overridable with
`DEBATEBENCH_SOURCES_DIR`. Shared pool names come from a vetted list
(`args-me`, `debatesum`) because each one's licence was checked by hand; any
other name is a config error. If **both** pools return nothing, the run fails
rather than quietly debating from nothing.

## The judge

One call, both sides, five dimensions scored independently and never blended:

| Dimension | Max |
|---|---|
| `argument_quality` | 30 |
| `evidence_grounding` | 25 |
| `steelman_fidelity` | 20 |
| `rebuttal_effectiveness` | 15 |
| `clarity` | 10 |

The **winner is arithmetic, computed outside the model**: higher total, then
`steelman_fidelity` as the tiebreak, then a coin toss — `run.seed % 2`, so a
tied transcript always resolves the same way and you can check it by hand
(ADR-023). `winner_reason` says which rule decided it, and `coin_toss` means
the scores did not. The model is never asked who won. Every dimension is printed beside the total, because a total on
its own explains nothing.

A dimension that fails to parse is an **error**, never a zero — a zero would be
a silent score.

### What the judge has actually been validated to do

`qwen3:8b` was measured against the 631-speech human-rated dataset from
*Debatable Intelligence* ([arXiv 2506.05062](https://arxiv.org/abs/2506.05062)),
using that paper's own statistic and prompt: **Kendall's Tau-C +0.547** against
the mean of 15 human ratings per speech, with 631/631 replies parsed. The
human-to-human ceiling on the same data, measured leave-one-annotator-out, is
0.405 — so it ranks speeches about as consistently as the annotators agree with
each other.

**Only the ordering is validated. The calibration is not**, and the difference
matters here:

- Human-authored speeches score within 0.18 of human ratings.
- **Machine-generated speeches score 0.95 to 1.52 low.**

Tau-C measures rank and is blind to that gap. So: **comparing the two sides of
one debate is supported** — which is exactly what the winner logic does — while
reading an absolute `argument_quality` as a quality measure, or comparing scores
across different debates, **is not**. The caveat bites hardest here, because
this tool scores machine-generated turns, which is where the judge is least
calibrated.

Unvalidated entirely: the winner logic itself, the steelman tiebreak,
`rebuttal_effectiveness`, and the fact-check pass. Only `qwen3:8b` has been
measured; other judges are unknown.

Pick a judge that is neither debater, and whose context holds a whole
transcript. Apple Foundation Models cannot — its ~4,096-token session limit is
smaller than most transcripts.

### `--fact-check`

**On by default.** It runs a second call that audits each claim against what the
transcript actually records — both sides' evidence and turns — never against the
model's own knowledge of the world. Verdicts are `supported`, `contradicted`,
`unsupported`, and `not_checkable`.

> **Known gap.** This pass has not met its exit gate. Over seventeen runs on one
> saved transcript, no ledger has ever carried a `not_checkable` verdict.
> **An earlier version of this note said the audit "skips non-factual
> statements". That was wrong.** The opinions are listed; they land in
> `unsupported`, one verdict over, because the prompt never told the model to
> ask "is this a factual claim at all?" before asking whether the record backs
> it. ADR-024 makes that the first question; the fix is being measured, not
> assumed. Claims the audit *does* list have been accurate, including ones
> contradicting the opponent's own recorded evidence. Treat the ledger as
> incomplete rather than wrong, and `--no-fact-check` skips the second call.

> **Judge with the model already loaded.** On Ollama the audit is deterministic
> *within* a model load state and not across one: the first call after the model
> is loaded returns a materially thinner ledger than calls that follow it — 11
> claims and zero `contradicted` against 20 and three, on the same transcript
> and seed. A cold judge under-reports. Touch the model first, or hold the state
> constant across any comparison you intend to read.

## Backends

One OpenAI-compatible adapter with a configurable `base_url` covers everything.
A probe of three servers on identical weights
(`BACKEND-PROBE-RESULTS.md`) produced the recommendations here:

| | Notes |
|---|---|
| **Ollama** | **Recommended for real runs.** Honours `response_format` in both modes, queues a second request instead of refusing it, prefills fastest. Costs ~20% decode speed. Model names are Ollama's own (`qwen3:8b`). |
| `vllm-mlx` | Fastest decode. Refuses a concurrent request with HTTP 503. Leaves reasoning inside `content`. |
| `mlx_lm.server` | Ignores `response_format` entirely. Its own authors say it is not for production. Model name must be the exact repo id. |
| Apple Foundation Models | Fine for development via `fm serve`. Context is too small to judge with. |

Things measured that may surprise you:

- **No single token-budget field works everywhere**, so the adapter sends both
  `max_tokens` and `max_completion_tokens` with the same value. AFM honours only
  the second; Ollama and `vllm-mlx` honour only the first.
- **None of the three served two requests in parallel** as configured here —
  they queue or refuse. For Ollama that is a setting, not the server: it runs
  one slot by default (`-np 1`, `OLLAMA_NUM_PARALLEL` unset). Raising it is
  untested; see `BACKEND-PROBE-RESULTS.md`.
- **No server rejects an over-context prompt.** It will try, and can wedge the
  engine for the rest of a run. Watch your budgets.
- Run model servers with `HF_HUB_OFFLINE=1`. Ollama has no Hugging Face
  dependency; its equivalent is `OLLAMA_NO_CLOUD`.
- Check what address your server bound with `lsof`, not with the documentation.
  Ollama has been observed on a wildcard address, reachable off-box.

## Output

Both files are JSON, carry a `schema_version`, and rotate any existing file to
`<path>.1` rather than overwriting it.

The **transcript** records the resolved run (topic, seed, phases, and a snapshot
of each side's team file, so it stays readable after the team file changes) plus
every turn keyed by `(phase_index, side_index)`. Each turn carries its text,
token usage, budget, whether it hit that budget, finish reason, latency, and
start time. Prep turns additionally carry the raw `evidence` passages they were
given. Credentials in a `base_url` are stripped before it is recorded.

The **score file** records the judge model, its budget, every dimension with its
justification, each side's total, the winner and the reason, and — when enabled
— the fact-check ledger.

## Using it from Python

Everything supported is in **`debatebench.api`** and nothing else (ADR-028).
Other module paths are reachable, but internal, and change without notice.

```python
import asyncio
from debatebench.api import debate, judge, load_run, write_transcript, write_scores

config = load_run("run.yaml")
transcript = asyncio.run(debate(config))
write_transcript(transcript, config.output)

sheet = asyncio.run(judge(transcript, model="qwen3:8b",
                          base_url="http://localhost:11434/v1", budget=6000))
print(sheet.winner, sheet.winner_reason, [side.total for side in sheet.sides])
```

Four things to know:

- **Nothing here writes a file.** `debate` returns a `Transcript` and `judge`
  returns a `ScoreSheet`; `write_transcript` and `write_scores` are separate
  calls, and they rotate an existing file exactly as the commands do. One wart:
  `run.yaml` still *requires* `output:`, and `debate()` ignores it.
- **Both are `async`.** Wrap them in `asyncio.run(...)`, or await them from a
  loop you already have. There is no synchronous version, deliberately: it would
  raise inside a running loop, which is where a live viewer would call it.
- **You can bring your own model.** Pass `backends=` (one per side) or
  `backend=`, and no HTTP call is made at all — anything with a single
  `async generate(request)` satisfies the `Backend` protocol:

  ```python
  transcript = asyncio.run(debate(config, backends=[my_pro, my_con]))
  ```

  Omit it and the OpenAI-compatible adapter is built from the config, honouring
  its `timeout`. `Backend` is a *static* typing `Protocol`: your type checker
  verifies it structurally, and `isinstance(mine, Backend)` raises `TypeError`
  rather than answering. That is deliberate — a runtime check could only confirm
  that a `generate` attribute exists, not that it is `async` or takes the right
  argument, and a misleading `True` is worse than no check.
- **You can watch a run in-process.** Subscribe to the same event bus the
  `--events` stream is built on:

  ```python
  from debatebench.api import EventBus, EventType

  bus = EventBus()
  bus.subscribe(lambda e: print(e.type, e.phase_index))
  transcript = asyncio.run(debate(config, events=bus))
  ```

  `make_event_writer(config)` is exported too, if you want the ADR-027 JSONL
  written to a stream of your own.

Failures raise: `ConfigError`, `DebateError`, `JudgeError`, `BackendError`,
`TranscriptError`, `RetrievalError`. They have no common base class yet.

**Stability.** `debatebench.api` is pre-1.0 and may change with a minor version;
each change gets an ADR and a note here. The **file formats** are the durable
contract — the transcript, the score file and the event stream each carry a
`schema_version`. If you need a stronger promise than pre-1.0 Python, read and
write the JSON.

## Not in scope

Deliberately absent, and not to be added casually:

- **Consensus, voting, or convergence logic.** The premise is sustained,
  non-converging adversarial positions. Consensus-seeking in the turn loop is
  the specific thing that ruled out the projects reviewed before this one.
- **Formal verification** of claims. Domain-mismatched for non-formalizable
  motions.
- **Cloud-provider-specific features**, and **UI or dashboard code**.

## Testing

```bash
pytest
```

Every default test runs against a scripted fake backend, so the suite is
deterministic and needs no model. Live-model tests are opt-in:

```bash
DEBATEBENCH_LIVE_TESTS=1 pytest
```

## Licence

MIT — see `LICENSE`. Design lifted from four MIT-licensed projects is
attributed in `NOTICE`.
