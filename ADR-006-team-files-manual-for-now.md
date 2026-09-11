# ADR-006: Team Files — Manual Authoring Now, PersonaKit Alignment Later

**Status:** Accepted
**Date:** 2026-09-11
**Depends on:** ADR-002 ("Config")
**Resolves:** OPEN-QUESTIONS.md item 1

## Decision

Drop the claim that `teams/*.yaml` files are "PersonaForge-compatible" with "zero
conversion step." That claim was asserted in ADR-002 and `CLAUDE.md` without
checking it against PersonaKit's actual `PersonaDefinition` schema
(`~/Projects/PersonaKit/Sources/PersonaKit/PersonaDefinition.swift`). It's false:
the two schemas share only `id` and `name`. `voice`, `stance`, `corpus` and
`values` don't exist on `PersonaDefinition`; it requires roughly a dozen fields
(`categoryID`, `region`, `era`, `instructions`, `fewShotExamples`,
`schemaVersion`, …) that a team file doesn't have. One is JSON, the other YAML.

**For now: team files are authored by hand**, directly against the schema
already defined in ADR-002 (`id`, `name`, `voice`, `stance`, `corpus`, `values`,
no `model`/`budget`). No dependency on PersonaForge, PersonaKit, or any
conversion tooling. This unblocks B1 immediately.

**Aligning with PersonaKit is real, future, separate work — not started, not
scheduled.** Two shapes it could take, decided later, on the PersonaKit side:

1. Add an optional debate-oriented extension to `PersonaDefinition` (`voice`,
   `stance`, `corpus`, `values` as additional optional fields), so a persona
   authored in PersonaForge can serve as a team file directly.
2. Write a one-way converter, `PersonaDefinition` → team YAML, kept in whichever
   repo makes more sense once it exists.

Which of these (or something else) is right is a question for whoever's working
on PersonaKit next, informed by what PersonaForge's other consumers need — not
decided here, and not blocking anything in this repo.

## Why

Hand-authoring is strictly simpler than either real option above, and this repo
doesn't need PersonaForge at all to make progress: `run.yaml` already points at
a `team:` file by path, and nothing downstream of that (B1's validation, B2's
orchestration loop, B4's Prep phase) cares how the file was created. Deferring
the schema question costs nothing now and avoids designing PersonaKit changes
under pressure from debatebench's own schedule.

## Consequences

- OPEN-QUESTIONS.md item 1 is resolved; B1 is unblocked.
- ADR-002's "Config" section and `CLAUDE.md`'s "Config" section both need their
  "PersonaForge-compatible... zero conversion step" wording corrected — the
  underlying decision (no `model`/`budget` in team files) stands on its own
  reasoning and doesn't need the compatibility claim to justify it.
- A handful of hand-written team files (liberal, conservative, at minimum) need
  to exist before B1's exit-gate test cases can use real fixtures rather than
  synthetic ones. Not a blocker — placeholder fixtures work fine for B1's own
  tests — but worth having before B4.
- When PersonaKit alignment eventually happens, every hand-written team file in
  this repo is a plain YAML file with no other tooling depending on its origin,
  so migrating them (or not) is low-stakes.
