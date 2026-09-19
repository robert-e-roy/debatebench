# ADR-037: A Run Records What Shaped Its Output

**Status:** Accepted
**Date:** 2026-09-19
**Depends on:** ADR-005 (transcript format), ADR-013 §4 (score-file format),
ADR-012/ADR-014 (retrieval and the shared pools), ADR-032 (`strict_json`),
ADR-033 (`thinking`), ADR-036 (the prompt segments this reuses)
**Schema:** transcript `schema_version` **2 → 3**, score `schema_version`
**2 → 3**. Both readers accept every earlier version; every new key is additive.

## Context — three things change the output and none of them are written down

ADR-036 made the prompts visible *before* a run. This is the other half: a
finished file that says what produced it.

Measured gaps, each verified rather than assumed:

1. **`thinking`** is a per-side `run.yaml` field (`config.py:88`) that changes
   output substantially — ADR-033 measured `gemma4:12b` going from 2,254
   characters of reasoning to zero, roughly 10× faster. It appears nowhere in
   `SideSnapshot`. Two runs differing only in `thinking` produce transcripts that
   cannot be told apart.
2. **`strict_json`** is the same defect one command over. ADR-032 measured parse
   failures 5 of 9 → 0 of 9 and ledgers growing rather than thinning. The score
   file records `judge_model`, `judge_budget` and `fact_check_enabled`, and not
   this. Separating the two arms of that comparison, on 2026-09-19, meant reading
   **filenames** someone had chosen by hand.
3. **`sources:` is recorded nowhere at all.** Not in `RunSnapshot`, not in
   `SideSnapshot`. `Evidence.source` is the originating *row's* source, not the
   pool. The pool is `~/.cache/debatebench/sources/<name>.jsonl`, whose location
   is overridable with `DEBATEBENCH_SOURCES_DIR`, and whose contents can be
   rebuilt with different filtering at any time.

The third is the worst of them, and it is the one a user raised rather than the
code review. The prompt has `debatebench_version` as a weak pin and now
`--show-prompt` to recover it. The corpus has **nothing**: two prep runs on one
machine can draw from different pools, with different row counts and different
passages, and no field in either file shows it.

**What is already recorded, and does not need this ADR:** the team's own wording.
`TeamSnapshot` carries `name`, `voice`, `stance` and `values`, so a transcript
already preserves the exact words that shaped each debater, and a prep turn
already carries the passages that actually reached the model. The gap is not the
evidence — it is *which pool it was drawn from*.

## Decision

**A transcript and a score file each record the request shape and the prompt that
produced them.**

### Transcript, `schema_version` 3

```json
"run": {
  "prompt": {
    "fingerprint": "5f2a91c0d4e77b13",
    "system": "You are {name}, a debater. Your outlook: {stance}. ...",
    "phases": {"opening:medium": "Give your opening statement: ... about 5 sentences."}
  },
  "sources": [{"name": "args-me", "rows": 4784, "fingerprint": "d49e5746056ec0e6"}],
  "sides": [{"thinking": true, ...}]
}
```

### Score file, `schema_version` 3

```json
"prompt": {
  "fingerprint": "8b71e0aa4c2d1f96",
  "score_system": "You are judging a formal debate against a fixed rubric. ...",
  "fact_check_system": "You are auditing a finished debate. ..."
},
"strict_json": true,
"thinking": true
```

## Why the two prompts are recorded differently

**The debate prompt is a frame with holes**, so it records as a template:
`system` is ADR-036's segments with each config value replaced by its `{slot}`.
That is both readable and exactly the artifact a tunable prompt file would hold.
The per-phase instruction contains no config value at all — the resolved sentence
count is `debatebench`'s — so it records verbatim, keyed by the `phase:length`
label the run asked for.

**The judge prompt is not a frame, and templating it would record a string that
was never sent.** Both judge system messages *branch*: the scoring prompt's
`evidence_grounding` line differs on `_prep_grounded(transcript)`, and the
fact-check prompt's passage-id line differs on whether any ids were recorded. So
the judge records the **exact system message** for each of its two calls. That is
safe because the transcript itself lives in the *user* message: the system string
carries no per-run content, so it is stable across transcripts and varies exactly
when the prompt or its branch varies.

Two mechanisms because the two prompts have genuinely different structure. One
mechanism forced onto both would have to lie about one of them.

## What the fingerprint is, and what it deliberately is not

A 16-character BLAKE2b digest over `debatebench`'s **own** contribution: the
system template plus every phase instruction the run used, in phase order; for
the judge, the two system messages.

- It is **invariant** to topic, team, model, seed and turns. Two runs on
  different motions with the same build share a fingerprint, which is what makes
  "same instructions?" a one-glance question.
- It **moves** when a prompt is edited — including an edit that never reaches a
  released version number, which is the case `debatebench_version` cannot cover
  and which becomes the normal case once prompts are tunable.
- It is **not** a content hash of the whole request. The debate-so-far differs
  between any two runs by construction, so hashing the full message would differ
  always and mean nothing.

## Consequences

- `READABLE_VERSIONS` becomes `(1, 2, 3)`; the reader already uses `.get()` for
  optional keys, so v1 and v2 files keep loading and simply carry no prompt
  record. Nothing re-judges differently.
- Hashing a pool costs about 47 ms for the 4.9 MB `args-me.jsonl`. There is no
  performance argument for leaving it out.
- `sources` is recorded only for a run whose phases include `prep`. A run that
  never retrieved must not claim a corpus it did not read.
- **The tests assert the difference, not the presence.** Two runs differing only
  in `thinking`, or only in `strict_json`, must produce files whose recorded
  fields differ; mutating one row of a fixture pool must move the recorded
  fingerprint. A field that exists but never varies would close nothing.
- This unblocks tunable prompts (the user's standing requirement that prompts be
  settable outside Python). An editable prompt is only safe once a file records
  which one it used — otherwise every past result becomes uninterpretable the
  first time someone edits one. **Tunable prompts are not in this pass.**
