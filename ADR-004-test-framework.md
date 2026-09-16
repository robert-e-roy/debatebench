# ADR-004: Test Framework

**Status:** Accepted (2026-09-11)
**Date:** 2026-09-11
**Amended:** 2026-09-11 — the live AFM tests start `fm serve` themselves
**Depends on:** ADR-001, ADR-002, ADR-003, ADR-007

## Decision

- **pytest** as the test runner, as a dev-only dependency.
- **No async test plugin at first.** Tests drive the orchestrator's single
  coroutine entry point with `asyncio.run(...)`. Add a plugin only when async
  fixtures become unavoidable, and record that choice when it happens.
- **A scripted `FakeBackend`** implementing the backend `Protocol` is the default
  for every test. It returns canned text and reports token usage. It can be told
  to fail, return empty, overshoot a budget, or sleep on a given
  `(phase_index, side_index)`. A plain `python -m pytest` makes no model calls and
  needs no server.
- **Live tests are opt-in behind `DEBATEBENCH_LIVE_TESTS=1`**, following the
  workspace convention (HomesteadAI's `HOMESTEAD_LIVE_TESTS=1`). They hit a real
  `fm serve` (ADR-003) or `mlx_lm.server` and run locally only.
- **The live AFM tests start `fm serve` themselves**, on a free local port, and
  stop it afterwards. That's test setup, not the tool: ADR-003's rule that the
  tool never starts servers still holds. With `DEBATEBENCH_LIVE_TESTS=1` set, a
  missing `/usr/bin/fm` fails those tests rather than skipping them.
- **Layout:** `tests/` at the repo root; hand-written fixtures (`run.yaml`, team
  files, transcripts) under `tests/fixtures/`.
- **CI is deferred to B7.** Hosted CI runners can't be assumed to have Apple
  Intelligence, so live tests stay off CI regardless.

  **Discharged 2026-09-16** (`.github/workflows/tests.yml`), two days after B7,
  because until then there was no remote to run it on. The clause's *reason*
  outlived its deferral and is now the workflow's design: CI never sets
  `DEBATEBENCH_LIVE_TESTS`, so every job runs against the scripted
  `FakeBackend` and the live-model tests skip. A runner has no Apple
  Intelligence, no Ollama and no GPU, and a suite that needed one would be a
  suite nobody could run. It runs pytest on 3.11 and 3.12, the two versions
  `pyproject.toml` classifies, and installs from `uv.lock` with `--locked` so a
  lock that has drifted from `pyproject.toml` fails the job instead of being
  quietly re-resolved into something untested.

## Why

`CLAUDE.md` asks for a reasoned choice, not whatever is most familiar. pytest is
also the most familiar option; it wins here on specifics:

- **B1's exit gate is a table of config cases** (valid, missing team file,
  malformed YAML, missing field). `@pytest.mark.parametrize` expresses that
  directly.
- **Hard Rule 7 needs file and stream capture.** Testing that the `output:`
  path from a test `run.yaml` holds nothing but JSON needs a temporary output
  path and captured stdout/stderr — the
  built-in `tmp_path` and `capfd` fixtures.
- **Contributors expect it.** It's the norm for open-source Python tools, and it
  also runs stdlib `unittest` tests, so nothing is locked out.
- **It doesn't touch ADR-001's dependency rule.** "Zero required dependencies" is
  about what users install; a dev-only test dependency adds nothing to that.

**Alternative considered:** stdlib `unittest` with `IsolatedAsyncioTestCase` —
zero dependencies and built-in async support. Rejected because parametrized case
tables and output-capture fixtures would have to be hand-built, and those are
exactly what the B1 and B3 exit gates need.

**Why no async plugin yet:** the orchestrator exposes one coroutine, so
`asyncio.run` per test is enough. The common async plugins have changed their
configuration defaults across releases, and that churn isn't worth taking on
until async fixtures are actually needed.

## How each hard rule gets a test

B2's exit gate asks that every ADR-001 anti-pattern has a test that would have
caught it. Using the `FakeBackend`:

| Rule | Test |
|---|---|
| 1 — no silent phase failure | The fake raises on one `(phase_index, side_index)`, and separately returns empty text. Assert the run raises and the `output:` path from the test `run.yaml` does not exist. |
| 2 — never key by side alone | Run a phase list with a repeated phase name. Assert every turn is present and none is overwritten. |
| 3 — no blended judge score | Feed the judge malformed or partial dimension output. Assert an error, never a zero. Lands in **B5**, when the judge exists, not B2. |
| 4 — no sync client in `async def` | Run a heartbeat task alongside the orchestrator while the fake awaits `asyncio.sleep`; assert the heartbeat keeps ticking during turns. A deliberately blocking fake (`time.sleep`) should make this test fail. The heartbeat interval and tolerance get picked in B2 so that a short blocking call is reliably caught. |
| 5 — orchestrator-enforced budgets | Scoped to `budget` (the per-phase cap) only — the fake reports `completion_tokens` over the phase budget on a single turn. Assert the orchestrator catches it. Exact behavior depends on ADR-003's overshoot question. **`prep_budget` (ADR-007) is deliberately not covered here**: it's a pool spent across however many internal calls Prep's retrieval logic makes, which isn't testable until B4 decides that mechanism. Its enforcement test belongs to B4/B6, not this table — see OPEN-QUESTIONS. |
| 6 — phases are data | Run the same orchestrator over two different phase lists. Assert each transcript follows its list exactly. |
| 7 — output-file discipline | Run with a test `run.yaml` whose `output:` points into `tmp_path`. Assert the file parses as JSON and all logging went to stderr (`capfd`). |

## Consequences

- B1 can start once this is accepted. Until then, `CLAUDE.md` still forbids test
  infrastructure.
- The `FakeBackend` becomes a maintained test utility that has to track both the
  backend `Protocol` and the transcript format (ADR-005).
- `python -m pytest` stays fast and deterministic. Real-model behavior is covered
  only by the opt-in live suite and the B0 hardware probe.

## Open questions

1. **Minimum Python version — resolved by ADR-008:** 3.11.
2. **Coverage tooling.** None proposed; add it once there's code worth measuring.
