# ADR-008: Runtime Baseline — Python 3.11+, httpx, PyYAML

**Status:** Accepted
**Date:** 2026-09-11
**Amended:** 2026-09-11 — the PyYAML consequence was wrong: type-checking alone doesn't
catch YAML 1.1's coercions. Corrected below.
**Depends on:** ADR-001 (dependency scope), ADR-003 (adapter), ADR-004 (tests), ADR-007 (config)
**Resolves:** ADR-003 open question 2 (HTTP client); ADR-004 open question 1
(minimum Python version); the choice of YAML parser

## Decision

- **Python ≥ 3.11** (`requires-python = ">=3.11"`).
- **Two runtime dependencies:**
  - **`httpx`**, the async HTTP client for the `openai-compatible` adapter;
  - **`PyYAML`** for config, with `yaml.safe_load` only.
- **One dev dependency:** `pytest` (ADR-004).

Nothing else is added without an ADR.

The orchestration core — phase loop, event dispatch, backend `Protocol` — imports
neither dependency. `httpx` lives only in the adapter and `PyYAML` only in config
loading. That keeps ADR-001's "zero required dependencies" true for the layer it
was written about.

## Why

- **3.11 gives `asyncio.TaskGroup`**: if any side's task fails, the others are
  cancelled and the error propagates. That's Hard Rule 1 ("every side or the run
  aborts") by construction, the opposite of aragora's `gather(return_exceptions=True)`
  (ADR-001, anti-pattern 1). It also brings `ExceptionGroup` and `tomllib`. The
  dev machine runs 3.14, but a public tool shouldn't require the newest release.
- **`httpx` satisfies Hard Rule 4 natively**, as a real async client rather than
  blocking calls in `asyncio.to_thread`. Its streaming and cancellation are what
  B2 needs if budgets are enforced by cutting a streamed reply (ADR-003 open
  question 1) and for per-turn live events. The dependency-free alternative,
  stdlib `urllib` under `to_thread`, was rejected because mid-reply streaming and
  cancellation are clumsy.
- **`PyYAML` with `safe_load`:** config is only ever read, and `safe_load` never
  constructs arbitrary objects. `ruamel.yaml` was rejected because its strength,
  comment-preserving round-trips, only matters if the tool writes YAML back out.

## Consequences

Two library defaults would silently break B1 unless it handles them. Both were
checked on this machine (httpx 0.28.1, PyYAML 6.0.3):

- **httpx's default timeout is 5 seconds for every operation.** B0 measured 25 s
  to first token for a 4,000-token prompt, and 256-token turns take seconds on
  their own, so the default would kill real turns. The adapter must set explicit
  timeouts: generous or unlimited for reads, short for connecting. A timeout that
  does fire is a failed turn (Hard Rule 1).
- **PyYAML follows YAML 1.1, and type-checking alone doesn't catch its
  coercions.** `safe_load` turns bare `yes`/`no`/`on`/`off` into booleans
  (`model: no` loads as `False`), and a leading zero makes an integer octal
  (`seed: 042` loads as 34). Both slip past a plain type check: 34 is a valid
  `int`, and `budget: yes` loads as `True`, which passes an `int` check because
  `bool` is a subclass of `int`. So B1 must:
  - load config with a stricter loader that treats only `true`/`false` as
    booleans and rejects leading-zero integers, along with YAML 1.1's other
    non-decimal integer forms: hex (`0x1F`), binary (`0b101`), base 60 (`1:30`
    loads as 90) and underscores (`1_000`);
  - reject `bool` wherever an integer is expected;
  - type-check every other field (strings must be strings), rejecting
    mismatches rather than coercing them.

  The loader is B1's to implement. The obvious one-line fix, dropping PyYAML's
  boolean resolver entirely, over-corrects: `true` becomes the string `"true"`.

Also:

- **ADR-003's open question 2 and ADR-004's open question 1 are closed**, pointing
  here.
- **B1 records the baseline in `pyproject.toml`** (`requires-python`, the two
  dependencies, `pytest` as a dev dependency) when it creates the package. B7's
  packaging work builds on that.
