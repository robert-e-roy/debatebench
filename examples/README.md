# examples

A debate you can run in two commands, and the three files it needs.

```
run.yaml                    one run, no prep: topic, phases, two sides, the judge
run-prep.yaml               the same motion WITH prep, and no dataset download
teams/advocate.yaml         climate-policy advocate
teams/skeptic.yaml          free-market skeptic
teams/social-democrat.yaml  programme design, international precedent   + corpus
teams/tea-party.yaml        enumerated powers, local control            + corpus
teams/neutral.yaml          even-handed analyst, for use as a control   + corpus
```

Any two of the five can face each other, as long as one is `side: pro` and the
other `side: con`. **A team file carries no side** — which side a persona argues
is set in `run.yaml`, so the same file is reused across motions and across
sides.

## Run it

You need a model server. These files assume **Ollama** with `qwen3:8b`, which
is the recommended backend for real runs (ADR-018) — it was measured against
`mlx_lm.server` and `vllm-mlx` in `BACKEND-PROBE-RESULTS.md`.

```bash
ollama serve            # in another terminal, if it isn't running already
ollama pull qwen3:8b    # ~5 GB, once

debate examples/run.yaml     # writes examples/transcript.json
judge  examples/run.yaml     # reads that transcript, writes examples/scores.json
```

Both commands print progress to **stderr** and write JSON to the path in
`run.yaml` and nowhere else, so you never need shell redirection to keep the
output file clean.

Expect the debate to take a few minutes: six speeches, and no backend measured
here serves two requests at once, so the two sides take turns rather than
running together.

## Two commands, not one

`debate` never invokes `judge`. They are separate passes because judging is
cheap and re-running a debate is not — you will often judge one transcript
several times, with different judges, and never want to re-debate to do it.

That is also why `judge` accepts flags that override the file:

```bash
judge examples/run.yaml --model phi4-mini:latest   # same debate, another judge
judge examples/run.yaml --no-fact-check            # scoring only, one call
```

The overriding value is what gets recorded in the score file, so a score never
claims a model that didn't produce it.

`debate` takes the same kind of override, for the model and the budget only:

```bash
debate examples/run.yaml --model phi4-mini:latest    # both sides
debate examples/run.yaml --con-model phi4-mini:latest   # just the con side
```

Same rule: the transcript records what actually ran, not what the file said.
There is no `--output` and no `--seed` — an A/B that needs a different output
path is really two experiments and wants two files, and a seed sweep already
works by deleting `seed:` and reading what each run reports.

## Paths are relative to the file, not to you

`teams/advocate.yaml` and `transcript.json` resolve from `run.yaml`'s own
directory. `debate examples/run.yaml` from the repository root writes
`examples/transcript.json`, not `./transcript.json`. Copy `run.yaml` somewhere
else and its `team:` paths have to move with it or become absolute.

## Not in a `pip install`

The wheel installs the package only, so `pip install debatebench` gives you no
`examples/` directory. These files are in the source tree and the sdist. If you
installed from a wheel, copy the config out of the top-level `README.md`
quickstart instead.

## The teams

The last three carry a `corpus:` — their own research pool, used by the prep
phase. `advocate.yaml` and `skeptic.yaml` do not, which is why `run.yaml` has no
prep and `run-prep.yaml` uses the other pair.

**`neutral.yaml` is a control.** It argues whichever side you assign it, but
from evidence and while stating what the evidence does not settle. Neutral
against neutral isolates the model's contribution; neutral against an advocate
isolates the persona's. Pair it with `debate`'s override flags and you can move
one variable at a time:

```bash
debate run-prep.yaml --model phi4-mini:latest   # same personas, another model
```

### The corpora are fiction, deliberately

Every row in `*-corpus.jsonl` is invented, says so in its own text, and names
places that do not exist — Kessering, Mourne Ridge, the Ostrander review. That
is not laziness about sourcing; it is what makes grounding **testable**. A model
cannot know an invented figure from pretraining, so when a speech cites one, it
demonstrably read the record rather than recalled the world. The fact-check pass
checks claims against the transcript for the same reason.

Do not mistake these for evidence about real carbon pricing. Point `corpus:` at
your own JSONL to use real material:

```json
{"id": "x-1", "topic": "carbon tax", "source": "my-corpus", "text": "…"}
```

A team's own corpus carries **no `side`** field — everything in it already
belongs to that side. Shared `sources:` pools do carry one, because they hold
both sides mixed together.

Each corpus also ends with one deliberately off-topic row, which is filtered out
and is there to prove that filtering happens.

## Prep without downloading anything

`run.yaml` has no `prep` phase. Prep retrieves from JSONL pools that must
already exist on disk, and **nothing downloads them**, so a prep run on a clean
machine fails by design rather than debating from nothing.

**`run-prep.yaml` turns it on without any of that**, because retrieval layers
two pools and either one alone is enough: with no `sources:` key it searches
each team's own `corpus:` and nothing else. That is the whole reason the three
new teams carry corpora.

```bash
debate examples/run-prep.yaml
judge  examples/run-prep.yaml
```

What that produces, measured on `qwen3:8b` with the seed in the file: eight
turns over four phases, five evidence rows recorded per side with no overlap
between them, and a fact-check of **18 claims, all `supported`**, seventeen of
them citing the speaker's own passages by id. Compare `run.yaml`, which can only
ever return `not_checkable` because it records nothing to check against.

**You will not see a `contradicted` verdict here, and that is the corpora's
doing rather than the judge's.** Each team's corpus describes its own invented
world — Kessering, Mourne Ridge — so the two sides never make opposing claims
about the same fact. A contradiction needs both sides holding passages on one
point, which is what the shared `sources:` pools provide and a pair of private
corpora structurally cannot.

> **If `judge` fails with "the reply's JSON is malformed", retrying will not
> help.** `judge` sends the debate's own seed so that re-judging is reproducible
> (ADR-017 §6), which means a malformed reply reproduces byte for byte — four
> attempts on one transcript gave the identical fault at the identical offset.
> Change the judge model, or change `seed:` and re-run `debate`. This is open
> question 14, not a settled design.

To add the *shared* pools on top you need three things, not one:

1. a pool at `~/.cache/debatebench/sources/args-me.jsonl` (or point
   `DEBATEBENCH_SOURCES_DIR` elsewhere), with rows like
   `{"id": "am-1", "topic": "carbon tax", "side": "pro", "source": "args-me", "text": "…"}`;
2. `sources: [args-me]` at the top level of `run.yaml`;
3. `prep` first in `phases`, and a `prep_budget` on **both** sides.

Shared pool names come from a vetted list (`args-me`, `debatesum`) because each
licence was checked by hand — any other name is a config error. A team's own
`corpus:` is a path and has no such restriction.

`prep_budget` without `prep` in `phases`, or `prep` without `prep_budget`, is a
validation error either way — that combination is almost always a half-finished
edit, so it is rejected rather than guessed at.

Prep is worth the setup: without it every factual claim comes back
`not_checkable`, because the fact-check pass checks claims against **what the
transcript recorded**, never against the model's own knowledge. With no
evidence recorded there is nothing to check against, and the score file says so
in a note rather than pretending.

## When it goes wrong

| What you see | What it means |
|---|---|
| `config error: … base_url is required` | Every side needs its own server URL. There is no default, deliberately. |
| `connection refused` | The server named in `base_url` isn't running. |
| `model … not found` | For Ollama, `model:` is Ollama's own name (`qwen3:8b`), not a Hugging Face repo id. Check `ollama list`. |
| `hit budget` on every turn | `budget:` is a hard completion-token cap. Speeches are being cut mid-sentence; raise it. |
| `asks for length 'huge'` | A `:length` suffix is `short`, `medium` or `long` only. Omit it and you get `medium`. |
| `Remove the space after the colon` | `rebuttal: long` is a YAML mapping. The schema wants the string `rebuttal:long`. |
| `judge.output and output are the same file` | The score file would overwrite the transcript. Give it its own path. |
| `has no judge: block` | You ran `judge` against a `run.yaml` without one. Add it, or name a transcript and pass the four flags. |

Every error names the file, the key and, where there is one, the fix. If one
doesn't, that's a bug worth reporting.
