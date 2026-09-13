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

## Decisions this needs before any code

1. **The acceptance threshold.** The paper states none. Pick a Tau-C value that
   means "trust this judge" **before** seeing our results, or it becomes
   post-hoc justification.
2. **Scope** — a dedicated session between B5 and B7, or folded into B5's exit
   gate. Item 6 offers both. Folding it into a gate that has already passed
   would quietly reopen that gate.
3. **Accepting the coverage above**, explicitly, including that the winner logic
   and the fact-check remain unvalidated.
4. **Run size.** 631 speeches × ~600 words is roughly 1.75 h per model at this
   machine's measured rates. A stratified subset (all 8 sources, proportional)
   would give a first signal in well under an hour; the full set is the
   publishable number.
