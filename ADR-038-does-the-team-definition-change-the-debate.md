# ADR-038: Does the Team Definition Change the Debate?

**Status:** Accepted — **run 2026-09-19; results and the prediction scorecard in §Results**
**Date:** 2026-09-19
**Depends on:** ADR-006 (team files are identity, never run-time settings),
ADR-012/ADR-014 (retrieval by topic and side), ADR-035 (`phi4:14b` is the
standing judge), ADR-037 (a run now records the prompt it used),
OPEN-QUESTIONS 9 (model and stance are confounded; mirroring is mandatory)

## Context — the ladder was built for models, and personas were never tested

Every comparison this project has run varies the **model**. The team file — the
persona a side argues as — has been held fixed and never measured. It is four
fields (`name`, `stance`, `voice`, `values`) occupying roughly 200 characters of
a ~3,000-character prompt, and nothing establishes that it does anything at all.

That is worth knowing in both directions. If a rich persona and an empty one
produce the same evidence and the same verdicts, `teams/*.yaml` is decorative and
ADR-006's whole "durable identity" apparatus buys style, not substance. If it
moves results as much as a model size step does, then every model comparison run
so far held a large uncontrolled variable fixed by luck rather than by design.

**Why it is measurable now, and was not before.** `retrieve(topic, side, sources,
corpus)` does not take the persona, so every run of one motion hands a given side
the **same ten passages**. The persona enters only at the prep *synthesis* call
and the argument turns. So the retrieved set is a fixed control and any
divergence downstream is the team file and nothing else.

## The measure, chosen after checking it has resolution

The obvious judge-free measure — which evidence ids appear in the argument turns
— was tested against the six existing prep transcripts first and **is
degenerate**: ids appear 0 times in five of six, and 3 times in the sixth. Prep
rewrites passages into prose and the turns paraphrase.

One level upstream the same measure works. Counting ids inside the **prep notes**
across those six transcripts:

| | received | cited |
|---|---|---|
| `healthcare-0.6b-pro` pro | 10 | 3 |
| `healthcare-14b-pro` pro | 10 | 5 |
| `morality-0.6b-pro` pro | 10 | 6 |
| `medicaid-0.6b-pro` pro | 10 | **0** |

Every side is handed exactly ten and cites between none and six, and the subsets
differ by model — `healthcare` pro cites `{4715, 4723, 4728}` at 0.6b and a
superset including `{3094, 3110}` at 14b. So **which of its ten passages a side
picks up** is the primary measure: judge-free, already recorded in the
transcript, and demonstrated to discriminate before a single run was spent.

## Protocol

Held constant: motion (`Government should provide universal health care.`,
chosen because it retrieves 100% on-topic), **`qwen3:14b` on both sides** so
model and persona cannot trade, seed 42, phases
`[prep, opening:medium, rebuttal:medium, conclusion:short]`, the `args-me` pool.

Judge: **`phi4:14b`** with `--strict-json` (ADR-035). Deliberately not the
debaters' family — `qwen3:8b` judging `qwen3` debaters is the bias
`MODEL-COVERAGE` names, and it is also where every prompt-sensitivity finding in
this repo was collected.

Three runs, not four:

| run | pro | con |
|---|---|---|
| `full-advocate-pro` | Universal Coverage Advocate | Fiscal and Delivery Skeptic |
| `full-skeptic-pro` | Fiscal and Delivery Skeptic | Universal Coverage Advocate |
| `minimal` | Debater | Debater |

**The full condition is mirrored because a persona effect would otherwise be
indistinguishable from the side effect** — OPEN-QUESTIONS 9 measured `qwen3:0.6b`
swinging **+16 by side alone**.

**The minimal condition is not mirrored, because mirroring it is provably a
no-op.** `minimal-a` and `minimal-b` are byte-identical apart from `id`, which
never enters a prompt, and retrieval filters by `side` rather than by team. So
both orientations would issue identical requests. Running it twice would buy a
duplicate, not a control.

Those three runs still yield four persona-versus-floor cells, because each full
orientation exercises each persona on the opposite side: advocate-as-pro,
advocate-as-con, skeptic-as-pro, skeptic-as-con — each against the floor on the
same side, holding the ten passages identical.

## Predictions, recorded before the runs

ADR-030's value was that its prediction was written down and then falsified on
all three counts. The same discipline here.

1. **Evidence selection moves, but does not transform.** In **at least 3 of the
   4** cells, the prep-cited id set differs from the floor's by at least one id,
   with Jaccard overlap **≥ 0.4**. The persona should tilt which passages look
   worth using without overriding what was retrieved.
2. **Side beats persona.** The two full orientations will be won by the same
   **side**, not by the same **persona** — pro twice or con twice. A ~200
   character persona should not outweigh a position effect measured at +16.
3. **The ledger stays the same size**, within ±25% between full and minimal.

**What would falsify the premise entirely:** all four cells citing identical id
sets, with ledgers inside noise. Then the team file does not affect substance,
and ADR-006's durable-identity apparatus is a style feature that should be
described as one.

**The opposite surprise, and what it would mean:** the same *persona* winning
both orientations. That would make the team file a stronger lever than side
position, and would mean every model comparison in this repo silently held a
large variable fixed — worth more than the result itself.

## Consequences

- Artifacts land in the `debates` repository under `persona/`, which as of today
  is backed up (`box:Projects/debates.git`). ADR-037's recording means each
  transcript states its own prompt template and corpus digest, so these runs are
  the first in this project that can be compared later without trusting a
  filename.
- The field-by-field ablation (`voice` alone, `values` alone) is **deliberately
  not in this pass.** Full versus floor carries the whole question; if the floor
  debates identically, there is nothing left to ablate.


## Results, 2026-09-19 — generation 2 (`prep_budget: 6000`, `qwen3:14b-16k`)

Generation 1 was discarded: 4 of its 6 prep turns hit the token cap, so it
measured where the cap fell. See `debates/PREP-BUDGET.md`, which is the more
important output of this session. Everything below passed a truncation gate —
all six preps finished, 1338–2126 tokens of 6000.

ADR-037's recording earned itself here: **all three runs record the same prompt
fingerprint `ac1725e3ed914781` and the same corpus digest `93adf200b6751ecf`**,
so "only the team file differed" is verified rather than asserted.

### The prediction scorecard

| # | prediction | outcome |
|---|---|---|
| 1 | ≥3 of 4 cells differ in evidence selection, Jaccard ≥ 0.4 | **half.** 2 of 4 differed; where they did, Jaccard was 0.75 and 0.83 — above the floor, but the count was wrong |
| 2 | both full orientations won by the same **side**, not persona | **held.** pro won both, +6 and +9, with a different persona in the pro slot each time |
| 3 | ledger within ±25% between full and floor | **falsified.** 15 against 23 claims is −35%, and the *composition* moved far more than the count |

### 1. Evidence selection: nothing on pro, a little on con

Each side is handed the same ten passages (retrieval never sees the persona), so
this is judge-free and deterministic.

| | Universal Coverage Advocate | Fiscal Skeptic | blank `Debater` |
|---|---|---|---|
| as **pro** | 5 ids | 5 ids | 5 ids — **identical, Jaccard 1.00** |
| as **con** | 5 ids | 8 ids | 6 ids — Jaccard 0.83 / 0.75 |

**On the pro side three very different team files select the same five
passages.** On con the persona moves one or two of six to eight, and the
direction is coherent: the skeptic arguing con — aligned — takes up **two more**
than the blank; the advocate arguing con — arguing against its own stance —
takes up **one fewer**.

### 2. Scores: one persona is worth points, the other is worth nothing

| run | pro | con | gap | winner |
|---|---|---|---|---|
| advocate as pro | **89** | 83 | +6 | pro |
| skeptic as pro | **81** | 72 | +9 | pro |
| blank | 81 | 83 | −2 | con |

Read down the persona rather than across the run:

- **Universal Coverage Advocate: 89 arguing pro, 72 arguing con** — against the
  blank's 81 and 83. So roughly **+8 when aligned with its side and −11 when
  arguing against its own stance.**
- **Fiscal Skeptic: 81 as pro, 83 as con — the blank's scores exactly.** On
  totals this persona is indistinguishable from having none. (The *components*
  differ by 1–2 points, so the totals coinciding is a coincidence of sums, not
  the same debate: the three debate digests are `011b873f`, `471261b1`,
  `abf19db8`.)

### 3. The ledger moves far more than the score

| run | claims | supported | contradicted | not_checkable |
|---|---|---|---|---|
| advocate as pro | 15 | **1** | **9 (60%)** | 5 |
| skeptic as pro | 23 | 18 | 5 | **0** |
| blank | 23 | 14 | 3 | 5 |

Same motion, same model both sides, same judge, same passages. One team-file
swap takes `contradicted` from 13% to 60% of the ledger.

## How much of this to believe

**The evidence-selection result is solid.** It is judge-free, the received set is
a verified constant, the prep turns reproduce byte-for-byte across days and
directories, and the truncation control shows the clean cells were unchanged by
the budget fix.

**The score results are suggestive at best, and this project's own evidence says
so.** `MODEL-COVERAGE` records five judges on one transcript agreeing on the
winner while their margins ranged **+4 to +49**. A +6 or +9 gap sits inside that
spread. `phi4:14b` has no Tau-C, and it failed outright on 1 of 3 transcripts the
day before. The −2 in the blank run is not a con win; it is a tie a different
judge would break either way.

So the defensible statement is: **a team file changes what a side argues far more
than it changes whether the side wins — and on the pro side of this motion it
did not change what was argued from at all.**

## What this earns, and what it does not

- The field-by-field ablation (`voice` alone, `values` alone) is now worth
  running **only on the con side**, where there is an effect to attribute. On pro
  there is nothing to ablate.
- One motion, one judge, one seed, N=1 per cell. The asymmetry between pro and
  con may be a property of *this* motion's passages rather than of sides.
- The cheapest next test is the same three runs on a second motion. If pro is
  again persona-proof and con is not, that is a finding about sides. If it
  flips, it is a finding about corpora.


## Motion 2, predicted before the runs — 2026-09-19

Motion 1 left one question sharply posed: **is the pro side persona-proof because
of the side, or because of that motion's passages?** Three team files selected the
identical five ids there, Jaccard 1.00, while con moved by one or two.

The test holds the personas fixed and changes only the motion, to
**"The United States should adopt Medicaid for All."** — deliberately the
*weak-retrieval* one: **45% of its passages are on topic against 100%** for the
healthcare motion, because "united states" swamps "medicaid" and pulls in
marijuana and prison debates. Same teams, same models, same seed, same budgets,
same floor.

**Prediction.** If pro was persona-proof because its ten passages were strongly
on-point and effectively self-selecting, then a noisier set gives a persona room
to tilt, and **the pro cells should come back with Jaccard < 1.00**. If pro is
still persona-proof on a 45%-on-topic corpus, the insensitivity belongs to the
**side** and not to the passages.

I expect the first: **pro breaks, Jaccard between 0.5 and 0.9.** The mechanism I
am proposing is that a clean corpus decides for you and a noisy one does not.

**What would make me wrong in the more interesting way:** pro at Jaccard 1.00
again. That would mean something about arguing *for* a motion — rather than
about the evidence available — makes the persona inert, and would be a finding
about sides that nothing here predicts.

**A third outcome worth naming in advance:** both sides moving a lot. That would
say the effect is corpus *quality*, not side, and would put motion 1's clean
pro/con asymmetry down to the corpus being good rather than to the sides being
different.


## Motion 2 results — the effect is the corpus, not the side

Same personas, same models, same seed, same floor; only the motion changed, to
the **45%-on-topic** one. Gate passed: all six preps finished, 1598–2168 of 6000.
All three runs carry prompt fingerprint `ac1725e3ed914781` and corpus digest
`93adf200b6751ecf`, so only the team file differed.

### Evidence selection, both motions side by side

Jaccard against the blank floor, same side, same ten passages:

| | motion 1 — healthcare, **100% on-topic** | motion 2 — medicaid, **45% on-topic** |
|---|---|---|
| advocate as **pro** | **1.00** | **0.38** |
| skeptic as **pro** | **1.00** | **0.50** |
| skeptic as **con** | 0.75 | 0.50 |
| advocate as **con** | 0.83 | 0.75 |

**The pro side is not persona-proof. Its corpus was.** On a clean, on-topic
passage set three very different team files converge on the same five ids; on a
noisy one they diverge to 0.38 and 0.50. Motion 1's clean pro/con asymmetry was a
property of that motion's retrieval, not of arguing for versus against.

### Scores

| run | pro | con | gap | winner |
|---|---|---|---|---|
| advocate as pro | 88 | 87 | **+1** | pro |
| skeptic as pro | — | — | — | **judge failed** |
| blank | 68 | 85 | **−17** | con |

Removing the personas costs the pro side **17 points** here, against a swing of
roughly 8–11 on motion 1. The direction matches the evidence measure: where the
corpus does not decide for you, the persona does, and it shows up in the score.

### The prediction scorecard

**Predicted: pro breaks, Jaccard 0.5–0.9.** Pro broke — direction right, and the
proposed mechanism ("a clean corpus decides for you and a noisy one does not") is
supported. The **magnitude was outside the band**: 0.38 and 0.50 against a 0.5
floor. Both con cells also moved more than motion 1, which is the third outcome
§Motion 2 named in advance — *"both sides moving a lot would say the effect is
corpus quality, not side"* — and that is what happened.

Running total across this ADR: of six recorded predictions, **two held, two were
half right, two were falsified.**

### `phi4:14b` failed again, and it is deterministic

`m2-skeptic-pro` failed with `claims[3] is not_checkable but cites 1 passage(s)`
and **failed identically on a retry** — same claim index, same violation. So this
is not a sampling flake; the judge reproducibly cannot emit a valid ledger for
that transcript.

That is a **third distinct** `phi4:14b` failure mode, and the second that
constrained decoding cannot reach: a `not_checkable` verdict is defined to cite
nothing, and citing a passage contradicts it — a cross-field rule
`_evidence_citations` enforces and JSON Schema cannot. Its failure rate is now
**2 of 8 judgings attempted**.

## Where this leaves the question

**A team definition changes what a side argues from, and how much it matters
depends on the corpus.**

- With a clean, on-topic corpus the evidence largely selects itself and the
  persona is close to inert on the side whose passages are cleanest.
- With a noisy corpus the persona decides what gets used, moves half the cited
  set, and is worth on the order of 17 points of score.

**The practical reading**: persona is a lever you reach for when retrieval is
weak, and a rounding error when retrieval is strong. Improving the corpus and
writing a better persona are substitutes, not complements — and improving the
corpus is the one that also makes the result checkable.

Still N=1 per cell, one judge, two motions, and every score here comes from a
judge with no Tau-C that fails one transcript in four. The **evidence-selection**
half is solid; the **score** half is directionally consistent across two motions
and nothing stronger.
