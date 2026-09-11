# ADR-005: Transcript Format — the `debate` → `judge` Contract

**Status:** Proposed
**Date:** 2026-09-11
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
  "budget": 2000, "finish_reason": "stop",
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
- **`usage` is as reported by the backend** (fields are `null` if not reported);
  `budget` is the limit the orchestrator applied. Together they make every budget
  claim checkable after the fact (Hard Rule 5). ADR-003 shows `finish_reason` alone
  can't be trusted for this.
- **A `prep` turn also carries `evidence: [...]`**, that side's recorded evidence
  set. The item shape is provisional until B4. At minimum each item has a stable
  `id`, the `source` it came from, and its `text`.
- **No fact-check verdicts in version 1.** Where the fact-checker lives — inside
  `debate`, inside `judge`, or as its own command — is undecided (B6). Adding its
  output later is a `schema_version` bump.

### Writing

- The document is written only after every configured phase has a response from
  every side (Hard Rule 1). On failure, nothing is written to the output path.
- It is written atomically: to a temporary file in the target's directory, flushed
  and fsynced, then moved onto the output path with `os.replace`. A crash
  mid-write can't leave a partial file.
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

## Open questions (decide before accepting)

1. **An existing file at the output path.** "Nothing written on failure" doesn't stop a
   stale transcript from an earlier run sitting at the same path, and `judge`
   would score it without complaint. Either refuse to start if the path exists
   (unless `--force`), or delete it at start and lose the old file even if the new
   run fails.
2. **What counts as a valid turn** — a refusal, empty text, or a reply that
   reached its budget (which ADR-003 shows can't be detected from
   `finish_reason`). This decides what `turns` may contain.
3. **What "round" means**, given ADR-002's `rounds: 3` alongside an explicit phase
   list. The key above works either way, but the `run` snapshot should record
   whatever `rounds` turns out to mean.
4. **Human-readable rendering.** ADR-001 notes aragora's paired machine- and
   human-readable views as precedent. If wanted, it's derived from this file by a
   separate step; `debate` writes nothing but its output file (Hard Rule 7).
