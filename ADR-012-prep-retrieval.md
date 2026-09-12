# ADR-012: Prep Retrieval Mechanism — Query Formation, Method, and What `prep_budget` Buys

**Status:** Accepted
**Date:** 2026-09-12
**Amended:** 2026-09-12 — corrected a real error (§1/§2 matched on `stance`,
which ADR-007 §7 explicitly says is not a position on the motion; `side` is
the field that actually distinguishes the two sides) and a real gap (a
team's `corpus:` is an unlabeled local directory and cannot be searched by
the same metadata match as `sources:`); resolved the dependency/offline
contradiction in the original §5 by moving dataset acquisition out of
debatebench's runtime entirely. Caught in review before any code was written
against the original version — see "What changed" below.
**Depends on:** ADR-002 ("Phase structure", "Data sourcing"), ADR-003
("Manual setup" precedent), ADR-005 (transcript `evidence` field), ADR-007
("sources vs corpus" schema §3, §7 `side`/`stance` distinction, budgets §2),
ADR-008 (fixed at exactly two runtime dependencies: `httpx`, PyYAML),
ADR-009 (backend request/result types — no tool-calling surface), ADR-010
(prep currently fails loudly with no model call), ADR-011 (`length`
explicitly excludes prep)
**Resolves:** OPEN-QUESTIONS.md item 10
**Supersedes:** an earlier draft of this decision made under the label
"ADR-008", never reconciled with the canonical ADR-008 and never took effect.

## What changed in the amendment

- Query formation and the shared-pool filter now match on **`side`** (`pro`/
  `con`), not `stance`. `stance` is a team file's persona label (ADR-007 §7:
  "not a position on the motion") and would exact-match nothing in a
  side-labeled corpus.
- A team's own `corpus:` gets a **separate, genuinely different retrieval
  method** (topic-keyword only, no side filter), not the shared pool's
  method applied to a different location.
- Dataset acquisition (`args-me`, `debatesum`) is now a **one-time, manual,
  out-of-band step**, not something debatebench fetches at runtime. This
  removes both the third-dependency problem (ADR-008 fixes exactly two) and
  the direct contradiction with `HF_HUB_OFFLINE=1` (ADR-002) that "fetched by
  the tool at run time" created.

## Decision

### 1. Query formation — orchestrator-driven, keyed on `side`, not `stance`

The orchestrator forms each side's shared-pool query deterministically from
`topic` + that side's **`side`** (`pro` or `con`, ADR-007 §7). No model call
forms the query — ADR-009 fixed `GenerationRequest`/`GenerationResult` with
no tool-calling surface, so a query-forming model turn isn't just undesigned,
it isn't representable in the current seam without a new ADR.

A team's `stance` (persona identity, e.g. `liberal`) plays no role in
retrieval. It's who the side is; `side` is what it's arguing.

### 2. Two retrieval methods, not one, for the two pool types

- **Shared `sources:` pool** (`args-me`, `debatesum`): metadata filtering.
  Match on `topic` (keyword/fuzzy) **and `side` (exact: `pro` or `con`)**,
  return the top 10 passages. This pool holds both sides' material mixed
  together, so it needs both filters — this is what makes two sides querying
  one pool retrieve different, side-aligned evidence.
- **Team's own `corpus:`** (a local directory, no metadata at all): keyword
  search only, matched against `topic`, no side filter. Everything in a
  team's own corpus already belongs to that side by construction, there's no
  opposing-side content in there to exclude. Top 10 passages from this pool
  too, when `corpus` is present.
- **Combined:** up to 10 (shared) + 10 (own corpus, if present) = up to 20
  raw passages recorded per side, per ADR-007 §3's "layered on top of, not a
  replacement for."

No embeddings, no external search dependency, for either method.

### 3. What `prep_budget` is spent on — one model call, not retrieval itself

Unchanged from the original decision: retrieval (steps 1–2) is free,
deterministic, no generation, no budget consumed. `prep_budget` caps exactly
one model call per side that synthesizes its retrieved passages into prep
notes, enforced by the orchestrator like any other phase (Hard Rule 5,
ADR-010 §3's overshoot tolerance). `length` (ADR-011) doesn't apply to prep.

### 4. Transcript recording — unchanged, plus one clarification

The Prep turn's `evidence: [...]` holds the raw retrieved passages,
untouched, each with `id`, `source`, `text` (ADR-005). The synthesis call's
output is that turn's ordinary `text` field. **A Prep turn's `budget` field
holds `prep_budget`'s value, not `budget`'s** — ADR-005's schema is generic
across phases and doesn't state this mapping explicitly; it needs to.

### 5. Dataset acquisition is a one-time manual step, not runtime code

**debatebench never fetches `args-me` or `debatesum` over the network.**
Both must already exist locally, as JSONL files, before `debate` runs —
the same category of prerequisite as "`fm serve` must already be running"
(ADR-003, "Manual setup"). Concretely:

- debatebench looks for `~/.cache/debatebench/sources/<name>.jsonl`
  (`args-me.jsonl`, `debatesum.jsonl`). Missing file at Prep time is a clear,
  named error: which file, which dataset, and that it must be downloaded
  first — the same shape as ADR-007 §6's "a team file that doesn't exist is
  an error."
- Each line is one JSON object with the fields retrieval needs: `id`, `text`,
  `topic` (or the dataset's nearest equivalent, e.g. args-me's conclusion),
  `side` (normalized to `pro`/`con` from whatever the source dataset calls
  its own stance/orientation label), `source`.
- **Producing that JSONL from each dataset's native form is an out-of-band
  setup concern**, documented, not shipped. A person (or a separate,
  undocumented-here helper script) may use the Hugging Face `datasets`
  library, `pandas`, or anything else to do this conversion once, offline.
  None of that is a debatebench runtime dependency — ADR-008's two
  (`httpx`, PyYAML) are unaffected. This also means the offline requirement
  (ADR-002) is trivially satisfied: debatebench makes zero network calls for
  `sources`, so there's nothing for `HF_HUB_OFFLINE=1` to even apply to on
  this path.
- **Follow-up needed in shipped code:** B1's `sources` validation currently
  keeps `sources` as written without checking it against an allow-list
  (flagged during review as `config.py:111`). That needs a small edit,
  validating against `{args-me, debatesum}`, the same retroactive-fix
  pattern ADR-011 already used against finished B2 work.

### 6. Licensing

- `Hellisotherpeople/DebateSum` — MIT, confirmed via Hugging Face's own
  license field and independently via a third-party paper citing it as MIT.
- `webis/args_me` — CC-BY-4.0 per Webis's Zenodo release, which states
  verbatim: **"Individual rights to the content still apply."** Built by
  crawling four debate portals, including Debatewise, which ADR-002's "Data
  sourcing" names as an example not to scrape directly. Using the
  already-published, already-relicensed Webis corpus is a different act
  from debatebench scraping Debatewise itself, but that difference needs
  stating, not assuming: **`args-me` is retrieval-only and never bundled or
  redistributed as part of the debatebench repo or package**, the same
  posture already applied to `tasksource/logical-fallacy` in ADR-002.

  These findings came from real web searches performed while drafting this
  ADR (Webis's Zenodo page and Hugging Face's dataset pages directly), not
  reconstructed from memory. Worth an independent recheck given how
  load-bearing licensing is here, the same standard already applied to every
  other dataset in this project — but they weren't unverified guesses.

## Why

Query formation and both retrieval methods resolve to "keep it simple,
orchestrator-driven, no new dependency" — the same instinct already
governing ADR-001, ADR-007, and ADR-009's closed request/result shape. Using
`side` rather than `stance` isn't a stylistic choice, it's the one that
actually works against a side-labeled corpus, and reusing `stance` would
have reintroduced the exact confusion ADR-007 §7 was written to fix. Moving
dataset acquisition out of debatebench's runtime resolves two independent
contradictions with one change: it respects ADR-008's fixed dependency count,
and it makes the offline requirement automatically true rather than
something "fetched at run time" has to somehow honor.

## Consequences

- **B4's scope is fully specified**: two retrieval methods (shared pool:
  topic+side; own corpus: topic only), the one `prep_budget`-capped synthesis
  call, `evidence` + `text` on the Prep turn with `budget` mapped to
  `prep_budget`, and reading pre-existing local JSONL files rather than
  fetching anything.
- **B1's config validation** (ADR-007 §6) gains a concrete case: a `sources`
  entry not in `{args-me, debatesum}` is an error. This needs applying to
  already-shipped B1 code, not just documented here.
- **Setup documentation** (README, B7) needs to state the one-time JSONL
  preparation step and where debatebench expects the files, since nothing in
  `debate` itself will create them.
- OPEN-QUESTIONS item 10 is resolved.

## Open questions this doesn't resolve

- Whether "top 10" (per pool) is actually a good number — untested.
- Whether live retrieval is ever added alongside static corpora — deferred to
  B4's own judgment call; any live source still has to clear the licensing
  gate and, per this amendment, would need its own justification for
  re-introducing a runtime network dependency ADR-008 doesn't currently
  allow.

