# ADR-009: Backend Seam — Request and Result Types

**Status:** Accepted
**Date:** 2026-09-11
**Depends on:** ADR-001 (single-method async `Protocol`), ADR-003 (AFM behavior),
ADR-004 (`FakeBackend`), ADR-007 (budgets, `seed`), ADR-008 (`httpx`)

## Decision

ADR-001 fixed the seam's shape: one async `generate` method. This ADR fixes what
crosses it.

```python
Role = Literal["system", "user", "assistant"]

@dataclass(frozen=True)
class Message:
    role: Role
    content: str

@dataclass(frozen=True)
class GenerationRequest:
    messages: tuple[Message, ...]
    max_completion_tokens: int    # the per-phase budget

@dataclass(frozen=True)
class GenerationResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    finish_reason: str
    latency_ms: int

class Backend(Protocol):
    async def generate(self, request: GenerationRequest) -> GenerationResult: ...

class BackendError(Exception): ...
```

- **Missing usage is an error.** If a server's reply has no token usage, the
  backend raises `BackendError` rather than reporting zeros. A budget checked
  against a made-up zero is an unenforced budget (Hard Rule 5).
- **Every failure is one error type.** Non-2xx responses (including AFM's HTTP 500
  on context overflow), timeouts, connection failures and malformed replies
  (no `choices`, non-string content, no `finish_reason`) all raise `BackendError`.
  No `httpx` type crosses the seam. The message carries the server's own error
  text, since context overflow and genuine server faults differ only by message
  (ADR-003).
- **The backend doesn't judge a reply.** Empty text and a `completion_tokens`
  count over budget are returned as they are. Whether they fail the turn is the
  orchestrator's call: Hard Rules 1 and 5, ADR-003's overshoot question, and
  ADR-005's "what counts as a valid turn".
- **`latency_ms` is measured by our adapter**, as wall-clock time around the
  request, not reported by the server.
- **The `Protocol` is the whole seam.** Construction (`base_url`, `model`, the HTTP
  client) and closing connections stay outside it.
- **The `openai-compatible` adapter sends exactly** `model`, `messages`,
  `max_completion_tokens` and `"stream": false`, per ADR-003.
- **No sampling parameters yet.** `run.yaml` has a run-level `seed` (ADR-007 §5),
  but how it reaches each request is B3's question, because B3's gate is where
  reproducibility gets tested: one value for every turn, or a different one derived
  for each turn. Temperature has no config field at all, so each server's default
  applies until one exists. Adding either is a one-field change to
  `GenerationRequest`.

## Why

- **R0's source returns a bare `str`.** arbgjr's `LLMProviderProtocol` is
  `generate(prompt, *, system_prompt, temperature, max_tokens) -> str`
  (`R0-RESULTS.md`). A string can't carry token usage, so the orchestrator couldn't
  enforce budgets (Hard Rule 5); it could only trust the backend, which is what
  the rule forbids.
- **The rest of the spec already assumes more than a string.** ADR-005 records
  usage, `finish_reason` and latency for every turn, and ADR-004's `FakeBackend`
  reports token usage.
- **Messages, not a prompt plus a system prompt.** Chat roles are what every
  `openai-compatible` server takes. This fixes only the shape; what goes into the
  messages is B2's prompt construction.
- **One request field covers AFM and MLX.** `max_completion_tokens` is the unit
  ADR-003 found honored and ADR-007 adopted. `mlx_lm.server` (0.31.3) reads it
  too, falling back to `max_tokens` only when it's absent (checked in its
  `server.py`). That's what lets B3 use the same adapter for both.
- **Objects rather than keyword arguments.** A later field such as `seed` doesn't
  change the method signature of every backend and fake.

## Consequences

- **Attribution stands.** The single-method async seam is arbgjr's design
  (ADR-001); the types are ours. It's credited in a source comment now, and in
  `NOTICE` at B7.
- **The `FakeBackend` (ADR-004)** returns `GenerationResult` and can raise
  `BackendError`.
- **B2's orchestrator** checks `completion_tokens` against the phase budget after
  every turn (ADR-003, rule 3). This result type is what makes that check
  possible.
- **Ollama's and LM Studio's handling of `max_completion_tokens` is unverified.**
  B3 checks it. The orchestrator's own budget check catches a server that ignores
  it either way.

## Open questions

1. **Seed and temperature pass-through.** Settled in B3, with its reproducibility
   gate.
