# Judge Validation — method, data, and the decisions it still needs

**Status:** **complete 2026-09-14, full 631 speeches.** `qwen3:8b` clears the
threshold on *ordering* and fails on *calibration*. This is OPEN-QUESTIONS item
6, which blocks B7 and blocks trusting any score from B5 onward.

## Result — full dataset, 631 speeches, `qwen3:8b` via Ollama

**631/631 scored. Zero parse failures, zero errors.** 3 h 27 m.

| aggregator | Tau-C | human ceiling | |
|---|---|---|---|
| raw mean | **+0.547** | 0.405 | 135% of ceiling — **CREDIBLE** |
| rounded mean | **+0.401** | 0.316 | 127% of ceiling |

Both clear the ≥0.38 threshold fixed before any judge ran.

**The subset corroborates rather than being revised.** It gave +0.513 / +0.376
on 117 speeches; the full set gives +0.547 / +0.401. A material disagreement
would have been grounds to distrust one of the two runs, not to prefer the
better number.

**Calibration is where it fails, and at full n the split is sharper than the
subset showed.** Mean judge 2.85 against human 3.61, a −0.76 bias that lands
almost entirely on machine-generated speeches:

| source | n | judge | human | diff |
|---|---|---|---|---|
| Arg-Human1 | 23 | 3.78 | 3.79 | **−0.01** |
| Human expert | 152 | 4.10 | 4.19 | **−0.10** |
| Arg-Human2 | 76 | 3.49 | 3.67 | **−0.18** |
| Arg-Search | 76 | 2.17 | 3.12 | −0.95 |
| Project Debater | 76 | 3.05 | 4.03 | −0.98 |
| Summit | 76 | 1.93 | 2.96 | −1.03 |
| Arg-GPT2 | 76 | 1.95 | 3.40 | −1.46 |
| Speech-GPT2 | 76 | 1.70 | 3.22 | −1.52 |

**All three human-authored sources fall within 0.18 of human ratings; every
machine-generated source is 0.95 to 1.52 low.** The judge agrees with humans
about human writing and is far harsher than humans about machine writing.

This also vindicates marking the subset's `Arg-Human1` cell unquotable: at n=4
it read **+0.35**, and at n=23 it is **−0.01**. The direction flipped, and had
it been quoted it would have muddied the very split the full run makes clean.

**Tau-C measures ordering only, so it is blind to all of the above.** It rewards
exactly what this judge does well.

### What this licenses, and what it does not

- **Supported:** comparing two sides' scores against each other, which is what
  ADR-013 §3 does to pick a winner. Rank is what was validated.
- **Not supported:** reading an absolute `argument_quality` number as a quality
  measure, or comparing scores across debates — the bias depends on what is
  being judged.
- **Untouched:** the winner logic itself, the steelman tiebreak, the coin-toss
  tiebreak added by ADR-023, `rebuttal_effectiveness`, and the fact-check pass.
  B7's README must say so rather than claim "the judge was validated".

**A caveat that matters for this tool specifically.** `debatebench` judges
*machine-generated* debate turns, and machine-generated speech is precisely
where this judge is least calibrated. Ordering still holds, which is what the
winner depends on — but nobody should read a 17/30 from it as "this argument was
mediocre".

### Corroborated on a real debate, 2026-09-14

B7's gate runs put this judge on a `debatebench` transcript rather than on the
paper's dataset, and the calibration finding reproduced immediately — in the
direction the table above predicts, but more starkly than a −0.76 mean bias
suggests.

**A prep-less debate scored the PRO 100/100.** Every dimension at its maximum,
including `evidence_grounding: 25/25` on a transcript containing **zero
recorded evidence**, justified by calling "the EU's cap-and-trade and Canada's
tax" well-anchored — neither of which appears anywhere in the transcript.

That is not a bug, and an earlier reading of it here as one was wrong.
ADR-013 §4 defines exactly this weak mode: with no prep, the judge scores
"general argumentative rigor from its own knowledge, with nothing recorded to
check against — a materially weaker guarantee, visibly labeled as such". The
`prep_grounded: false` sitting in the same object is that label doing its job.

What it *is* is the clearest available picture of the bias: on machine-generated
turns this judge does not merely mis-scale, it **saturates**. The prep-enabled
run scored 97 against 95 — both sides near-perfect, the winner turning on a
2-point margin. Ordering did the work the validation supports; the absolute
numbers carried no information at all.

**This is the concrete case behind the README's warning.** Nobody should read
`evidence_grounding: 25/25` as "well-evidenced" on a transcript with no
evidence in it.

## Corroborating run — stratified subset, 117 speeches

117/117 scored, **zero parse failures, zero errors**, 36.5 minutes.

| aggregator | Tau-C | human ceiling | verdict |
|---|---|---|---|
| raw mean | **+0.513** | 0.405 | 127% of ceiling — **CREDIBLE** |
| rounded mean | **+0.376** | 0.316 | 119% of ceiling |

Both clear the ≥0.38 credible threshold, which was fixed before any judge ran.

**But the ordering is the only thing that passes.** Mean judge score 2.85 against
human 3.64 — a −0.78 bias that is *not* uniform, and the per-source breakdown is
the real finding:

| source | n | judge | human | diff |
|---|---|---|---|---|
| Human expert | 29 | 4.07 | 4.13 | **−0.06** |
| Arg-Human2 | 14 | 3.79 | 3.73 | +0.05 |
| Arg-Human1 | 4 | 4.25 | 3.90 | +0.35 *(n=4, too thin to read)* |
| Project Debater | 14 | 3.21 | 4.09 | −0.87 |
| Arg-Search | 14 | 1.86 | 3.07 | −1.21 |
| Summit | 14 | 1.71 | 2.93 | −1.22 |
| Arg-GPT2 | 14 | 2.07 | 3.40 | −1.32 |
| Speech-GPT2 | 14 | 1.57 | 3.51 | **−1.94** |

It judges human-written speeches almost exactly as humans do, and marks
machine-generated ones one to two full points below. **Tau-C measures ordering
only, so it rewards precisely what this judge does well and is blind to what it
does badly.** Anyone reading a raw 0–30 `argument_quality` score from this judge
would be badly misled; anyone comparing two sides' scores against each other
would not. That distinction matters for `debatebench`, where ADR-013 §3 decides
the winner by *comparing* totals — the use the evidence supports.

**This also resolves the discrepancy flagged below.** A judge scoring 0.513
against a 0.405 human ceiling is not a contradiction: it correlates against the
mean of 15 raters, which is far less noisy than any single annotator, so beating
the average individual human is expected rather than suspicious. The paper's
"≥7B clusters above 0.5" and this ceiling are consistent. That note is left in
place below for the record, with this correction attached.

ADR-002 says the IBM datasets come "before trusting any judge model choice", and
tells us to read *Debatable Intelligence: Benchmarking LLM Judges via Debate
Speech Evaluation* (Sternlicht, Gera, Bar-Haim, Hope, Slonim — EMNLP 2025,
[arXiv 2506.05062](https://arxiv.org/abs/2506.05062),
[code](https://github.com/noy-sternlicht/Debatable-Intelligence)) before
designing our own pass. Read 2026-09-13; this file records what it settles.

---

## The data, verified rather than assumed

`noystl/speech-quality-dataset` — the authors' **own filtered set**, published as
a single `data.csv`. Use it rather than re-deriving from
`ibm-research/debate_speeches` (948 rows), which would risk filtering
differently than they did.

Cached out-of-band at `~/.cache/debatebench/validation/speech-quality-dataset.csv`,
per ADR-012 §5's posture: acquisition is a manual step, a *run* pulls nothing.

Verified locally:

| | |
|---|---|
| speeches | **631** (paper: 631) |
| topics | **76** (paper: 76) |
| labelers per speech | **exactly 15** — ADR-002 previously said 5–30 |
| individual ratings | 9,465, scale 1–5, **per-annotator, not pre-averaged** |
| mean length | 605.6 words |

Columns: `id, topic_id, topic, source, text, goodopeningspeech, #labelers,
labeler_ids`. `goodopeningspeech` holds the *list* of 15 ratings, which is why
both of the paper's routes are open to us rather than only the aggregate one.

Mean score by source — the gradient a judge has to reproduce:

| source | n | mean |
|---|---|---|
| Human expert | 152 | 4.19 |
| Project Debater | 76 | 4.03 |
| Arg-Human1 | 23 | 3.79 |
| Arg-Human2 | 76 | 3.67 |
| Arg-GPT2 | 76 | 3.40 |
| Speech-GPT2 | 76 | 3.22 |
| Arg-Search | 76 | 3.12 |
| Summit | 76 | 2.96 |

---

## The method, pinned to their implementation

**Primary statistic — Kendall's Tau-C** against the mean human score, per speech,
across all 631. Their code is `scipy.stats.kendalltau(a, b, variant='c')`, with
no rescaling of the judge's score and no row filtering; predictions are matched
to annotations by `id`. Reproducible with scipy alone — we need none of their
code.

**One asymmetry to handle honestly.** Their repo contains two aggregators:
`aggregate_human_annotations_avg` (used on the Tau-C path) and
`aggregate_human_annotations_rounded_avg`, which rounds the mean to an integer.
Rounding 15 ratings into 5 buckets changes the tie structure, and tau-**c** is
specifically the variant that is sensitive to ties and unequal category counts.
**Compute both and report the pair**, rather than picking one and implying a
precision we don't have.

**Secondary statistic — weighted Kappa**, leave-one-out: substitute the judge for
one human and measure pairwise agreement, over annotator pairs sharing ≥50
speeches. The paper notes the shared-speech counts stay small even then, "which
could introduce noise". Secondary for a first pass.

**Their judge prompt**, verbatim, is a *single* 1–5 Likert item:

> Your task is to indicate to what extent you agree or disagree with the
> statement: "This speech is a good opening speech for supporting the topic."
> … 1 = Strongly disagree … 5 = Strongly agree. Provide your score in the
> following format: `<score>[Insert a single number between 1 and 5]</score>`

**There is no score-parsing code in their repo.** Extracting `<score>N</score>`,
and deciding what happens when it is absent or malformed, is ours to write — and
on this project's evidence that is the part most likely to fail: four distinct
malformed-reply modes were measured across four backends on 2026-09-12/13.

**Their headline results**: judges under 7B underperform; models ≥7B cluster
above roughly 0.5 Tau-C; the best (Qwen-72B) matches or exceeds human pairwise
agreement. No acceptance threshold is stated anywhere — human pairwise Kappa is
the implicit baseline. Even strong judges assign systematically lower scores
than humans, and all five judges rated GPT-4.1's speeches above human experts'.

---

## What this validates, and what it does not

This measures **whether a candidate judge model's quality judgement tracks human
judgement**. That is what ADR-002 asks for and what item 6 blocks on.

It does **not** validate:

- **four of our five dimensions.** Their annotators gave one blended 1–5 score
  explicitly conflating "relevance, style, factuality, and argument strength".
  Ours scores five dimensions separately, and ADR-013's central rule is that
  they are never blended. At best this speaks to `argument_quality`.
- **the winner logic** (ADR-013 §3), the steelman tiebreak, or the draw path.
- **`rebuttal_effectiveness` or the hit-ledger**, which need a two-sided
  transcript; these are single opening speeches.
- **the fact-check pass** (ADR-015) at all.

Anything left unvalidated should be said so in B7's README, not implied to be
covered because "the judge was validated".

**A likely-uncomfortable result worth expecting.** Our candidate judge is
Qwen3-8B, which sits just above the paper's ≥7B line. A plausible outcome is
"marginal" — and finding that out before B7 is the entire point.

---

## The human ceiling, measured from this data

Tau-C runs **−1 to +1**: +1 perfect ordering agreement, 0 none, −1 inverted.
But 1.0 is not the target. On a subjective task the 15 annotators do not agree
with each other either, so **human-to-human agreement is the ceiling**, and it
is computable here rather than borrowed — every individual rating is in the
file.

Procedure, identical to what a judge would face: leave one annotator out,
correlate their ratings against the mean of the other 14 on the speeches they
rated, Tau-C, averaged over annotators. 82 annotators; median 116 speeches each
(range 2–239).

| minimum speeches | aggregator | n | mean | median | min | max |
|---|---|---|---|---|---|---|
| ≥30 | raw mean | 64 | **0.405** | 0.404 | 0.116 | 0.840 |
| ≥30 | rounded mean | 64 | 0.316 | 0.301 | 0.070 | 0.590 |
| ≥50 | raw mean | 56 | **0.382** | 0.382 | 0.116 | 0.675 |
| ≥50 | rounded mean | 56 | 0.295 | 0.297 | 0.070 | 0.522 |

Two things follow, and both matter more than the headline number.

**The rounding choice moves the ceiling by ~0.09** — a quarter of the way to the
human ceiling itself. It is not a presentational detail, and any threshold has
to name which aggregator it refers to.

**The paper's figures looked irreconcilable with this, and the subset run
resolved it.** Their ≥7B judges "cluster above 0.5 Tau-C", which is *above* the
0.405 human ceiling measured here, and that seemed to demand a judge outperform
every typical annotator. It does not. A human is scored leave-one-out against
the mean of the *other 14* raters; a judge is scored against the mean of **all
15**, which is less noisy. Beating the average individual human is therefore
expected, not suspicious — `qwen3:8b` did it at 0.513. The two numbers measure
slightly different things and both stand.

The ceiling is still the right anchor for a *threshold*, because it is the
honest answer to "how well do humans do this task". It is not a cap.

## The scale is compressed at the top — measured 2026-09-15

Two findings from data already on disk, no new runs. Both bear on the
calibration failure recorded above, and the second answers an open question
ADR-023 left.

**1. The judge avoids the middle of its scale.** The 631-speech validation run
(`probe/validation/judge-scores-qwen3-8b-full.json`) scored on 1–5:

| score | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| count | 96 | 233 | **41** | 194 | 67 |
| share | 15.2% | 36.9% | **6.5%** | 30.7% | 10.6% |

The distribution is **bimodal with a hole at the midpoint** — 3 is used a fifth
as often as its neighbours. A judge that rarely says "middling" turns small
quality differences into large score gaps, which is a property worth knowing
about a tool whose output is a comparison.

**2. Over half of all rubric dimensions ever scored came back at maximum.**
Across every debatebench score file on disk, deduplicated to **4 distinct
dimension-score sets** (the 25 `probe/b6` files are one transcript re-judged, so
they count once):

| | side 0 | side 1 |
|---|---|---|
| `examples/scores.json` | 100/100, 5 of 5 maxed | 91/100, 0 maxed |
| `examples/scores-prep.json` | 100/100, **5 of 5 maxed** | 100/100, **5 of 5 maxed** |
| gemma4:12b mirror run | 85/100, 0 maxed | 93/100, 1 maxed |
| `probe/b6` gate transcript | 97/100, 3 maxed | 95/100, 2 maxed |

**21 of 40 dimension scores (52%) sit at the maximum**, and every total observed
falls in **85–100**. The bottom 85% of a 100-point scale has never been used.

**This answers ADR-023's open question.** It asked whether an observed tie means
"equal" or "the scale topped out". The one draw on record is `scores-prep.json`
at 100/100 against 100/100, with **all ten dimensions at maximum**. That is a
ceiling, not a close contest — so the coin toss ADR-023 introduced is, on the
only tie we have, resolving a saturation artefact rather than a genuine dead
heat. The toss is still the right call for a tie; what this says is that *ties
of this kind are evidence about the rubric*, and a run of them should be read as
the scale failing rather than the debate being even.

**Sample caveats, stated rather than buried.** Four distinct score sets, three
transcripts, two judge models — far too few to put an interval on. The 1–5
distribution is a different task (single speeches, one dimension) from the
0–100 rubric and corroborates only the shape, not the numbers. What is solid is
the direction: both measurements point the same way, and neither required a new
run to find.

**What would settle it:** score a deliberately weak debate — one side arguing
badly on purpose — and see whether the rubric can reach the bottom half at all.
That is one debate and one judge call, and it is the cheapest test of whether
these scores carry information below 85.

## Decisions

1. **Acceptance threshold — proposed, anchored on the table above.** Against the
   **raw** mean: **≥ 0.38 is credible** (matches the median human annotator),
   **0.30–0.38 marginal**, **< 0.30 is worse than a typical annotator** and the
   judge should not be trusted. Chosen before any judge has been run, which is
   the point. Revisit only if the paper-discrepancy above resolves in a way that
   changes what the ceiling means — not because a result lands just under.
2. **Scope — a dedicated session** between B5 and B7. Folding it into B5's
   already-passed exit gate would quietly reopen that gate.
3. **Coverage accepted as scoped**: this validates `argument_quality` against a
   single blended human score. The winner logic, the steelman tiebreak,
   `rebuttal_effectiveness` and the fact-check pass remain unvalidated, and B7's
   README must say so rather than implying the judge was validated wholesale.
4. **Run size — stratified subset first, then the full 631.** All 8 sources
   proportionally, for a first signal in well under an hour; the full set is the
   publishable number and only worth its ~1.75 h once the subset looks viable.

**Dependency note:** this analysis uses `scipy` from the system Python, not the
package venv. ADR-008 fixes the shipped runtime at `httpx` + PyYAML, and a
validation script is no more part of the runtime than `probe/backend/` is.
Nothing here is added to the package's dependency surface.
