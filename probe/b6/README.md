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

**Save the transcript too, not just the score file.** Every run below was
recorded by its output alone, so when the diagnosis needed re-testing there was
nothing to re-run. One input survived by luck in a temp directory; the other is
gone.

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
| 2026-09-14 | qwen3:8b, Ollama, ADR-019 | yes | yes | no | no | `rejudge-…-a.json` (= run 1) |
| 2026-09-14 | qwen3:8b, Ollama, ADR-019 | yes | yes | **yes** (3) | no | `rejudge-…-b.json` (= the six) |

The last two rows are the **same transcript, same seed, eleven minutes apart**
— see "The audit is not reproducible" below before reading any row here as a
condition. The input for every 2026-09-14 ADR-019 row is now saved as
`transcript-2026-09-14-gate.json`; earlier rows' inputs were never kept.

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
loaded at 10:41. ~~Treat it as a cold-server sample~~ — **the cold-server
explanation is withdrawn, see the next section.**

## The audit is not reproducible, and this page's determinism claim is wrong

**Measured 2026-09-14 ~17:40–17:51**, after the transcript was finally saved
here (`transcript-2026-09-14-gate.json` — it had survived only in a temporary
directory). Two runs of `judge`, same file, same seed, same model, same
Ollama, eleven minutes apart, nothing changed in between:

| run | artifact | claims | tally |
|---|---|---|---|
| A | `rejudge-2026-09-14-a.json` | 11 | 10 `supported`, 1 `unsupported` |
| B | `rejudge-2026-09-14-b.json` | 20 | 15 `supported`, 3 `contradicted`, 2 `unsupported` |

**Each is byte-identical, `judged_at` removed, to a committed artifact** — A to
run 1, B to the six-run group. So run 1 and runs 2–7 are not two conditions.
They are two draws from one input, and this page's framing of run 1 as a
distinguishable sample was wrong. So was the inference that six identical
ledgers demonstrate determinism: six draws landing in one basin is what that
measures, and A found the other basin on the first try.

**What this invalidates:**

- The cold-server explanation above. Run B was the fresh-load call and returned
  20; the README's run 1 was a fresh-load call and returned 11. The variable
  cannot be load state.
- `BACKEND-PROBE-RESULTS` finding 6's scope. Its measurement stands — two seeded
  472-char replies were byte-identical — but its conclusion was generalised to
  this audit, whose reply is ~4,000 tokens from a reasoning model. It explicitly
  set out to explain "an audit returning 11, 18 and 20 claims from identical
  input" and concluded it "was not" unpinned sampling. On this evidence it is.
- **OPEN-QUESTIONS 14's premise.** "A transcript the judge can't parse is
  permanently unjudgeable" rests on ADR-017 §6 reusing the seed so a malformed
  reply reproduces forever. If the reply is not reproducible, re-running is
  already an escape, and option 2 there needs no seed change at all.
- Any claim that clause (2) is "met reproducibly". It fires in some draws. The
  six-run hash is evidence it *can* fire, not that it reliably does.

**What it does not invalidate.** ADR-019 still changed behaviour: the
pre-ADR-019 ledger on this same transcript is saved here as
`scores-2026-09-14-pre-adr-019.json` (18 claims, 17 `supported`, 1
`not_checkable`), and no post-ADR-019 draw has yet produced a `not_checkable`.
But with draw-to-draw variance this large, one run either side is not a
before/after, and the withdrawal below stands for a second reason.

## Condition B — ADR-024's reorder, measured and REVERTED

Run 2026-09-14 22:28–22:47 under the amended protocol: two draws per load state
against the same transcript. The only change from condition A was moving
`not_checkable` to the top of the prompt's verdict list with one sentence saying
to decide it first.

| state | draws | claims | supported | contradicted | unsupported | not_checkable | hash |
|---|---|---|---|---|---|---|---|
| cold | 2 | 9 | 8 | 1 | 0 | 0 | `6fe57f30f1cc6a38` |
| warm | 2 | 16 | 15 | 0 | 1 | 0 | `6640c71bd6c58b79` |

**The protocol's self-test passes.** Both cold draws are byte-identical and both
warm draws are byte-identical, so within-state determinism holds under a changed
prompt too, and the amendment that replaced N=5 stands.

**The change fails, and costs more than it returns.** Against condition A:

| | A cold | B cold | A warm | B warm |
|---|---|---|---|---|
| claims | 11 | 9 | 20 | 16 |
| `contradicted` | 0 | **1** | **3** | **0** |
| `not_checkable` | 0 | 0 | 0 | 0 |

- **Clause (3) still never fires.** Zero `not_checkable` in all four draws, which
  is what the change existed to produce. ADR-024 §3's hypothesis — that the list
  order was doing the damage — is **falsified**.
- **Clause (2) is lost in the warm state**, 3 cross-side contradictions to none.
  ADR-024 §5 names that trade a regression in advance, and here it was paid for
  nothing.
- Cold gains one contradiction, but cold is the weaker state to begin with and
  one clause does not offset the other.

So the prompt is reverted to the baseline order. The artifacts stay.

**A comparison that looked available and is not.** Diffing the two ledgers
claim-by-claim suggests 19 of A's 20 claims were "dropped". That reading is
wrong: the audit re-worded nearly every claim between conditions, so string
matching finds no counterpart for claims that are plainly the same assertion.
**Only the verdict counts compare reliably here.** Anything claim-level needs a
matching rule that survives rewording, and no such rule exists yet.

**What it suggests for the next attempt.** Both ledgers shrank — 11→9 cold and
20→16 warm. Leading with "if this is not a factual claim, stop" appears to make
the audit list *less*, not classify more finely, which runs against the
"Filter nothing out" instruction sitting above it. Whatever is tried next should
be phrased to protect listing, and ADR-024 §3's reserve option should not be
assumed to escape this.

## Comparing condition A with condition B

They were run under different protocols — A took five draws in an uncontrolled
state, B takes two per state — and that difference is **not** a reason to treat
them as incomparable. Within-state determinism collapses both to the same two
observations:

| | cold | warm |
|---|---|---|
| condition A | `baseline-a-d1.json` | `baseline-a-d2…d5.json` (identical) |
| condition B | `condition-b-cold-*.json` | `condition-b-warm-*.json` |

So compare cold against cold and warm against warm, one ledger each. The
differing N is an artefact of when each ran, not of what each measured.

## Condition A baseline, N=5 — the gate FAILS, and the variance has a shape

Run 2026-09-14 21:26–21:59 under the standard fixed earlier that day, on
`transcript-2026-09-14-gate.json`, `qwen3:8b`, budget 6000, five draws
sequentially. Artifacts `baseline-a-d1.json` … `d5.json`.

| draw | claims | supported | contradicted | not_checkable | hash |
|---|---|---|---|---|---|
| 1 | 11 | 10 | 0 | 0 | `455775e5835cd5ec` |
| 2 | 20 | 15 | **3** | 0 | `be6197db7ac41208` |
| 3 | 20 | 15 | **3** | 0 | `be6197db7ac41208` |
| 4 | 20 | 15 | **3** | 0 | `be6197db7ac41208` |
| 5 | 20 | 15 | **3** | 0 | `be6197db7ac41208` |

**Result: FAIL.** Clause (1) in 5/5, clause (2) in 4/5, **clause (3) in 0/5**.
No ledger carried all three. Per the standard there is no sixth draw. The three
contradictions in draws 2–5 are genuinely cross-side — side 1's claims against
side 0's `am-3` and `am-1` — so clause (2) is properly met, not a coincidence of
counts.

## Correction: the audit is deterministic, and "not reproducible" was wrong

**Fifteen runs now exist on this one transcript, and they have produced exactly
two outputs**, byte-identical within each group once `judged_at` is removed:

- `455775e5835cd5ec` — 11 claims, no contradictions. **3 runs.**
- `be6197db7ac41208` — 20 claims, 3 contradictions. **12 runs.**

There is no sampling spread. Ordering separates them perfectly:

| run | when | preceded by | hash |
|---|---|---|---|
| run 1 | 10:43 | `llama-server` loaded at 10:41 | A |
| runs 2–7 | 10:47–11:09 | each other, back to back | B ×6 |
| `rejudge-…-a` | 17:43 | ~13 min since the last `qwen3:8b` call | A |
| `rejudge-…-b` | 17:49 | run A, immediately | B |
| `baseline-a-d1` | 21:26 | ~3.5 h idle | A |
| `baseline-a-d2…d5` | 21:32–21:59 | each other, back to back | B ×4 |

Every first call after the model sat idle past Ollama's keep-alive gives A;
every call closely following another gives B. 3/3 and 12/12.

**So the withdrawal recorded above is itself withdrawn.** The earlier entry
said "the cold-server explanation is withdrawn … the variable cannot be load
state", on the grounds that `rejudge-b` was the fresh-load call. That rested on
reading a `ps` line — a `llama-server` started minutes earlier — as the
`qwen3:8b` runner. It carried `--mmproj`, so it was a vision model's runner, not
this one. The inference was wrong and the conclusion built on it was wrong.
ADR-017 §6's reproducible re-judging holds **within a load state**; it does not
survive one.

A plausible mechanism, not yet tested: a cold load has no prefix cache, so the
long prompt is prefilled in a different batching order and diverges in the
low bits. Ollama does report `prompt_tokens_details.cached_tokens`, and it was
observed going 0 → 25 between a cold and a warm call during the gemma4 probe.

**The prediction was made, then tested, and it holds.** Recorded in `cde093f`
before the run: stop the model, draw once (predict A), draw again immediately
(predict B). Run 2026-09-14 22:10–22:23, artifacts `statetest-cold.json` and
`statetest-warm.json` — **not gate draws, and not to be counted toward any N.**

| draw | `ollama ps` before | predicted | got | |
|---|---|---|---|---|
| cold | *(empty — model unloaded)* | `455775e5835cd5ec` | `455775e5835cd5ec` | **hit** |
| warm | `qwen3:8b, 11 GB, 100% GPU` | `be6197db7ac41208` | `be6197db7ac41208` | **hit** |

Both to the byte. Seventeen runs on this transcript now, still exactly two
outputs, and the state that selects between them is settled: **whether the model
was already resident when the call arrived.** Not sampling, not temperature, not
server warmth in any vaguer sense — Ollama's own `ps` was empty before the first
and populated before the second.

Practical consequences:

- **Judging is reproducible if, and only if, load state is held constant.** The
  useful rule for anyone re-running a comparison: touch the model first, or stop
  it first, but do the same thing every time.
- **A cold audit is the weaker one here** — it finds 11 claims and zero
  contradictions where the warm audit finds 20 and three. Whatever the mechanism
  costs, it costs recall.
- **`OPEN-QUESTIONS` 14 is answerable now.** A malformed reply reproduces within
  a state and does not survive a state change, so "re-run after stopping the
  model" is a repair that needs no code and no seed change. Whether that should
  be *automated* is still the open decision.

**It also compromises the N=5 protocol as written.** Five consecutive draws are
not five independent samples — they are one cold draw and four warm ones, and
the four warm ones are the same bytes. N=5 sampled two states, one of them four
times. Any future condition has to either control the state or say which state
it is measuring.

**The gate needs a run protocol, not another run.** Clause (3) cannot be
diagnosed from single draws when a single input yields 11 or 20 claims. Any
prompt change must be measured over N draws per condition, comparing verdict
*rates*, before anything is concluded from it.

**The protocol, decided 2026-09-14 before any run against it** (full text in
`BUILD-GUIDE.md` B6): **N = 5** draws per condition; the gate passes if **one
ledger of the five carries all three clauses at once**; **no sixth draw** — if
five do not produce it, that is a recorded failure, and re-running past N to
reach a pass voids the gate. All five ledgers are kept either way, with their
transcript. A pass says the configuration *can* produce all three, not that it
does reliably; the five ledgers are what any rate claim must cite.

Clauses (1) and (2) are near-certain to turn up somewhere in five draws at the
variance measured above, so in practice this gate binds on clause (3) — zero
`not_checkable` in every post-ADR-019 draw so far.

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
