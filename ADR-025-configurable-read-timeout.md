# ADR-025: The Read Timeout Is Configurable, and Is Not Part of the Experiment

**Status:** Accepted
**Date:** 2026-09-15
**Depends on:** ADR-008 (`httpx`, and why the 5-second default was replaced),
ADR-007 (`run.yaml` schema), ADR-020 (settings in the file, flags override),
ADR-021 (what `debate` may override, and why), ADR-005 (what the snapshot records)
**Amends:** ADR-021 §1's "nothing else is overridable"

## Context — a fixed ceiling excluded a model from being measured

`openai_compat.py` has always pinned the read timeout at 600 seconds, with the
comment explaining that httpx's 5-second default would kill real turns. It was
right about the default and wrong to assume one replacement value would hold.

Measured 2026-09-15: a `gemma4:12b` fact-check against a transcript carrying prep
evidence, at `--budget 20000`, exceeded 600 seconds on a cold model load and
failed with `ReadTimeout`. Nothing was wrong with the run. The model is a
reasoning model spending thousands of tokens thinking before it answers, the
prompt was large, and the server had just loaded 11 GB of weights.

For a tool whose stated purpose is comparing models, a hardcoded limit that
excludes the slower ones is the same defect as an unenforced budget claim, in the
opposite direction: the harness silently decides what can be measured. It is also
undiscoverable — no flag, no key, no environment variable, and the error names
the symptom rather than the setting.

## Decision

### 1. `timeout` is an optional key, in seconds

In `run.yaml` at the top level, applying to both sides:

```yaml
timeout: 1800        # optional; seconds; default 600
```

And in the `judge:` block, which already carries its own `model`, `base_url` and
`budget` (ADR-020 §1):

```yaml
judge:
  timeout: 1800
```

A positive integer. Validation is the strict loader's usual treatment, and the
error names the key.

### 2. Both commands take `--timeout`, and the flag wins

`debate run.yaml --timeout 1800` and `judge run.yaml --timeout 1800`, following
ADR-020 §4's rule that a flag overrides the file for one run. `judge` already
accepts a bare transcript plus flags, and `--timeout` joins that set.

### 3. It is not per-team

Two sides may point at different servers (B3 ran one debate across two), so a
per-side timeout is arguable. It is not adopted: one generous value covers a
slow side without harming a fast one, since a timeout is a ceiling and not a
wait. If a case appears where one side must fail faster than the other, that is
a new ADR with a reason behind it.

### 4. Only the read timeout moves

`connect`, `write` and `pool` stay at 5 / 30 / 5 seconds. The measured problem
is entirely in waiting for a reply; a connect that takes longer than five
seconds to a local server is a fault, not patience.

### 5. This amends ADR-021 §1, and does not breach its principle

ADR-021 gave `debate` exactly two override flags and said "nothing else is
overridable", listing `output`, `seed`, `base_url`, `topic` and `phases` with a
reason for each. The reason was always the same one: those change *what the
experiment is*. A timeout cannot. It cannot alter a single token of the output —
it decides only whether the output arrives or the run fails. So it sits outside
the category ADR-021 was protecting, and its list is extended rather than its
principle bent.

### 6. It is **not** recorded in the transcript

ADR-005's snapshot records the resolved config, and this is a deliberate
exception. The snapshot exists so a transcript stays interpretable — so a reader
can see what produced these turns. A timeout produced nothing: at 600 seconds and
at 1800 the same run yields the same turns, or yields none at all. Recording it
would add a field to the document, cost a `schema_version` bump, and carry no
information about the debate.

The rule this sets, for the next setting that arrives: **the snapshot records
what shaped the output, not everything that was configured.**

## Why

The alternative was to raise the constant. That fixes one model on one machine
and leaves the next person with the same undiscoverable ceiling — and there is no
value that is right for both a 1.5B model answering in four seconds and a 24B
model thinking for twenty minutes. The default stays 600 so nothing changes for
anyone who never hits it.

## Consequences

- **ADR-021 §1**'s list is extended; its principle is restated in §5 above.
- **ADR-007 §6**: `timeout` joins `run.yaml`'s valid keys and the `judge:`
  block's.
- **`open_client()`** takes the read timeout; it is the only consumer of the
  constant, so nothing else changes.
- **ADR-005 is not amended** — see §6. This is the first setting deliberately
  excluded from the snapshot, and the reason is recorded so the exception does
  not become a precedent for excluding things that *do* shape output.
- **The default is unchanged at 600 seconds**, so no existing config behaves
  differently.

## Open questions this doesn't resolve

- Whether a timeout should be *reported* when it fires with a suggestion — the
  error currently names the symptom (`timed out (ReadTimeout)`) and not the
  setting that would fix it. CLAUDE.md's "a failure must carry what's needed to
  fix it" says it should; that is an implementation detail this ADR does not
  spend itself on.
- Whether `connect`, `write` and `pool` ever need the same treatment. No
  measurement suggests they do.
