# ADR-028: One Public Module, `debatebench.api`, and the CLIs Are Its First Callers

**Status:** Accepted
**Date:** 2026-09-16
**Depends on:** ADR-008 (the layering `__init__.py` protects), ADR-005 (the
transcript's `schema_version`), ADR-009 (the backend seam), ADR-013 (the score
file), ADR-020 (the `judge:` block), ADR-025 (`timeout`), ADR-027 (the event
stream), Hard Rules 4 and 7
**Resolves:** ADR-027's open question — "whether this stream should eventually
be the *only* machine-readable seam … depends on the public-API question
`__init__.py` still leaves open." It is not the only one. See §8.
**Does not amend:** Hard Rule 7, ADR-007's required `output:`. See §5 and §9.

## Context — the library exists, but nothing says which half of it is yours

CLAUDE.md has said from the start that this repo is "the CLI **and library**
only". The library half was never marked. `__init__.py` exports nothing on
purpose, and its docstring says why:

> Submodules are imported explicitly, never from here, so importing the backend
> seam doesn't pull in httpx or PyYAML (ADR-008).

That is a good reason, and `tests/test_layering.py` enforces it across ten
modules. But the effect is that a caller who wants to run a debate in-process
has to reconstruct what `cli.py` does — open a client with the right timeout,
build one `OpenAICompatibleBackend` per side, call `run_debate`, and know that
`orchestrator.BUDGET_TOLERANCE` exists — by reading the CLI's source. Everything
they import is an internal module path with no stability promise, which is the
coupling ADR-027 §"Context" named as the second of two bad options.

ADR-027 fixed the *out-of-process* half: `--events` is a JSONL contract for
another program, so the stderr log stays free to change. It left the in-process
half open, in as many words.

There is a second, sharper reason to do this now. Three harness bugs this
week (`probe/b6/README.md`) came from shell scripts reimplementing what the
tools already do — copying a score file unconditionally, grepping for `"wrote"`
in text that also contains `"failed"`, chaining on a file that was never
written. Every one of them would have been a type error or an exception in
Python. The absence of an API is why those scripts existed.

## Decision

### 1. There is exactly one public module: `debatebench.api`

Everything it exports is the public surface. Everything else —
`debatebench.judging`, `debatebench.orchestrator`, `debatebench.prompts`,
`debatebench.config`, and the rest — is internal and may change in any release
without notice, whatever its name looks like.

The surface is **not** re-exported from `debatebench/__init__.py`, lazily or
otherwise. Two reasons, in order:

- The package root's docstring asserts "submodules are imported explicitly,
  never from here". Root re-exports would make that sentence false. A PEP 562
  `__getattr__` would keep `tests/test_layering.py` green — laziness defeats it
  either way — so the layering test does **not** discriminate between the two
  options, and it should not be cited as though it does.
- `import debatebench.api` telling you it is the API is worth more than the four
  characters it costs, and no-magic matches everything else in this package.

`api.py` is the one module allowed to import both `httpx` and `yaml`, because
composing the tool's two jobs requires both. It is therefore deliberately absent
from `tests/test_layering.py`, with a comment there saying so.

### 2. Two functions, named for the two commands

```python
async def debate(config, *, backends=None, events=None) -> Transcript
async def judge(transcript, *, model, budget, base_url=None, backend=None,
                fact_check=True, timeout=DEFAULT_READ_TIMEOUT) -> ScoreSheet
```

`debate` and `judge` are the commands' names, so the mapping from the
documented CLI to the API needs no documentation of its own.

They are **not** named `run_debate`. `orchestrator.run_debate` already exists
with a different signature — it requires backends and cannot build them, since
ADR-008 forbids the orchestrator importing httpx — and two functions with one
name and different contracts is the kind of drift this project keeps paying for.

### 3. The backend is injectable, and that is half the point

Pass `backends=` (one per side, in side-index order) or `backend=` and the API
makes no HTTP calls at all: anything satisfying ADR-009's `Backend` protocol
works, including the test suite's `FakeBackend`. Omit it and the API opens its
own client, honouring `config.timeout` / the `timeout=` argument (ADR-025), and
closes it before returning.

This is what a caller cannot easily do through the CLI, and it is what makes an
in-process API worth having rather than a `subprocess.run` wrapper.

`Backend` stays a plain `Protocol`, **not** `@runtime_checkable`, so
`isinstance(mine, Backend)` raises `TypeError`. Decorating it was considered and
declined: `runtime_checkable` verifies only that a `generate` attribute exists,
not that it is a coroutine function or takes a `GenerationRequest`, so it would
answer `True` for a synchronous `generate` — the one mistake Hard Rule 4 exists
to catch. A `TypeError` that sends the caller to the type checker is better than
a `True` that sends them into a run. The README says so at the point of use.

### 4. The CLIs call these functions; there is no second composition

`cli._run` and `judge_cli._score` **become** calls to `api.debate` and
`api.judge`. One code path serves both, so the existing suite exercises the API,
and a change to either command cannot silently diverge from what a library
caller gets.

This is a constraint on the design, not a consequence of it: if the API's shape
had forced either command to loosen an error message or drop a check, the seam
would have been in the wrong place and the design would have changed.

### 5. The API returns objects and writes nothing

`debate` returns a `Transcript`; `judge` returns a `ScoreSheet`. Neither writes
a file. Writing is an explicit second call — `write_transcript(transcript, path)`
or `write_scores(sheet, path)`, both exported — and the caller chooses the path.

Hard Rule 7 is untouched. It governs the **`debate` command**: that command
still writes only to `run.yaml`'s `output:`, still has no `--output` flag, and
still keeps its log on stderr. A function that writes nothing cannot mix logging
into a file it never opens.

The consequence is a wart, recorded rather than fixed: **`config.output` is
ignored by `api.debate`**, while ADR-007 still requires the key. A caller who
only wants a `Transcript` object must still put a path in the file. Making
`output:` optional would amend ADR-007's required-field list and needs its own
ADR; it is not worth one yet.

`JudgeConfig` has the same problem twice over — its `output` and `transcript`
fields are meaningless to a function that is handed a `Transcript` and returns a
`ScoreSheet`. That is why `judge` takes explicit keyword arguments rather than
a `JudgeConfig`: passing a struct half of whose fields are silently dead is
worse than unpacking four fields at the call site, which is what `judge_cli`
now does.

### 6. Async only. There is no synchronous wrapper

Callers write `asyncio.run(debate(config))`, which is already one line.

The reason is **not** Hard Rule 4, which forbids a synchronous client *inside*
`async def` and says nothing about a wrapper around it. The reason is that a
sync wrapper raises `RuntimeError` when called from inside a running event
loop — and a live viewer, a dashboard, or a fact-check panel is exactly the
caller most likely to have one, and exactly the caller this API is for. A
convenience that breaks for its primary audience is not a convenience.

### 7. Collisions are renamed, not shadowed

A flat namespace has four genuine collisions. Each gets a distinct public name,
and the internal one keeps its module-local name:

| public name | internal |
|---|---|
| `transcript_json` | `transcript.as_json_dict` |
| `scores_json` | `judging.as_json_dict` |
| `TRANSCRIPT_SCHEMA_VERSION` | `transcript.SCHEMA_VERSION` |
| `SCORE_SCHEMA_VERSION` | `judging.SCORE_SCHEMA_VERSION` |
| `EVENT_SCHEMA_VERSION` | `event_stream.SCHEMA_VERSION` |

`prompts.build_request` and `judging.build_request` collide too; §8 excludes
both, so the collision never reaches the surface.

### 8. What is deliberately outside the surface

- **The prompts** — `prompts.py`, `judging.build_request`,
  `judging.build_fact_check_request`, `judging.render`. Changing prompt text is
  how this project improves: `probe/b6/` is a log of three prompt conditions
  written and reverted in one day. Exporting them would make the next such
  revert a breaking change, and freeze the experiment to protect callers who
  should not be depending on the wording in the first place.
- **`cli.main` and `judge_cli.main`** — argv parsing is not a library interface.
  A caller with an `argv` list wants `subprocess`; a caller in Python wants §2.
- **Retrieval internals, the winner arithmetic (`decide`), `speaking_order`,
  both `BUDGET_TOLERANCE` constants, and anything `_`-prefixed.** All reachable,
  none promised.
- **`load_team`** — `load_run` loads the team files a run names.

`--events` (ADR-027) stays, and is not superseded: it is the *out-of-process*
seam, for a consumer in another language or another process that should not
import Python at all. `api` is the in-process one. `make_event_writer` is
exported so a library caller can write the same JSONL to a stream of its own
choosing, and get one format for both.

### 9. The JSON stays the durable contract; the Python surface is convenience

The transcript (ADR-005), the score file (ADR-013) and the event stream
(ADR-027) each carry a `schema_version`, and those remain what another program
should depend on across versions.

`debatebench.api` is pre-1.0 and may change with a minor version. Every change
to it gets an ADR and a note in the README, the same as any other decision here.
After 1.0 it follows semantic versioning. A caller who needs a promise stronger
than that today should read and write the JSON.

## Why

**Because the composition already exists twice and was about to exist a third
time.** `cli._run` and `judge_cli._score` are eight lines each of exactly what a
library caller needs. The choice was to export them or to let every caller
rewrite them; the harness bugs this week are what rewriting them looks like.

**Because "internal" is not a property of a name.** Without a marked surface,
`from debatebench.judging import score_debate` is indistinguishable, to the
person writing it, from a supported call. Marking one module is the cheapest way
to make the distinction checkable — and to make the *other* modules genuinely
free to change, which is what lets ADR-024 §2's schema question be answered
later without worrying about who imported `Claim`.

**Because the backend seam is the tool's most reusable part and was unreachable.**
ADR-009's `Protocol` means anything with one `async generate` can debate.
Reaching that through the CLI requires a running HTTP server; reaching it through
`api.debate(config, backends=[mine, mine])` requires nothing.

## Consequences

- **A new module, `api.py`, and no behaviour change to either command.** Both
  keep their flags, their stderr text and their exit codes; their internals now
  route through the API. The CLI tests that pin stderr strings are unchanged and
  still pass, which is the check that the seam landed in the right place.
- **`tests/test_layering.py` gains a comment, not a case.** `api` legitimately
  imports httpx and yaml; the comment exists so the omission is not later
  "fixed" by someone adding a case that would fail.
- **The exception surface is six unrelated types** — `ConfigError`,
  `DebateError`, `JudgeError`, `BackendError`, `TranscriptError`,
  `RetrievalError` — with no common base, so a caller wanting "any debatebench
  failure" writes a six-name tuple. Adding a shared base class is
  backwards-compatible and probably right; it touches six modules and is left to
  its own decision (OPEN-QUESTIONS 15).
- **`config.output` is required and ignored** by `api.debate` (§5), and
  `JudgeConfig.output` / `.transcript` are unused by `api.judge`.
- **README grows a section**, and its opening "Two commands" framing gains a
  third bullet. The API is documented where the CLI is, not in a separate file,
  because a reader deciding between them needs both on one page.
- **This does not make the package importable more cheaply.** `import
  debatebench.api` pulls httpx and PyYAML, as it must. Everything ADR-008
  protects is protected by *not* putting this in `__init__.py`.

## Open questions this doesn't resolve

- Whether the six exception types get a common base (OPEN-QUESTIONS 15).
- Whether `RunConfig` should be constructible in code without a YAML file. It is
  a frozen dataclass and nothing stops it, but every ADR-007 validation lives in
  `load_run`, so a hand-built config is unchecked and that is the caller's
  problem. If in-code construction becomes a real use case it needs a validating
  constructor, not a documentation note.
- Whether `api` should expose a fact-check-only entry point. `judge` currently
  does both calls or one; a caller wanting the audit without the rubric has to
  score first. No one has asked.
