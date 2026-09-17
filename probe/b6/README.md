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

## Condition C — the user turn's "factual claims", measured and REVERTED

Run 2026-09-15 09:37–09:53. One line changed from condition A: the user turn,
which said `Audit this debate's factual claims.` — pre-filtering, from the last
position the model reads, in direct contradiction of the system prompt's
"Filter nothing out" — became `Audit every assertion this debate makes.`
Nothing else moved; the verdict list is condition A's order.

| state | claims | supported | contradicted | unsupported | not_checkable | hash |
|---|---|---|---|---|---|---|
| cold | 14 | 9 | **3** | 2 | **0** | `2279df5a2d6761ee` |
| warm | **5** | 3 | 2 | 0 | **0** | `d57e1aa58493ddc6` |

Both same-state pairs byte-identical again; the protocol's self-test has now
passed under three different prompts.

**It fails, and the warm state collapses.** Cold improves markedly — 11 claims
to 14, and zero `contradicted` to three. Warm falls from **20 claims to 5**, an
audit that has stopped looking at most of the debate.

## The pattern across three conditions — prompt changes invert by state

| | A | B | C |
|---|---|---|---|
| cold claims | 11 | 9 | **14** |
| cold `contradicted` | 0 | 1 | **3** |
| warm claims | **20** | 16 | 5 |
| warm `contradicted` | **3** | 0 | 2 |
| `not_checkable`, either state | 0 | 0 | 0 |

**Both prompt edits helped cold and hurt warm.** That is now two independent
changes moving the two states in opposite directions, which makes prompt tuning
against this setup unreliable in a specific way: a variant judged on one state
will mislead about the other, and the warm state — every call after the first —
is the one users actually get.

**Clause (3) has never fired in 25 runs**, across three prompt variants and both
states. No `not_checkable` has ever been produced on this transcript by
`qwen3:8b`. Two readings remain and they have different next steps:

1. **The instruction is still wrong**, and prose is the wrong instrument. The
   structural version — a `factual` boolean in the claim schema, so the model
   answers the gating question in a field instead of holding it in its head — is
   ADR-024 §2 as schema rather than prose. It changes the claim shape, so it
   needs an ADR and a `schema_version` decision.
2. **This model will not produce the verdict**, whatever the prompt. Every one
   of the 25 runs is `qwen3:8b`. Judging the same transcript with a second model
   separates the two readings in four draws, and `gemma4:12b` is installed and
   measured (OPEN-QUESTIONS 13) — it needs a budget well above 6000, since it
   spends the first several thousand tokens thinking.

Reading 2 is cheaper and strictly diagnostic: it changes no code and can only
narrow the question. It should come first.

## The model ladder — clause (3) fires, and qwen3:8b is the outlier

Run 2026-09-15 17:10–17:31 on the gate transcript, fact-check on, every model
warmed with a trivial call first so the judge call happens **resident** (load
state changes the ledger, so it is held constant). A same-family ladder, so size
is the only variable that moves.

| judge | claims | supported | contradicted | `not_checkable` | clauses |
|---|---|---|---|---|---|
| `qwen3:0.6b` | 1 | 1 | 0 | 0 | — (degenerate) |
| `qwen3:1.7b` | 1 | 1 | 0 | 0 | — (degenerate) |
| **`qwen3:4b`** | 10 | 8 | 0 | **2** | (1) + **(3)** |
| `qwen3:8b` *(baseline)* | 20 | 15 | **3** | 0 | (1) + (2) |
| **`qwen3:14b`** | 12 | 8 | 0 | **4** | (1) + **(3)** |
| `deepseek-r1:32b-16k` | — | — | — | — | **failed to parse** |

**Clause (3) fires, and it fires on the exact claims `qwen3:8b` gets wrong.**
8b's two `unsupported` verdicts are "Rural renewable energy investment can offset
fossil fuel reliance" and "The CON's focus on leakage overlooks climate urgency"
— the value judgement this page has been citing for two days. `qwen3:4b` calls
both `not_checkable`. `qwen3:14b` calls the second one `not_checkable` too,
along with three more value judgements.

**So the prompt is not broken.** Three conditions of prompt-tuning (B and C, both
reverted) were chasing a defect that was never in the wording. The same prompt
produces the verdict on a smaller model and a larger one, and not on the one
model every single previous B6 run used.

**And it is not a size threshold.** 4b does it, 8b does not, 14b does. That is
non-monotonic, which rules out "the model is too small to tell an opinion from a
fact" — 4b manages it. Something about `qwen3:8b` specifically resolves these
claims to `unsupported`.

**The gate is still not met, and the reason has inverted.** No single ledger
carries all three clauses — but the obstacle is no longer clause (3). 4b and 14b
produce **zero `contradicted`**, so they lose clause (2), which 8b produces
reliably in every warm run. Each model gets a different pair:

- `qwen3:8b` → (1) + (2), never (3)
- `qwen3:4b`, `qwen3:14b` → (1) + (3), never (2)

The gate asks for one ledger with all three. Nothing tested does both halves.

**Two things worth noting about the runs themselves.** `qwen3:0.6b` and
`qwen3:1.7b` returned a single claim each — they cannot perform this task at all,
which is the first measurement of the floor. And `qwen3:4b` was loaded by Ollama
at a **262,144-token context**, reported 43 GB resident with a 41%/59% CPU split,
and still completed — the same context-inflation that killed `deepseek-r1:32b` at
128K, survived here only because the weights are small.

`deepseek-r1:32b-16k` failed validation on a truncated verdict — `'upported'`
where `supported` was meant — after about eight minutes. That is the malformed
class ADR-026 declines to retry around, on the slowest model available.

## qwen3:14b under the full protocol — clause (3) is stable, clause (2) never appears

Four draws, two per load state, 2026-09-15 17:41–17:58.

| state | draws | claims | supported | contradicted | `not_checkable` | hash |
|---|---|---|---|---|---|---|
| cold | 2 | 12 | 8 | **0** | **4** | `d72f8775e05bb83b` |
| warm | 2 | 13 | 9 | **0** | **4** | `1be4a3d66d141d09` |

Same-state pairs byte-identical — the protocol's self-test passes a fourth time,
now on a fourth model. **Four `not_checkable` in every draw, in both states, and
zero `contradicted` in every draw.**

So 14b is *stable* where 8b is not. On `qwen3:8b` the load state decides whether
clause (2) appears at all — warm finds three contradictions, cold finds none. On
`qwen3:14b` the state barely moves the ledger (12 claims against 13) and moves
neither clause.

**The two models are complementary and neither is sufficient:**

| | (1) supported | (2) contradicted | (3) not_checkable |
|---|---|---|---|
| `qwen3:8b` warm | ✅ | ✅ 3 | ❌ 0 |
| `qwen3:8b` cold | ✅ | ❌ 0 | ❌ 0 |
| `qwen3:4b` | ✅ | ❌ 0 | ✅ 2 |
| `qwen3:14b` both states | ✅ | ❌ 0 | ✅ 4 |

B6 asks for all three in one ledger. **Every model tested gets exactly two, and
which two depends on the model rather than on the prompt.** Three prompt
conditions were reverted chasing a defect that moves with the judge.

## Generation is a bigger lever than size — qwen3:4b against qwen3.5:4b

Same parameter count, same prompt, same transcript, same load state. Only the
model generation differs.

| judge | budget | claims | supported | contradicted | `not_checkable` | clauses |
|---|---|---|---|---|---|---|
| `qwen3:4b` | 6,000 | 10 | 8 | **0** | **2** | (1) + (3) |
| `qwen3.5:4b` | 32,000 | 14 | 9 | **4** | **0** | (1) + **(2)** |

**They get opposite pairs.** One generation finds the opinions and no
contradictions; the next finds four cross-side contradictions — all verified
cross-side, side 0's claims against `am-4` and side 1's against `am-3` — and no
opinions. At the same size.

**The budgets differ because they had to.** `qwen3.5:4b` failed at 6,000 with
**23,149 characters of thinking and no answer at all**. At identical parameter
counts the newer generation needed roughly five times the budget to answer the
same prompt. That asymmetry is recorded rather than normalised away: it is
OPEN-QUESTIONS 13 (budget counts thinking) landing on the newest generation, and
it means a budget tuned for one generation silently starves the next.

## Clause (2)'s evidence does not show what clause (2) asks for

2026-09-16, investigating why `qwen3:14b` finds no contradictions. It ended by
questioning `qwen3:8b`'s.

**First, two clean negatives on 14b.** Both baselines reproduce byte-for-byte a
day later (cold 12 claims `d39899c15418cd71`, warm 13 `62f09bc321324861`). And
**budget is inert**: warm at 16,000 is byte-identical to warm at 6,000, same
hash. 14b is not being squeezed for thinking room, so OPEN-QUESTIONS 13 is not
the cause — a contrast with `qwen3:32b`, where changing the budget demonstrably
changed the reply.

**Then the passages themselves.** Each of 8b warm's three contradictions, put to
four models as a single pair with no debate framing and no audit context
(`contradiction-spread.json`):

| pair | 4b | 8b | 14b | 3.5:4b |
|---|---|---|---|---|
| 1. "regressive before any rebate arrives" vs `am-3` | NO | **NO** | NO | NO |
| 2. "Brindlewick's success is exceptional and not scalable" vs `am-1` | NO | **NO** | NO | NO |
| 3. "carbon taxes create regressive burdens" vs `am-3` | NO | NO | YES | YES |

**`qwen3:8b` rejects, in isolation, two of the three contradictions it reports
inside the audit.** On pair 1 the text is on its side: `am-3` reads "turns **a
regressive tax** into a progressive transfer", which presupposes the very
regressivity the claim asserts. On pair 2, `am-1` reports that Brindlewick
succeeded and says nothing about scalability.

**It is not ADR-019's emphasis block** (`contradiction-winsblock.json`). Prepending
`CONTRADICTION WINS` verbatim flips nothing — six of six stay NO, several quoting
the block's own "a passage that agrees does not contradict" back.

### What actually produces them: the record includes the opponent's turns

ADR-015 §2 defines the record as "the passages each side retrieved, **and what
either side said**". The probe above supplied only a passage, so it asked a
narrower question than the audit does. Adding the opposing side's **turn text**
(`contradiction-turntext.json`):

| pair | model | passage only | passage + opponent's turns |
|---|---|---|---|
| 2. Brindlewick | `qwen3:8b` | NO | **YES** |
| 2. Brindlewick | `qwen3:14b` | NO | **YES** |
| 1. regressive | `qwen3:14b` | NO | **YES** |
| 1. regressive | `qwen3:8b` | NO | NO |

Three of four flip, and the reasons name the mechanism outright — 8b: "the record
**argues** that Brindlewick's success demonstrates the potential of a carbon tax…
directly contradicting the assertion". That is the opponent's *argument*, not a
retrieved passage.

### The structural gap this exposes

A turn-driven contradiction still has to be cited, because `_evidence_citations`
refuses `contradicted` with no ids. So the model borrows a topically-related
**passage** id for a contradiction that came from a **turn**, and nothing checks
that the cited passage is what did the contradicting. The code comment on that
function says a citation that cannot be checked is "exactly what this pass exists
to avoid"; this is that, arriving through a door the validator does not watch.

**So the verdicts are not obviously wrong under ADR-015 §2** — the record does
include turns, and the opponent's turns do oppose these claims. What is wrong is
the **citation**, and therefore the gate. B6 clause (2) asks for "a side asserts
something that the *opponent's recorded evidence* contradicts — verdict
`contradicted`, **pointing at the opponent's passage**". Two of the three
verdicts point at a passage that four models, including the one that produced the
verdict, agree does not contradict the claim.

**Clause (2) has been recorded as "met and reproducible" since 2026-09-14 on this
evidence.** That status is now in question — not because the model misbehaved,
but because "the record" means one thing in ADR-015 §2 and a narrower thing in
the gate, and nothing reconciles them. That is a decision to be made, not a bug to
fix, and it is logged as OPEN-QUESTIONS 16.

### The citation requirement is not what suppresses 14b — hypothesis falsified

A hypothesis worth stating because it was good and it is wrong. 14b cites the
*backing* passage and says `supported` on both halves of the pair. ADR-019 §2
requires a `contradicted` verdict to cite the **contradicting passage**, and for
a turn-driven contradiction none exists. So perhaps 14b sees the contradiction,
finds no legal citation, and falls back to `supported` — while 8b, looser,
borrows a topically-related id. That would have explained both models at once,
and it would have justified an ADR making turns citable.

Tested directly (`citation-cost.json`): same framing as the turn-text probe, plus
the audit's own constraint — "if contradicted you MUST cite the id of the passage
that contradicts it".

| pair | model | no citation asked | citation required |
|---|---|---|---|
| 2. Brindlewick | `qwen3:14b` | YES | **`contradicted`, cites `ds-2`** |
| 2. Brindlewick | `qwen3:8b` | YES | `contradicted`, cites `am-1` |
| 1. regressive | `qwen3:14b` | YES | `supported` |
| 1. regressive | `qwen3:8b` | NO | `supported` |

**14b is not suppressed.** Forced to cite, it names a passage as readily as 8b —
and names a *different* one, `ds-2`, while its own reason says "the **rebuttal**
explicitly argues…". It is citing a passage for a contradiction it located in a
turn, which is the borrowed-citation problem again and confirms it is general
rather than 8b-specific.

So **making turns citable would not make 14b report contradictions**, and the ADR
that hypothesis would have justified is not worth writing. OPEN-QUESTIONS 16's
option 2 remains defensible on citation-honesty grounds; it is now known not to
be a route to the gate.

Three explanations for 14b's zero have now been ruled out cheaply — budget
(byte-identically inert), passage adjacency, and citation strictness. What
remains is something about producing a full ledger in the audit context, and that
has not been tested.

**What this does not establish.** A single pair in isolation is an easier task
than producing a 20-claim ledger, and the two prompts are not the same prompt.
Every cell here is one draw with load state uncontrolled across the probe, and the
flip test is four cells. Pair 3 splits 2-2 and may well be a legitimate
contradiction. None of this shows 14b is *right* to return zero — only that the
reason it was called wrong does not hold up.

## ADR-032: constrained decoding, and two families that produce all three clauses

2026-09-17. Not a prompt change — a *grammar* change. The judge sends a JSON
schema with the request and Ollama constrains decoding to it, so an off-enum
verdict or a malformed object is unemittable rather than refused after the fact.

Measured under ADR-026 §3's pre-registered shape, three judges x three
transcripts both ways: **parse failures 5 of 9 → 0 of 9, and the ledgers grew
rather than thinned** (15→16, 11→12, 9→12, 17→36). The trade that killed
conditions B, C and ADR-030 — winning a metric by writing less — did not happen.

**All four verdicts in one ledger:**

| judge | unconstrained | constrained |
|---|---|---|
| `phi4:14b` | 0 of 1 | **3 of 3** |
| `mistral-nemo:12b` | 0 of 0 | **2 of 3** |
| `qwen3:8b` | 0 of 3 | **0 of 3** |

So B6's three clauses *do* appear together, reliably, on two families — the thing
this page recorded as never having happened. And **`qwen3:8b` still never emits
`not_checkable` even when the grammar permits nothing else to be wrong**, which
is the fourth independent channel agreeing that clause (3) is a property of that
judge. Verdict-list order, user-turn framing, a required `factual` field, and now
constrained decoding: four channels, four failures, one conclusion.

**This does not make the verdicts right.** The isolation test above was run on
`phi4:14b`'s cross-side contradictions and returned one confirmed by four models,
one contested, one false positive. `phi4:14b` also marks more than half its
claims `not_checkable` (24 of 44, 24 of 36) — plausibly a distortion mirroring
`qwen3:8b`'s zero rather than a correction of it.

**What it means for ADR-031.** That ADR closed B6 on "no judge tested produces
all three clauses", and named a judge that does, with citations surviving
isolation, as the reopening condition. Half of that is now met and half is not.
The gate stays closed; the finding belongs here and in `MODEL-COVERAGE.md`.

## ADR-030: the schema attempt, and the third failure through a third channel

`ADR-024 §2 as schema` — the option this page named as the one left — was built
and measured on 2026-09-16. Every claim carried a required `factual` boolean
before its verdict; `not_checkable` was removed from the verdict list and derived
from `factual: false`. Four draws, two per load state, `qwen3:8b`, budget 6000,
same transcript. Artifacts: `adr030-{cold,warm}-{1,2}.json`.

| draw | claims | supported | contradicted | unsupported | `not_checkable` | hash |
|---|---|---|---|---|---|---|
| cold ×2 | 16 | 13 | **0** | 3 | **0** | `873a3c47aeee8f64` |
| warm ×2 | 16 | 13 | **0** | 3 | **0** | `873a3c47aeee8f64` |
| baseline warm | 20 | 15 | **3** | 2 | 0 | `36859fa6f7798c1c` |

**Reverted.** Zero `not_checkable`, all three cross-side contradictions lost, and
the ledger down from 20 claims to 16 — the prediction ADR-030 §7 recorded in
advance was wrong on all three counts.

**The interesting part is what happened to the two target assertions.** The value
judgement, "the CON's focus on leakage overlooks climate urgency", was not
reclassified — it **vanished from the ledger**. The prediction, "can offset
fossil fuel reliance", stayed `unsupported`. Of the three lost contradictions,
one became `supported` **citing the speaker's own passage** and two dropped out
entirely.

So being made to answer "is this factual?" for every assertion was read as
licence to drop the ones that are not, two lines under a prompt that says
"Filter nothing out".

### Three channels, three identical failures

| condition | channel | `not_checkable` | claims | cross-side `contradicted` |
|---|---|---|---|---|
| baseline (A) | — | 0 | 20 | 3 |
| B | verdict-list order | 0 | fewer | **0** |
| C | user-turn framing | 0 | **5** | — |
| ADR-030 | required schema field | 0 | **16** | **0** |

**On `qwen3:8b`, every change that foregrounds the checkability question trades
away clause (2) and shrinks the ledger.** Three independent channels — what the
model reads, how the task is framed, and what the reply must structurally
contain — produce the same outcome. The schema channel was the strongest one
available, and ADR-030 argued explicitly that removing the competition between
`unsupported` and `not_checkable` should differ from reordering it. It did not.

**Clause (3) is not reachable on `qwen3:8b` by changing what we ask for.**
`qwen3:4b` and `qwen3:14b` produce it unprompted on this same transcript. The
variable is the judge — which is what this page concluded before ADR-030 was
written, and what ADR-030 failed to overturn.

### A real side effect: the load-state sensitivity disappeared

`qwen3:8b` is the model this project's determinism note rests on: cold 11 claims,
warm 20, decided by residency. Under ADR-030 **all four draws were byte-identical
across the cold/warm boundary** — 16 claims either way, one hash.

**Checked as a paired comparison**, because the first version of this claim
compared today's runs against a two-day-old baseline under a different prompt,
which confounds the schema change with anything that drifted in between. A cold
draw on the **reverted** prompt, run the same day:

| prompt | state | claims | hash |
|---|---|---|---|
| unchanged, 2026-09-14 | cold | 11 | `2fddcc93b6f8afc0` |
| **unchanged, 2026-09-16 (control)** | cold | 11 | `2fddcc93b6f8afc0` |
| unchanged, 2026-09-14 | warm | 20 | `36859fa6f7798c1c` |
| ADR-030 | cold *and* warm | 16 | `873a3c47aeee8f64` |

The control is byte-identical to the 2026-09-14 cold draw. Nothing drifted, the
split is still there on the unchanged prompt, and the reply schema is what
removed it. It also means **the audit reproduces to the byte across two days**,
which is a stronger determinism result than this page previously recorded.

### Where this leaves the gate

The most promising route left is **not** another prompt or schema change to 8b.
It is `qwen3:14b`, which already produces clause (3) stably in both states and
needs only clause (2) — and whose failure is now characterised: it lists both
halves of the `am-3`/`am-4` contradiction pair, cites both correctly, and marks
each `supported`. Its citation mechanics are exact; it never weighs a claim
against the *opposing* side's passage. That is an ADR-019 precedence failure on a
model ADR-019 was never measured on, and it has not been investigated.

## The full clause table, every judge tested

| judge | (1) supported | (2) contradicted | (3) `not_checkable` |
|---|---|---|---|
| `qwen3:0.6b` | degenerate — 1 claim | — | — |
| `qwen3:1.7b` | degenerate — 1 claim | — | — |
| `qwen3:4b` | ✅ | ❌ | ✅ 2 |
| `qwen3.5:4b` | ✅ | ✅ 4 | ❌ |
| `qwen3:8b` warm | ✅ | ✅ 3 | ❌ |
| `qwen3:8b` cold | ✅ | ❌ | ❌ |
| `qwen3:14b` both states | ✅ | ❌ | ✅ 4 |
| `qwen3:32b-16k` | **unparseable, twice** | — | — |
| `gemma4:12b` | not run on this transcript | — | — |

**Nothing has produced all three.** Seven judges across two generations and five
sizes, and every one that works at all returns exactly two clauses. The gate asks
for three in one ledger.

## qwen3:32b — four attempts, four unparseable replies, and a new lever found

| attempt | state | budget | fault |
|---|---|---|---|
| 1 | warm | 6,000 | `char 1038` |
| 2 | cold | 6,000 | `char 1038` — **identical** |
| 3 | cold | 6,000 | `char 1038` — **identical** |
| 4 | cold | **12,000** | `char 3699` — **different** |

**Verdict: `qwen3:32b-16k` cannot produce this format on this input.** It fits
(24 GB, 100% GPU), it runs, and four attempts produced no ledger. That is the
large rung's result.

The two faults are different defects, and both are recognisable:

- at `char 1038` — `"justification": "Hit_ledger": [` — it opened a
  justification string and emitted a *key* inside it, conflating two fields;
- at `char 3699` — `…dense with technical terms (e.g., "carbon leakage")…` —
  **unescaped inner quotes**, the same family as the doubled-quote defect
  OPEN-QUESTIONS 14 was originally written about.

**The new lever: changing `--budget` changes the reply.** Attempts 1–3 were
byte-identical failures across both load states; attempt 4 differed only in
budget and produced a different reply that got **3.6× further** before breaking.
So the request body is a lever on the output, independent of the seed and of
model residency.

That matters beyond this model. OPEN-QUESTIONS 14's option 2 was "re-ask with a
different seed", and ADR-017 §6 forbids the tool changing the seed. **Changing
the budget is a different mechanism with the same effect and no ADR against it** —
though it would change what the budget *means*, so it is not free either.

It also disproves a sentence in the error message written earlier today, which
claimed "nothing else needs changing — not the seed, not the budget". The budget
does change it. The message is corrected.

## ADR-026's repair advice failed on a model it was not measured on

`qwen3:32b-16k` returned malformed JSON — `Expecting ',' delimiter: line 19
column 38 (char 1038)`. The error told the operator what ADR-026 §2 says: stop
the model and judge again, because the reply is deterministic only while the
model stays loaded.

**It was tried, and it failed identically.** The first run was warm; the retry
stopped the model, slept, and ran cold. Both produced the same fault at the same
character offset, `char 1038`.

So the load-state repair is **model-dependent, not general**. It was measured on
`qwen3:8b`, where cold and warm give byte-different replies. `qwen3:14b` is
nearly state-insensitive (12 claims cold, 13 warm, identical clauses) and
`qwen3:32b` appears fully state-insensitive on this input. ADR-026 §2's wording
is corrected accordingly — the advice is worth giving, and it is not a guarantee.

## The second-model diagnostic has not run — four draws, four timeouts

Attempted 2026-09-15 10:09–11:15. `gemma4:12b` against the gate transcript at
`--budget 20000`, baseline prompt, four draws across both load states. **All
four failed with `ReadTimeout` and no artifact was written.** About 66 minutes
of machine time for one finding, which was not the one being sought: the read
timeout was hardcoded at 600 seconds and a 12B reasoning model at that budget
does not finish inside it. That is now a setting (ADR-025), found by the run it
blocked.

The question it was meant to answer is **still open**: clause (3) has never
fired in 25 runs, all `qwen3:8b`, and nothing yet separates "the instruction is
still wrong" from "this model will not produce this verdict". A rerun needs
`--timeout` well above the default and should be costed honestly first — one
successful draw answers the question, so a single warm draw is the right shape,
not four.

**A process note, because it cost more than the run did.** Two further jobs were
chained behind this one by polling for its final artifact. That file was never
written, so both waited indefinitely and had to be killed. **Never gate a queued
job on a file a failed job would not produce.** Sequence the work in one script,
or poll for something that exists either way.

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
