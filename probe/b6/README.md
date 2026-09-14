# B6 gate runs

BUILD-GUIDE's B6 exit gate is a **live** check — it asks what a real judge does,
not what the parser accepts. Its three clauses need to appear in **one** run:

1. a claim `supported` by the side's **own** evidence, with correct ids;
2. a claim `contradicted` by the **opponent's** recorded passage — the finding
   `prep_grounded` can never produce, and the reason the pass exists;
3. an opinion marked `not_checkable` rather than a false `unsupported`.

## Why this directory exists

**Every other measured run in this project leaves an artifact behind, and B6's
did not.** `probe/backend/` has its raw rows, `probe/validation/` has every
judged speech, `probe/b0/` has its memory samples. B6's gate runs left nothing,
so when the 2026-09-13 run produced a `contradicted` and the 2026-09-14 run did
not, **the evidence for what differed was already gone** — only commit messages
described it, and a commit message is not a measurement.

That is the failure CLAUDE.md's own rule names: a failure must carry what is
needed to fix it. Save the run.

## How to run one

The gate needs a transcript **with prep evidence**. A prep-less transcript
degrades to all-`not_checkable` by design (ADR-015 §2), so it cannot test
clauses (1) or (2) — four earlier "failures" were runs of exactly that shape,
which is why the diagnosis was wrong for a day.

```bash
# 1. a debate with prep, against pools that exist on disk
DEBATEBENCH_SOURCES_DIR=<pools> debate <run-with-prep.yaml>

# 2. judge it, fact-check on (the default)
judge <transcript.json> --model qwen3:8b \
  --base-url http://127.0.0.1:11434/v1 --budget 6000 \
  --output scores-<label>.json

# 3. keep the score file here, named for model and date
cp scores-<label>.json probe/b6/gate-<model>-<YYYY-MM-DD>.json
```

Then record, in the same commit: which clauses fired, which did not, the model
and backend, and the verdict tally. A run that fails is a result and is kept —
the point is to be able to compare two runs later.

## History so far

| date | model / backend | prep? | (1) supported | (2) contradicted | (3) not_checkable | artifact |
|---|---|---|---|---|---|---|
| 2026-09-13 | qwen3:8b, `vllm-mlx` and Ollama | yes | yes | **yes** | no | **not saved** |
| 2026-09-14 | qwen3:8b, Ollama | no | n/a | n/a | n/a (all, degenerate) | not saved |
| 2026-09-14 | qwen3:8b, Ollama | yes | yes | no | **yes** | not saved |
| 2026-09-14 | qwen3:8b, Ollama, ADR-019 | yes | yes | no | no | `gate-qwen3-8b-2026-09-14.json` |
| 2026-09-14 | qwen3:8b, Ollama, ADR-019 | yes | yes | **yes** (3) | no | `-repeat`, `-s3`…`-s7` (6 runs) |

Each clause has now been seen; never all three together. ADR-019 identifies why
clause (2) stopped appearing: `supported` and `contradicted` were defined by the
same test with no precedence rule, and on a two-sided corpus `supported` was
always a defensible answer. ADR-019 §1 makes contradiction win.

**ADR-019 is a prompt rule with no code enforcement** (its §3), so whether the
judge obeys it is exactly what a run here measures.

**Clause (2) needs a shared pool, not private corpora.** Measured 2026-09-14 on
`examples/run-prep.yaml`, where both sides prep from their own `corpus:` alone:
18 claims, all `supported`, zero `contradicted`. That is not the judge failing
ADR-019 — each team's corpus describes its own invented jurisdictions, so no
two passages bear on the same fact and there is nothing to contradict. A gate
run must use a pool where both sides hold passages on one point, the way
`args-me`'s `am-3` and `am-4` both speak to whether a carbon tax is regressive.

## What the ADR-019 runs measured

Seven runs, one saved prep transcript, same seed, `--budget 6000`, `qwen3:8b`
on Ollama. These are the first B6 gate runs with artifacts, so for the first
time the claims below can be checked rather than recalled.

**Clause (2) is met, and reproducibly.** Six of the seven runs return the same
ledger: 20 claims — 15 `supported`, 3 `contradicted`, 2 `unsupported`. Not
merely the same four counts: with `judged_at` removed the six score files hash
identically (`be6197db7ac41208`). All three contradictions are **cross-side**,
including the con's own `am-4` claim ("a carbon tax is regressive before any
rebate arrives") marked `contradicted` by the pro's `am-3`. That is the finding
`prep_grounded` cannot produce and the stated reason the pass exists.

**The seventh run is run 1, and it is not a control.** It returned 11 claims,
10 `supported`, 1 `unsupported`, zero `contradicted`, and cited `am-4` — the
speaker's *own* backing passage — where the other six cite the contradicting
`am-3`. That is precisely the pre-ADR-019 behaviour, which makes it tempting to
read as an old-prompt control. **It is not**: `judging.py` was saved at
10:41:06 and run 1 started at 10:41:54, so it used the ADR-019 prompt. What
distinguishes it is that it was the first judge call after `llama-server`
loaded at 10:41. Treat it as a cold-server sample, not as evidence about the
prompt.

**Clause (3) is unmet, and the reason is narrower than "the model skips
opinions".** Zero `not_checkable` in all seven runs — but the opinions *are*
listed, which means ADR-015's "Filter nothing out" instruction is working. They
are landing one verdict over: claim 17, "The CON's focus on leakage overlooks
climate urgency", is a value judgement recorded as `unsupported`, and claim 15,
"Rural renewable energy investment can offset fossil fuel reliance", is a
prediction recorded the same way. The prompt defines `unsupported` as "it **is**
a factual claim, but nothing recorded bears on it" and `not_checkable` as "an
opinion, a prediction or a value judgement **rather than** a factual claim", so
the two are decided by one question — is this a factual claim at all? — that
nothing tells the model to ask first.

**One earlier claim on this page's subject is withdrawn.** It was written here
and elsewhere that ADR-019 "traded clause (3) for clause (2)", on the strength
of the 2026-09-14 row above producing a `not_checkable`. That row is a
*different transcript*, and its score file was not saved, so there is no
pre-ADR-019 run on this transcript to compare against. On this transcript
clause (3) has never fired, before or after ADR-019, and no trade has been
measured.
