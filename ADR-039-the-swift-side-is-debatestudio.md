# ADR-039: The Swift Side Is `DebateStudio`, Not `DebateKit`

**Status:** Accepted
**Date:** 2026-09-20
**Amends:** ADR-002 — "Naming" (the Swift library line), "Language split", and
every forward reference to the Swift project
**Does not amend:** ADR-002's two-repo split, which stands unchanged

## Decision

**The Swift project is `DebateStudio`.** It exists at
`~/Projects/DebateStudio/`, created 2026-09-20, and its first document is
`S0-mlx-probe.md`.

`DebateKit` is retired as a project name. The empty
`~/Projects/DebateKit/` directory, reserved since 2026-09-11 and never used, is
removed so there is one name rather than two.

## Why

**ADR-002's own reasoning now points the other way.** It chose `DebateKit` as
"consistent with existing `Kit`-suffixed libraries (CorpusKit, JsonHelpKit)" —
and that convention is real, but it is a convention for **libraries**. This
workspace already distinguishes the two:

| | |
|---|---|
| `CorpusKit`, `JsonHelpKit`, `PersonaKit`, `DataMoldCore` | SwiftPM **libraries** |
| `CorpusKitStudio`, `PersonaForge`, `PersonaChat` | the **apps** on top of them |

`CorpusKit` / `CorpusKitStudio` is the exact pair: the engine carries `Kit`, the
app carries `Studio`. ADR-002 describes the Swift side as *"the shipped
product"* with a UI, a live dashboard and a real-time fact-check panel. That is
an app, so it takes the app suffix. Applying the library convention to it was a
consistency argument pointed at the wrong noun.

**This does not rule out a `Kit`.** The workspace pattern is "engine package +
thin app" (`Projects/AGENTS.md`), so `DebateStudio` will very likely contain a
SwiftPM package holding the orchestration logic. If that package wants to be
`DebateKit`, the name is free and the convention then applies correctly — to a
library. What changes here is only what the **project** is called.

## Consequences

- Forward-looking references across the repo are updated:
  `ADR-002` (four places), `ADR-015`, `BUILD-GUIDE`, `HARDWARE-FLOOR`,
  `CLAUDE.md`, `OPEN-QUESTIONS`.
- **Historical references are deliberately left alone.** `ADR-001`, `CLAUDE.md`
  and `OPEN-QUESTIONS` each record that the R0 evidence *"was moved from
  `~/Projects/DebateKit/` on 2026-09-11"*. That happened, under that path.
  Rewriting it would make a true statement false, which is a worse outcome than
  a stale name in a sentence about the past. Three references therefore still
  say `DebateKit` and should stay that way.
- ADR-002's two-repo split is untouched: `DebateStudio` is its own repository
  with no build-time or runtime dependency on this one, and the relationship is
  still "its design is ported from a stabilized version of this CLI's logic".
- `CLAUDE.md`'s out-of-scope rule now reads: a task referencing "the Swift side",
  `DebateStudio`, or the companion app is out of scope in this repo and should be
  flagged rather than reached across to.
