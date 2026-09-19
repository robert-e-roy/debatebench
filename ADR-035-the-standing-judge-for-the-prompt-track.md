# ADR-035: `phi4:14b` Is the Standing Judge for the Prompt Track

**Status:** Accepted
**Date:** 2026-09-19
**Depends on:** ADR-032 (constrained JSON — `--strict-json` is not optional with
this model), ADR-031 (B6's re-specified gate: a structurally checkable ledger is
the testable condition), ADR-017 §3 (the four-verdict vocabulary)
**Does not amend:** `JUDGE-VALIDATION.md`. Its Tau-C result is about `qwen3:8b`
and stays that way; this ADR does not transfer it.

## Context — the instrument is about to become the thing under test

The next work is prompt engineering: record which prompt produced a score file,
write down the emphasis finding, then make prompts tunable outside Python. All
three need a judge held fixed while the prompt varies.

The emphasis finding is that **four of four prompt interventions shrank the
ledger** — ADR-019's emphasis block, condition B (verdict order), condition C
(user-turn framing), ADR-030 (a required `factual` field) — and ADR-034 makes a
fifth. Every one of those five data points was collected on **`qwen3:8b`**.

That is the problem. A hypothesis cannot be falsified on the data that generated
it. If the prompt track continues on `qwen3:8b`, "foregrounding a question costs
you the ledger" stays unfalsifiable: it is either a fact about prompts or a fact
about that model, and running it again on that model cannot tell the two apart.
This project has already made that mistake three times — `MODEL-COVERAGE.md`
records that conditions B, C and ADR-030 were "tuning wording against a defect
that moves with the judge."

## Decision

**`phi4:14b` is the standing judge for prompt-track measurements**, with
`--strict-json` on (ADR-032's default).

`qwen3:8b` is retained as the **back-reference**, not the instrument. Two things
stay on it, deliberately:

1. **ADR-034's named next test** — state the passages-only restriction once,
   plainly, and see whether `contradicted` holds while the ledger returns. That
   test is *defined against* `qwen3:8b` baselines (below) and would be
   meaningless rebased. It runs on `qwen3:8b` as a closing experiment.
2. **Every ordering claim.** `JUDGE-VALIDATION`'s Tau-C +0.547 is a `qwen3:8b`
   result. `phi4:14b` has no Tau-C and this decision does not give it one.

## Why — measured, on the three prep transcripts, both judges

**1. Resolution.** A prompt change can only be observed where the ledger has room
to move. Constrained, on the same transcripts:

| transcript | `qwen3:8b` | labels | `phi4:14b` | labels |
|---|---|---|---|---|
| `healthcare-0.6b-pro` | 12 | 2 | **21** | **4** |
| `healthcare-14b-pro` | 16 | 2 | **44** | **4** |
| `medicaid-14b-pro` | 12 | 3 | **36** | **4** |

`phi4:14b` returns 2–3× the claims and uses **all four verdicts on 3 of 3**.
`qwen3:8b` returns **zero `not_checkable` on all three** — a quarter of the
observable space is structurally dead on the model whose prompt sensitivity we
are trying to characterise.

**2. Stability under no change.** Two independent `phi4:14b` draws on
`medicaid-14b-pro`, `judged_at` **16:19:59Z** and **20:12:34Z** on 2026-09-17 —
three hours fifty-three minutes apart, with other models loaded in between —
produced a **byte-identical** fact-check ledger (`68d29c1aba455515` over the
`fact_check` object). *Limit, stated because it matters:* load state was not
controlled, so this is reproduction across a four-hour gap, **not** the
pre-registered cold/warm result `qwen3:8b` has. The two-draws-per-state protocol
from B6 should be run on `phi4:14b` before the first prompt A/B is quoted.

**3. Lineage distance.** The debaters are `qwen3`. `phi4:14b` is phi3-family.
`qwen3:8b` judging `qwen3` debaters is the same-family bias an LLM judge is most
prone to, and it is what every judging result before 2026-09-17 was.

**4. Operationally the cleanest model on the ladder.** `trained_ctx` **16,384**,
so it fits as shipped at 9.1 GB with **no `num_ctx` Modelfile** — the only
candidate this week that needed no capping, against four that did
(`mistral-nemo` 51.8 GB, `qwen3:4b` ~43 GB, `selene` 22.5 GB, `llama3.1`/
`command-r` both at 131,072). No reasoning tax, so `budget` means completion.

## What this costs, stated plainly

- **No validated ordering.** `phi4:14b` has no Tau-C run. Any winner it picks is
  a judge's opinion with no human-agreement evidence behind it. Ordering claims
  keep coming from `qwen3:8b`.
- **It may distort the other way.** `phi4:14b` marked **24 of 44** claims
  `not_checkable` on `healthcare-14b-pro` — the same direction as
  `command-r:35b`'s 25 of 27, if far less extreme. An isolation test on its
  cross-side contradictions found one confirmed by four models, one contested and
  one **false positive**. Labels appearing reliably is not labels being correct.
- **`--strict-json` is load-bearing with it.** Unconstrained it emits doubled
  quotes inside justifications (4 of 10) and uses all four verdicts on only 1 of
  3 transcripts. Constrained: 3 of 3. This model is a good instrument *because
  of* ADR-032, not independently of it.
- **The `phi4` tag collision is real.** `phi4:14b` once overwrote `phi4-mini`'s
  score files. Score-file names must carry the judge.

## The baselines this decision freezes

`qwen3:8b`, `--strict-json` on, before and after ADR-034, so the closing test has
something to be measured against:

| transcript | claims (on → ADR-034) | `contradicted` |
|---|---|---|
| `healthcare-0.6b-pro` | 12 → 7 | 3 → **0** |
| `healthcare-14b-pro` | 16 → 13 | 2 → 2 |
| `medicaid-14b-pro` | 12 → 10 | 4 → **0** |
| **total** | **40 → 30** | **9 → 2** |

The headline recorded earlier was the ledger, 40 → 30. The sharper number is the
second column: **ADR-034 cost seven of nine `contradicted` verdicts**, on the two
transcripts where it shrank the ledger most. That is the fifth data point in the
emphasis finding, and the most expensive one.

## Consequences

- Prompt-track runs name `phi4:14b` and `--strict-json`; `qwen3:8b` runs are
  labelled as back-reference, not as the result.
- Before the first prompt A/B is quoted, `phi4:14b` gets B6's two-draws-per-state
  protocol on one transcript. If it turns out state-sensitive, the protocol holds
  state constant exactly as `qwen3:8b`'s does — it does not disqualify the model.
- `MODEL-COVERAGE.md` gains `phi4:14b`'s ledger sizes, label coverage and the
  reproduction result.
- **A score file cannot currently record any of this**, which is why the prompt
  track starts where it does: it stores `judge_model`, `judge_budget` and
  `fact_check_enabled`, and **neither `strict_json` nor the prompt**. The
  `strict_json` arm of every comparison above was recoverable only from the
  *filename* someone chose. That is a confound waiting to happen, and it already
  happened once this month (ADR-034's first measurement compared against a
  pre-ADR-032 arm). The first item of the prompt track therefore records the
  **request shape** — prompt fingerprint, `strict_json`, `thinking` — not the
  prompt alone.
