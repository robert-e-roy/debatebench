# examples

A debate you can run in two commands, and the three files it needs.

```
run.yaml              one run: topic, phases, the two sides, and the judge
teams/advocate.yaml   the pro side's identity
teams/skeptic.yaml    the con side's identity
```

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

## No prep here, on purpose

`run.yaml` has no `prep` phase. Prep retrieves from JSONL pools that must
already exist on disk, and **nothing downloads them**, so a prep run on a clean
machine fails by design rather than debating from nothing.

To turn it on you need three things, not one:

1. a pool at `~/.cache/debatebench/sources/args-me.jsonl` (or point
   `DEBATEBENCH_SOURCES_DIR` elsewhere), with rows like
   `{"id": "am-1", "topic": "carbon tax", "side": "pro", "source": "args-me", "text": "…"}`;
2. `sources: [args-me]` at the top level of `run.yaml`;
3. `prep` first in `phases`, and a `prep_budget` on **both** sides.

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
| `judge.output and output are the same file` | The score file would overwrite the transcript. Give it its own path. |
| `has no judge: block` | You ran `judge` against a `run.yaml` without one. Add it, or name a transcript and pass the four flags. |

Every error names the file, the key and, where there is one, the fix. If one
doesn't, that's a bug worth reporting.
