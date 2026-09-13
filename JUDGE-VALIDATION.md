# Judge Validation — method, data, and the decisions it still needs

**Status:** method established, **nothing run yet**. This is OPEN-QUESTIONS item
6, which blocks B7 and blocks trusting any score from B5 onward.

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

**This does not reconcile with the paper's figures, and that is unresolved.**
Their ≥7B judges "cluster above 0.5 Tau-C", which is *above* the human ceiling
measured here. Either they correlate against a mean that includes the annotator
being scored (which inflates agreement), or their Figure 2(b) is a different
comparison than leave-one-out. **Not verified — do not adopt 0.5 as a target
without resolving it**, because on this measurement 0.5 would mean demanding a
judge outperform every typical human annotator.

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
