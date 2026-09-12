# ADR-007: `run.yaml` Schema — CLI Invocation, Budgets, Sources, Phase Declaration

**Status:** Accepted
**Date:** 2026-09-11
**Amended:** 2026-09-11 — added §6, the validation details B1 needs (paths,
unknown and duplicate keys, phase names, team-file fields, types), and §7,
each team's side of the motion (`side: pro` / `side: con`). **Amended
2026-09-12** (via ADR-013): `judge` gains a required `--budget` flag, the
completion-token cap for its one scoring call — ADR-013 found this was
genuinely missing, not just undocumented. **Amended 2026-09-12** (via
ADR-016): each `format.phases` entry may carry a `:length` suffix
(`rebuttal:long`); see ADR-016 §5 for the grammar and the mapping-vs-string
hint. A `length` key in a `teams:` entry is an error.
**Depends on:** ADR-002 ("Config", "CLI shape"), ADR-003 (token-budget enforcement
findings), `debate-formats-research.md`
**Resolves:** OPEN-QUESTIONS.md items 3, 8, 10 (schema-level slice), 11
(schema-level slice)

## Decision

### 1. CLI invocation — file for `debate`, flags for `judge`

`debate` takes exactly one argument: a path to a `run.yaml`-shaped file
(`debate run.yaml`). No other flags for v1. Every setting — topic, phases,
teams (`model`/`budget`/`base_url`), sources, seed, and output path — comes
from that file. **`output:` is now a required field**; B1's validation rejects
a `run.yaml` missing it. There is no `--output` flag on `debate`.

`judge` takes one positional argument, a transcript path, plus flags:
`--model` (required, no default), `--budget` (required, no default — added
by ADR-013 §2, the completion-token cap for its one scoring call),
`--base-url` (optional), `--fact-check` /
`--no-fact-check` (default: on), `--output <path>` (required).

This isn't an inconsistency, it reflects what each command's config actually
is. `debate`'s config is multi-part and fixed for that run — a file fits.
`judge`'s entire reason for being a separate command (ADR-002, "CLI shape")
is that the same transcript gets re-judged with different settings each time
— a file you'd just edit and rerun is more friction than a flag, not less.

**Consequence: the `judge:` block is dropped from `run.yaml`'s schema.**
Nothing reads it — `debate` never invokes `judge`, and ADR-005's transcript
`run` snapshot doesn't capture it. An unused block in the schema is worse than
no block; a `judge:` section in a debate config would silently suggest it
does something it doesn't.

### 2. Budget semantics — both a per-phase cap and a prep pool, as two fields

`debate-formats-research.md` shows real formats use both mechanics at once:
a fixed time per speech, plus a separate pool spent at the debater's
discretion during prep. Adopt both, as two distinct fields per side:

- **`budget`** (existing field) — a **per-phase cap, in completion tokens**
  (the unit ADR-003 found reliably honored via `max_completion_tokens`;
  `max_tokens` is silently ignored by at least one target backend). Applies
  independently to every non-prep phase.
- **`prep_budget`** (new field, per side, optional) — a single pool, in
  completion tokens, for the whole Prep phase, spent however Prep's
  retrieval/generation logic uses it. **Required if `"prep"` appears in the
  phase list; validation error if `prep_budget` is set but `"prep"` is not in
  `phases`** — no silent default in either direction, no silent ignore. That
  combination is almost always a stale config (prep removed from `phases`
  without removing its budget, or vice versa), and B1 should reject it rather
  than guess which side of the mistake is the truth.

Both are enforced by the orchestrator, not trusted from the backend — Hard
Rule 5 applies to `prep_budget` exactly as it does to `budget`.

### 3. `sources` vs. team `corpus` — shared pool plus optional per-side layer

- `run.yaml`'s top-level **`sources:`** is the shared retrieval pool available
  to every side's Prep phase equally.
- Each team file's **`corpus:`** is an *optional* additional, side-specific
  pool, layered on top of `sources:`, not a replacement for it.
- B1 validates only that both are well-formed (valid identifiers/paths). It
  does not implement retrieval or decide how queries get formed — that's B4's
  job (BUILD-GUIDE), and stays open there. This gives B1 a complete schema to
  validate against without forcing B4's mechanism questions now.

### 4. Phase declaration — `phases` is the only source of truth

**`format.prep: true/false` is dropped.** Whether Prep runs is determined
solely by whether `"prep"` appears in `format.phases` — having two ways to
say the same thing was the actual contradiction OPEN-QUESTIONS flagged, not
just an ordering-precedence question, so removing one of them resolves it
outright.

**`format.rounds` is also dropped for v1.** `phases` is already an explicit,
expanded list — the existing example (`[prep, opening, rebuttal, retort,
rebuttal, conclusion]`) already expresses a multi-round exchange by repeating
`rebuttal`, not via a multiplier. Keeping `rounds` alongside an explicit list
was the exact redundant pairing that created the open question. If a
"repeat this cycle N times" convenience is wanted later, it's a documented
macro that expands to an explicit phase list — new scope, its own ADR, not a
raw runtime field read by the orchestrator.

**Exactly two teams are required in `teams:` for v1**, enforced by B1
validation, even though it's written as a YAML list. Alternating initiative,
the steelman-fidelity premise ("the opposing side"), and the hit-ledger all
assume two sides. Supporting more is real new design work (revisiting all
three of those), not a schema tweak — out of scope without a new ADR.

**What this does not resolve, and is not trying to:** what the second speaker
in a phase sees, which phases (if any) run both sides concurrently, what
distinguishes `retort` from `rebuttal` in practice, and where in the phase
sequence steelmanning actually happens. Those are B2 (the orchestration
loop / prompt construction) questions, not B1 (config parsing) questions —
they stay open, tracked under a narrowed item 11 in OPEN-QUESTIONS.

### 5. `seed` is optional; `base_url` per team is required, no default

- **`seed`** is optional. If omitted, the tool generates one at run start,
  logs it to stderr immediately, and records the actual value used in
  `run.seed` in the output transcript (ADR-005). Every run stays fully
  reproducible from its own transcript regardless of whether a seed was
  chosen up front — this isn't a silent default in the sense `CLAUDE.md`
  warns against (an unresolved architecture question), it's an optional
  input whose actual value is always captured, never guessed and hidden.
- **`base_url` is required for every team, no default.** The backend variety
  this tool targets, `fm serve` (a manually-chosen local port), `mlx_lm.server`,
  a remote Ollama host, LM Studio, each listens somewhere different, and
  nothing about a bare `model` name like `qwen3-8b` says which one to reach.
  Guessing a default (e.g. always `localhost:8080`) risks silently talking to
  nothing, or to the wrong server. Missing `base_url` is a B1 validation
  error, same tier as a missing `output` or malformed `teams:` entry.

### 6. Validation details (added 2026-09-11)

Writing B1's validation turned up details §1–§5 didn't settle:

- **Required:** `topic`, `format.phases`, `teams` and `output` in `run.yaml`;
  `team`, `side`, `model`, `base_url` and `budget` in each `teams:` entry.
  `prep_budget` follows §2 and `side` follows §7. `seed` and `sources` are
  optional.
- **Paths resolve from the directory containing `run.yaml`**, not the working
  directory. That applies to each team's `team:` and to `output:`, so a `run.yaml`
  behaves the same wherever `debate` is run from. `~` expands to the home
  directory. A team file that doesn't exist is an error.
- **`sources` and `corpus` are kept exactly as written.** ADR-002's example lists
  `sources` as dataset names (`args-me`, `debatesum`), not paths, and whether an
  entry is a name or a path is B4's question (§3). B1 checks only that `sources`,
  if present, is a list of non-empty strings, and `corpus`, if present, is a
  non-empty string. Whether a pool must exist when `prep` runs is also B4's.
- **Unknown keys are an error:** in `run.yaml`, its `format:` and `teams:`
  entries, and team files. Otherwise a typo such as `seeed: 42` is ignored and
  the run quietly generates a seed. The keys this ADR removed (`format.prep`,
  `format.rounds`, `judge:`) get errors that say what replaced them.
- **Duplicate keys are an error.** YAML parsers silently keep the last value, so
  `budget: 100` followed by `budget: 2000` is the same class of mistake as an
  unknown key.
- **Phase names come from a fixed list:** `prep`, `opening`, `rebuttal`, `retort`,
  `conclusion`. The list must not be empty, and any other name is an error.
  `prep` may appear at most once and must come first; the others may repeat (§4).
  What each phase means stays with B2. An entry may be `name:length` with
  `length` in `short`/`medium`/`long` (ADR-016 §5); `prep` may not carry one;
  `rebuttal: long` with a space is a mapping and is rejected with a hint.
- **Team files** require `id`, `name`, `voice` and `stance` (non-empty strings)
  and `values` (a list of strings). `corpus` is optional. A `model` or `budget`
  field is an error that points to `run.yaml`: those are run-time settings, not
  identity (ADR-002).
- **Types:**
  - `topic` and `model` are non-empty strings;
  - `base_url` is an `http` or `https` URL;
  - `budget` and `prep_budget` are integers of at least 1;
  - `seed` is an integer of at least 0. Negative seeds are rejected because some
    servers read `-1` as "pick one at random".

  A boolean is never accepted where an integer is expected (ADR-008).

### 7. Each team's side of the motion (added 2026-09-11)

- **Every `teams:` entry has a required `side`.** `pro` argues for the motion in
  `topic`; `con` argues against it. One team must be `pro` and the other `con`.
  Any other value is an error, including `Pro`, `for` and `against`.
- **It lives in `run.yaml`, not the team file**, for the same reason `model` does:
  a team file is reused across topics, and the side it argues changes from run to
  run. Swapping sides (OPEN-QUESTIONS item 9) is then a one-line edit. A `side`
  field in a team file is an error.
- **A team file's `stance` (e.g. `liberal`) stays part of the persona.** It is not
  a position on the motion.
- **List order doesn't imply a side.** Either team may be listed first. Who speaks
  first is B2's question (alternating initiative, ADR-001).

Why: in B1's first live run, on "We should ban AI.", both personas argued against
the motion. Nothing assigned a side, so each model worked one out from its
persona. The spec already assumed sides were assigned: ADR-002's
stance-consistency check verifies a turn "still entails its assigned stance", and
item 9 swaps sides between runs. The labels `pro`/`con` follow formal debate
usage.

## Why

All four of these were blocking B1 for the same underlying reason: `run.yaml`
didn't yet have one unambiguous shape. Each fix here removes a way for the
same thing to be said twice (prep flag vs. phase list; rounds vs. phase list;
a `judge:` block nothing reads) or adds the one piece of information that was
missing (token unit, prep pool, exactly-two-teams). None of it is a new
subsystem — it's the schema `run.yaml` was always supposed to have, made
explicit enough for B1 to validate against.

## Consequences

- ADR-002's `run.yaml` and team-file examples need updating: `prep: true` and
  `rounds: 3` removed from `format`; `judge:` block removed entirely;
  `prep_budget` and a required `base_url` added per side, `prep_budget`
  conditional on `"prep"` being in `phases`.
- `CLAUDE.md`'s "Config" section needs the same corrections.
- BUILD-GUIDE B1's exit gate can now name concrete validation cases: missing
  `output`, missing `base_url` on any team, `prep_budget` set without
  `"prep"` in `phases` (or vice versa), a `teams:` list with other than two
  entries, and the existing malformed-YAML/missing-field cases. `seed`
  absence is explicitly *not* a validation error — it's a generate-and-record
  case, not a failure case.
- OPEN-QUESTIONS items 3, 8, and the B1-relevant slices of 10 and 11 are
  resolved. Item 11 stays open, narrowed to its B2-only questions.
