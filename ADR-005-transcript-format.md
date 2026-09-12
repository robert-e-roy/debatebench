# ADR-005: Transcript Format — the `debate` → `judge` Contract

**Status:** Accepted (2026-09-11)
**Date:** 2026-09-11
**Amended:** 2026-09-11 — accepted with ADR-010, which settles what counts as a
valid turn and adds `hit_budget` and `budget_tolerance`. Two questions about
writing the file moved to B3.
**Depends on:** ADR-001 (never key by side alone; output file only), ADR-002 (two commands, hard invariant), ADR-003 (token usage reporting), ADR-007 (`run.yaml` schema; `output:` path)

## Decision

`debate` writes one UTF-8 JSON document to the `output:` path in its `run.yaml`
(ADR-007), and `judge` reads it. It
is the only interface between the two commands, so it's versioned from the first
release.

### Top level

```jsonc
{
  "schema_version": 1,
  "debatebench_version": "0.1.0",
  "started_at": "2026-09-11T14:02:11Z",
  "finished_at": "2026-09-11T14:09:47Z",
  "run": {
    "topic": "...",
    "seed": 42,
    "budget_tolerance": 16,  // tokens a reply may exceed its budget by (ADR-010)
    "phases": ["prep", "opening", "rebuttal", "retort", "rebuttal", "conclusion"],
    "sides": [
      { "index": 0,
        "team_file": "teams/liberal.yaml",
        "team": { "id": "liberal-climate", "name": "...", "stance": "liberal" },  // full team-file contents
        "side": "pro", "model": "qwen3-8b", "base_url": "http://127.0.0.1:8080/v1", "budget": 2000, "prep_budget": 1500 },
      { "index": 1, "...": "..." }
    ]
  },
  "turns": [ /* see below */ ]
}
```

- **`schema_version`** is an integer, starting at 1, bumped on any change to the
  document's shape. Readers refuse a version newer than they support and migrate
  older ones forward. That's the workspace rule for persisted formats, the same
  pattern PersonaKit's `schemaVersion` follows.
- **`run` is a snapshot of the resolved config**, including each team file's
  contents, not just its path. A transcript must stay interpretable after its
  `run.yaml` or team files change or disappear. API keys, and any credentials
  embedded in URLs, are never written.
- **`run.phases` is the expanded phase list**, exactly as executed.

### Turns

```json
{ "phase_index": 2, "phase": "rebuttal", "side_index": 0, "order": 1,
  "text": "...",
  "usage": { "prompt_tokens": 812, "completion_tokens": 388 },
  "budget": 2000, "hit_budget": false, "finish_reason": "stop",
  "latency_ms": 5120, "started_at": "2026-09-11T14:04:02Z" }
```

- **Key: `(phase_index, side_index)`**, unique within a transcript. `phase_index`
  is the position in `run.phases`, so a phase name that appears twice
  (`rebuttal`) never collides. This meets Hard Rule 2's intent (never key by side
  alone) however "round" ends up being defined. If `rounds` gets semantics later,
  `round` is added as a field without changing the key.
- **`side_index` is positional** — the order of `teams` in `run.yaml`, not the team
  `id`. Two sides may use the same team file with different models, which is a
  legitimate benchmark configuration, and a team-id key would collide.
- **`order`** records who spoke first within the phase (0 or 1), so alternating
  initiative can be checked after the fact.
- **`usage` is as reported by the backend**, and is never absent: a reply without
  token usage fails the turn (ADR-009), because a budget checked against a
  made-up zero is no check at all. `budget` is the limit the orchestrator applied,
  and `hit_budget` says the reply reached it and may have been cut off. Together
  they make every budget claim checkable after the fact (Hard Rule 5). ADR-003
  shows `finish_reason` alone can't be trusted for this.
- **A `prep` turn also carries `evidence: [...]`**, that side's recorded evidence
  set. The item shape is provisional until B4. At minimum each item has a stable
  `id`, the `source` it came from, and its `text`.
- **No fact-check verdicts in version 1.** Where the fact-checker lives — inside
  `debate`, inside `judge`, or as its own command — is undecided (B6). Adding its
  output later is a `schema_version` bump.

### Writing

- The document is written only after every configured phase has a response from
  every side (Hard Rule 1). On failure nothing is written, and any file already at
  the output path is left exactly as it was.
- **An existing transcript is rotated, not overwritten** (open question 1,
  decided 2026-09-11). Immediately before the new file takes its place, whatever
  sits at the output path is moved to `<output>.1`, replacing whatever `.1` held.
  A run therefore never destroys the previous run's transcript, and `judge`
  reading the output path always gets the newest one. Only one generation is
  kept: a second successful run replaces the backup.
- It is written atomically: to a temporary file in the target's directory, flushed
  and fsynced, then moved onto the output path with `os.replace`. A crash
  mid-write can't leave a partial file. The temporary file is written in full
  before the rotation, so a failure while serializing changes nothing.
- Strict JSON: `allow_nan=False`, and non-ASCII text kept as-is
  (`ensure_ascii=False`).

## Why

- ADR-002's two-command split only works if the file between the commands is a
  fixed, versioned contract. B2 builds it, B3 writes it, B5 reads it, and B5's exit
  gate requires hand-writing a lopsided one. None of that is possible against an
  unspecified shape.
- Snapshotting the resolved config is what lets a transcript be re-judged later —
  ADR-002's stated reason for having two commands — without trusting that the
  original config files still say what they said.
- Recording `usage`, `budget`, `order` and `latency_ms` per turn makes the
  asymmetric-budget comparison, which ADR-002 calls core to the product,
  auditable rather than just asserted.

## Consequences

- **B3's reproducibility check should compare each turn's `text`** (and `usage`),
  not whole files. Timestamps and latencies differ between identical runs by
  design.
- **`judge` validates its input strictly.** An unknown `schema_version` or a
  missing required field is an error, never a guess.
- **The format is defined once, in code** (dataclasses), and both commands use that
  one definition, so `debate` and `judge` can't drift apart.
- **The `FakeBackend` (ADR-004) and hand-written test transcripts** follow this
  format.

## Open questions

1. **Human-readable rendering (B3 at the earliest).** ADR-001 notes aragora's
   paired machine- and human-readable views as precedent. If wanted, it's derived
   from this file by a separate step; `debate` writes nothing but its output file
   (Hard Rule 7).

**Settled since this was drafted:** what counts as a valid turn (ADR-010 §3);
what "round" means — nothing, since ADR-007 dropped `rounds`, so turns are keyed
by `(phase_index, side_index)`; and what happens to an existing file at the
output path, now rotated to `<output>.1` (see "Writing"). An earlier draft
proposed a `--force` flag for that, which ADR-007 §1 rules out: `debate` takes
one argument and no flags.
