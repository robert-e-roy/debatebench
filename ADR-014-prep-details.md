# ADR-014: Prep Details — Corpus Format, Prep Privacy, and What an Empty Retrieval Means

**Status:** Accepted
**Date:** 2026-09-12
**Depends on:** ADR-005 (transcript `evidence`, `order`), ADR-007 (§3 `sources`
vs `corpus`, §6 validation), ADR-008 (two runtime dependencies), ADR-010 (§1
speaking order), ADR-011 (`length` excludes prep), ADR-012 (the retrieval
mechanism this fills in)
**Resolves:** the gaps B4 hit on contact with ADR-012 — none of these were
decided anywhere, and each one changes the code.

## Decision

### 1. A team's `corpus:` is a JSONL file, in the shared pool's row shape

`corpus:` names a JSONL file, not a directory:

```yaml
corpus: liberal-climate-corpus.jsonl
```

Each line is one JSON object with the same fields a shared-pool row has —
`id`, `text`, `topic`, `source` — **minus `side`**, which a team's own corpus
doesn't carry: everything in it belongs to that side by construction, which
is exactly why ADR-012 §2 gives it a different retrieval method. One row
shape means one parser and one passage type; the only difference between the
two pools stays the side filter, as ADR-012 §2 says it should be.

**It resolves relative to the team file's own directory**, the way `team:`
already resolves from `run.yaml`'s (ADR-007 §6). A team file is durable and
reused across runs (ADR-006), so its corpus travels with it, not with
whichever `run.yaml` happens to reference it that day.

ADR-007 §6's "`sources` and `corpus` are kept exactly as written" still holds
for what the **transcript records** — the snapshot keeps the string as
authored — but the value is now also resolved to a real path at load time,
because B4 reads it. The alternative considered was a directory of `.txt`/
`.md` files, one passage per file; it was rejected because it needs a second
parser, a chunking rule for long files, and a decision about which extensions
count, all to express the same thing JSONL already expresses.

### 2. A side never sees the opponent's prep

Prep notes are **private to the side that wrote them**. A side's own prep turn
appears in its own later prompts; the opponent's prep turn is never rendered
to it. Real debate prep is private, and showing it would let each side
pre-empt arguments its opponent never chose to reveal — which would make
`rebuttal` measure something other than what it claims to.

Both prep turns are still **recorded in full in the transcript**, which is
what the judge and the fact-checker read. Privacy is a property of the
prompts, not of the record.

**Raw evidence passages never go into any prompt.** The side's one synthesis
call sees them (that is the call's entire job); after that, only its own prep
*notes* travel forward. The passages stay in the transcript for traceability,
which is what ADR-012 §4 records them for.

Consequence: `render_debate` now takes the viewing side, required rather than
defaulted — a default is precisely how the opponent's prep would leak back in
later.

### 3. `order` is 0 for both sides on a prep turn

ADR-005 defines `order` as who spoke first within the phase. Nothing is
sequential about prep: each side retrieves from the pools independently and
synthesizes its own notes, and neither one's prep depends on the other's.
Numbering them 0 and 1 would put an ordering in the transcript that doesn't
exist and that a reader would reasonably believe. **Both prep turns carry
`order: 0`**, and a reader should take that as "no order," not as a tie.

Speaking order in the argument phases is unaffected: ADR-010 §1 already
counts only non-prep phases, so pro still opens the first argument phase
however many prep phases precede it.

### 4. Zero passages fails the run — counted after both pools, not before

A prep turn that retrieved nothing would put a model's ungrounded invention
into the `evidence` slot's place, which is the silent degradation Hard Rule 1
exists to prevent. So **a side that retrieves zero passages fails the run**,
with an error naming the side and what it searched.

The count is taken **after both pools have been searched**, never after the
shared pool alone. ADR-007 §3 makes `corpus:` an additional layer rather than
a requirement, and the same holds in reverse: a side whose shared-pool query
matches nothing but whose own corpus matches is properly prepared, and a run
with no `sources:` at all but a corpus on each team is a legitimate
configuration. Only "nothing from anywhere" is the failure.

### 5. Source files live in one directory, overridable by environment

ADR-012 §5 fixes the location as `~/.cache/debatebench/sources/<name>.jsonl`.
**`DEBATEBENCH_SOURCES_DIR` overrides that directory** when set.

This is a new user-facing surface, so it is stated here rather than left in
the code as an unannounced default. It exists because the tests need real
JSONL on disk without writing into the developer's home directory, and it
mirrors `DEBATEBENCH_LIVE_TESTS` (ADR-004), the one environment variable this
project already has. It reads a location only — it never changes which source
names are allowed (ADR-012 §5's allow-list still governs that) and it never
causes a download, because nothing in `debate` downloads anything.

### 6. `evidence` appears only on prep turns

The transcript's turn objects carry an `evidence` key **only where it means
something**, which is prep. An opening turn has no `evidence` key at all,
rather than an empty list that a reader might mistake for "prepared and found
nothing." This matches how ADR-005 documents it (`a prep turn also carries
evidence`) and needs no `schema_version` bump, since ADR-005 called the item
shape provisional until B4 and this is B4 fixing it at `id`, `source`, `text`.

## Why

Every decision here is one ADR-012 implies but doesn't state, and each one had
a plausible-looking wrong answer sitting next to it: a corpus directory that
needs its own parser, prep notes visible to both sides, an invented speaking
order on a phase that has none, a zero-result check placed one pool too early,
an environment variable introduced silently, and an empty `evidence: []` on
every turn that never had any. They are recorded together because they were
found together, in the hour between "start B4" and the first line of B4's code.

## Consequences

- **`config.py` resolves `corpus`** to a path while keeping the authored string
  for the snapshot, and validates `sources` against ADR-012 §5's allow-list —
  both edits to already-shipped B1 code.
- **`render_debate`'s signature changes** to require the viewing side; every
  call site and its tests change with it.
- **The fixture team file changes** from `corpus: sources/liberal-climate-corpus/`
  to a JSONL file beside it.
- **B7's setup documentation** gains `DEBATEBENCH_SOURCES_DIR` alongside the
  one-time JSONL preparation step ADR-012 §5 already requires it to describe.

## Open questions this doesn't resolve

- Whether "top 10 per pool" is a good number — still untested, as ADR-012 said.
- How a passage's `topic` is matched (keyword scoring) is an implementation
  detail of B4, deliberately not frozen here: it must be deterministic, and
  it must be documented where it lives, but it is expected to be tuned once
  there is real retrieval output to judge it by.
