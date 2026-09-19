# ADR-036: `debate --show-prompt` Renders What the Config Becomes

**Status:** Accepted
**Date:** 2026-09-19
**Depends on:** ADR-007 (`run.yaml` is the whole config), ADR-010 §2 (what each
phase asks for), ADR-016/ADR-022 (`name:length`, and a bare entry means
`medium`), ADR-021 (the override flags), Hard Rule 7
**Does not amend:** ADR-021. This is not an override — it changes nothing about
a run, and cannot, because it makes no model call.

## Context — the config names the ingredients, Python writes the sentence

A user writes `stance: progressive` in a team file and `rebuttal:medium` in a
phase list. What the model receives is:

```
You are Universal Coverage Advocate, a debater. Your outlook: progressive.
Your voice: plain-spoken and moral, argues from who is left out and what it
costs them. What you value: universal-access, cost-control, dignity.

The motion is: Government should provide universal health care.
You argue for the motion, whatever your own view.
```

and, for that phase:

```
Give your rebuttal. First state the other side's strongest argument fairly, in
terms they would accept. Then answer it, and attack their other arguments.
Answer in about 5 sentences.
```

The user chose four values and a word. Everything else — the frame sentences,
the `pro`→"for" mapping, the "whatever your own view" clause, the whole phase
instruction, and `medium` meaning **five** — is in `prompts.py` and appears in no
file they can read. `--help` does not mention it, the README does not state it,
and the transcript records the *ingredients* without the assembly.

The sharpest case is the steelman sentence. It exists only in
`PHASE_INSTRUCTIONS["rebuttal"]`, while `steelman_fidelity` is scored out of 20
in every run **and is the tiebreak** (`judging.py:172-174`, ADR-013 §3). A phase
list without `rebuttal` asks nobody to steelman and still tiebreaks on it. All
16 run.yamls in use include `rebuttal`, so nothing measured is affected; the
hazard is recorded in `OPEN-QUESTIONS` rather than fixed here, because it is a
scoring-semantics decision and not a rendering one.

## Decision

**`debate run.yaml --show-prompt` renders the prompts the run would send, to
stdout, and exits 0 without calling a model or writing a file.**

1. **It shows the exact strings.** The system prompt per side and the
   instruction per phase are rendered by **the same functions that build the
   real request**, never re-implemented. A preview that can drift from what ships
   is worse than no preview.
2. **Every fragment names its origin** — the file and key it came from, or
   `built in`. That is the feature; the prompt text alone would only move the
   problem.
3. **Overrides apply first.** `--pro-model` and friends change the config before
   rendering, exactly as they do before a run (ADR-021), so the preview is of
   what *would* run, and doubles as a check on the flags.
4. **It refuses `--events`.** No run happens, so there are no events, and both
   write to stdout. Refusing with a sentence beats emitting an empty stream.

## What it cannot show honestly, and how it says so

A turn's user message is `render_debate(...)` plus the instruction, and
`render_debate` depends on the turns already spoken. Only the first turn of a run
is knowable in advance ("Nothing has been said yet. You speak first.").

So the preview is **exact for the system prompt and the instruction, and
structural for the debate-so-far** — it names which turns will be in that slot
and in what order, rather than inventing text. Likewise `prep`: the retrieved
passages are the body of that prompt, and **`--show-prompt` runs no retrieval**,
naming the corpus and the slot instead. Showing real passages would make the flag
depend on the corpus being present and would answer a different question ("what
evidence did my side get?") than the one asked ("what does my config become?").
That is a plausible follow-on, not this ADR.

Stating the boundary is the point: a preview that quietly fabricated a
debate-so-far would be exactly the kind of unverifiable artifact this project
keeps finding in its own measurements.

## Why a flag rather than a document

A `PROMPTS.md` would be a second copy of the strings, and it would be wrong the
first time someone edited `prompts.py` without it. Rendering from the live code
cannot go stale. It also resolves per-run values — *this* team's stance, *this*
phase's length — which a document cannot.

## Consequences

- `prompts.py` gains a segment representation: `system_prompt()` becomes the join
  of annotated fragments rather than an f-string. A test asserts the join is
  byte-identical to the prompt actually sent, so the two cannot diverge.
- `prompts.py` stays stdlib-only (`tests/test_layering.py` unchanged): the
  segments carry provenance as plain strings, and the CLI does the formatting.
- This is the **authoring-time** half of prompt visibility. The recording half —
  a transcript that says which prompt and which request shape produced it — is
  separate and still owed. `thinking` is a per-side `run.yaml` field that
  demonstrably changes output (ADR-033: 2,254 characters of thinking to zero,
  ~10× faster) and appears nowhere in `SideSnapshot`, which is the same defect as
  `strict_json` missing from the score file.
- It is the precondition for making prompts tunable outside Python: an editable
  prompt is only safe once a user can see what the current one is.
