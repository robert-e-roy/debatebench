# Mirror runs — does speaking position decide the winner?

OPEN-QUESTIONS 9 says a model comparison can't separate "the bigger model argued
better" from "that side of the motion is easier" from judge bias. A **mirror
run** removes the first two by construction: the *same team file* on both sides,
the same model, the same budget. Whatever is left is position.

Config: `~/gem.yaml` — "Are DataCenters good for the community",
`Free-Market Conservative` on both sides, `gemma4:12b` debating and judging,
`budget: 2000` per phase, `phases: [opening, rebuttal, rebuttal, conclusion]`,
**no `seed:`**, so every run draws a fresh one and is an independent sample.

## Result — 9 of 9 to con

| run | seed | pro | con | margin |
|---|---|---|---|---|
| 1 | 584785143 | 85 | 91 | **+6** |
| 3 | 377027683 | 88 | 93 | **+5** |
| 4 | 744711221 | 87 | 92 | **+5** |
| 5 | 1053551035 | 92 | 95 | **+3** |
| 7 | 522445644 | 87 | 92 | **+5** |
| 8 | 790430574 | 92 | 95 | **+3** |
| 9 | 242913766 | 85 | 90 | **+5** |
| 10 | 2030440005 | 84 | 93 | **+9** |
| 11 | 1286180209 | 89 | 93 | **+4** |

**Con won every run**, by 3 to 9 points, mean +5.0. The margin never narrowed to
a tie and never inverted. Nine of nine one-sided is **p ≈ 0.004** two-tailed
against a fair coin — the first result in this project that would survive a
significance test.

Every total falls in **84–95**, which is the compression band `JUDGE-VALIDATION`
records, on a third model.

## What it does and does not establish

**Ruled out by construction:** model strength and stance difficulty, the two
confounds OPEN-QUESTIONS 9 names. Both sides are byte-identical persona files.

**Not separated:** the *label* (`con` in the prompt, `side_index` 1) from the
*speaking position*. With `[opening, rebuttal, rebuttal, conclusion]` the order
is `(pro,con) (con,pro) (pro,con) (con,pro)`, so con replies second in two
phases and opens two — and **pro** has the last word of the debate, which rules
out a simple recency effect on the final turn.

**Scope:** one motion, one persona, one model, one phase structure. A strong
result about this configuration, not a law about the judge.

## The experiment that would separate label from position

Add one argument phase — `[opening, rebuttal, rebuttal, rebuttal, conclusion]`.
`speaking_order` alternates on `argument_phases_before % 2` (ADR-010 §1), so the
slots invert and con concludes first while pro replies second twice. If con still
wins, the label is doing the work; if the winner follows the slots, position is.
Same harness, N=9 for comparability.

## Method notes — two runs were discarded, and how they were caught

11 runs were attempted; **2 are quarantined as `*.INVALID-stale-copy.json`** and
excluded above. Both were defects in the *harness*, not the tool, and both were
found by checking artifacts rather than by trusting the script:

- **Run 2** — the judge failed with malformed JSON, and the script's
  unconditional `cp ~/gem-scores.json` copied the *previous* run's score file.
  Caught by an identical `judged_at` with run 1.
- **Run 6** — the debate failed ("all reasoning and no answer", 9,713 characters
  of thinking), the script's `grep -E "wrote|failed"` matched the *failure* text
  so the exit check passed, and `judge` then read the stale transcript still
  sitting at `output:`. Caught by an identical seed with run 5.

That second one is ADR-027 §6's warning arriving in practice: **a failed debate
leaves the previous run's file at `output:`**, and anything that assumes a
missing file signals failure will read stale data and produce a result that looks
valid. The fix used from run 6 onward is `judge --output <artifact>` directly, so
a failed judge leaves no file at all.

**Every run here is validated by seed uniqueness**, not by the script's own
report. Any future batch should be checked the same way.

One further data point for ADR-026: run 7's judge returned malformed JSON and
**succeeded on a single retry** — the first direct evidence that one retry
suffices, which is exactly the convenience that ADR-026 declines to build into
the tool, because the visible failure is what makes rates like this measurable.
