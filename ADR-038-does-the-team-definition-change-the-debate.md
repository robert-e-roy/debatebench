# ADR-038: Does the Team Definition Change the Debate?

**Status:** Accepted — protocol fixed, **predictions recorded, runs not yet made**
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
