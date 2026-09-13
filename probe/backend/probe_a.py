"""BACKEND-PROBE.md Part A — API compatibility, one server per invocation.

Usage:  probe_a.py <base_url> <model> <label> [row ...]
        probe_a.py http://127.0.0.1:8082/v1 mlx-community/Qwen3-8B-4bit vllm-mlx
        probe_a.py http://127.0.0.1:8081/v1 <model> mlx_lm A2 A3 A5

Results are written to probe/backend/probe-a-<label>.json beside this file, so
a row is recorded as data rather than as terminal scrollback. A row that could
not be run is recorded too — the probe doc counts that as a finding, not a skip.

Two defects found while running session 1 are fixed here, and both mattered:

* **A1 needs a prompt that actually binds.** "Name three colours" answers in
  6-7 tokens, so a 20-token cap never applies and every server looks compliant.
  The prompt below asks for 400 words.
* **When content extraction fails, record the raw message.** The first version
  fell back to ``str(payload)`` and logged a repr of the response envelope,
  which is why mlx_lm's A2/A3/A5 had to be thrown away rather than read.

Standard library plus httpx, which the package already depends on (ADR-008).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).parent
TIMEOUT = httpx.Timeout(connect=5.0, read=300.0, write=60.0, pool=5.0)

# Long enough that a 20-token cap is visible in the token count (see A1 above).
BINDING = [{"role": "user", "content": "Write a detailed 400 word essay about the history of rain measurement."}]
SHORT = [{"role": "user", "content": "Name three colours."}]

# Rows that need an *answer* back (A2, A3, A5, A9) must leave room for a
# reasoning model to think first. Session 1 gave them 60-120 tokens, and Qwen3
# through mlx_lm spent the lot thinking: the message came back with a
# `reasoning` key and no `content` at all, which looked like a parsing bug and
# was really budget starvation — the same trap the judge hit before its budget
# went to 6000 (OPEN-QUESTIONS 13).
REASONING_BUDGET = 2000


def post(client: httpx.Client, url: str, body: dict, read: float | None = None):
    started = time.monotonic()
    try:
        response = client.post(url, json=body, timeout=read and httpx.Timeout(
            connect=5.0, read=read, write=60.0, pool=5.0))
    except httpx.TimeoutException as e:
        return None, f"TIMEOUT after {read or 300}s ({type(e).__name__})", 0
    except httpx.HTTPError as e:
        return None, f"TRANSPORT {type(e).__name__}: {e}", 0
    elapsed = round((time.monotonic() - started) * 1000)
    try:
        return response.status_code, response.json(), elapsed
    except ValueError:
        return response.status_code, response.text[:400], elapsed


def message_of(payload) -> dict:
    try:
        return payload["choices"][0]["message"]
    except Exception:
        return {}


def content_of(payload):
    """The reply text, or (None, the raw message) so a failure is evidence."""
    message = message_of(payload)
    text = message.get("content") if isinstance(message, dict) else None
    return (text, None) if isinstance(text, str) else (None, message or payload)


def usage_of(payload) -> dict:
    return payload.get("usage") or {} if isinstance(payload, dict) else {}


def parses_as_json(text) -> bool:
    if not isinstance(text, str):
        return False
    try:
        json.loads(text.strip())
        return True
    except ValueError:
        return False


def run(base_url: str, model: str, label: str, wanted: set[str]) -> dict:
    url = base_url.rstrip("/") + "/chat/completions"
    out = HERE / f"probe-a-{label}.json"
    found: dict[str, dict] = {}

    def save() -> None:
        """Persist after every row. A8 can wedge a server or be killed, and a run
        that dies mid-row must not take the rows that already succeeded with it —
        which is exactly how session 1 lost mlx_lm's file."""
        out.write_text(json.dumps({"label": label, "base_url": base_url, "model": model,
                                   "rows": found}, indent=2, default=str))

    with httpx.Client(timeout=TIMEOUT) as client:
        def record(row: str, **facts):
            found[row] = facts
            save()
            print(f"  {row}: {json.dumps(facts, default=str)[:320]}", flush=True)

        def finish_reason_of(payload):
            try:
                return payload["choices"][0].get("finish_reason")
            except Exception:
                return None

        if "A1" in wanted:
            # Not named `out`: that shadows the results Path that save() closes
            # over, and every row then fails with dict.write_text.
            fields = {}
            for field in ("max_tokens", "max_completion_tokens"):
                status, payload, _ = post(client, url, {
                    "model": model, "messages": BINDING, "stream": False, field: 20})
                fields[field] = {"status": status,
                                 "completion_tokens": usage_of(payload).get("completion_tokens"),
                                 "finish_reason": finish_reason_of(payload)}
            record("A1", **fields)

        if "A2" in wanted:
            status, payload, _ = post(client, url, {
                "model": model, "stream": False, "max_tokens": REASONING_BUDGET,
                # The prompt must NOT ask for JSON, or a model emits it regardless and
                # the row says nothing about whether response_format was honoured.
                # Session 1 asked "Reply with a JSON object mapping 'answer' to 4" and
                # recorded a pass for all three servers on that confounded evidence.
                "messages": [{"role": "user", "content": "What is two plus two?"}],
                "response_format": {"type": "json_object"}})
            text, raw = content_of(payload)
            record("A2", status=status, content_parses_as_json=parses_as_json(text),
                   sample=(text or "")[:160], raw_message_when_no_content=str(raw)[:200] if raw else None)

        if "A3" in wanted:
            schema = {"type": "object", "properties": {"answer": {"type": "integer"}},
                      "required": ["answer"], "additionalProperties": False}
            status, payload, _ = post(client, url, {
                "model": model, "stream": False, "max_tokens": REASONING_BUDGET,
                "messages": [{"role": "user", "content": "What is two plus two?"}],
                "response_format": {"type": "json_schema",
                                    "json_schema": {"name": "answer", "schema": schema, "strict": True}}})
            text, raw = content_of(payload)
            conforms = False
            if parses_as_json(text):
                conforms = set(json.loads(text.strip())) == {"answer"}
            record("A3", status=status, conforms_to_schema=conforms,
                   sample=(text or "")[:160], raw_message_when_no_content=str(raw)[:200] if raw else None)

        if "A4" in wanted:
            status, payload, _ = post(client, url, {
                "model": model, "messages": SHORT, "max_tokens": 20, "stream": False})
            record("A4", status=status, single_json_object=isinstance(payload, dict),
                   has_choices=isinstance(payload, dict) and "choices" in payload)

        if "A5" in wanted:
            body = {"model": model, "stream": False, "max_tokens": REASONING_BUDGET,
                    "temperature": 0, "seed": 42, "messages": SHORT}
            _, first, _ = post(client, url, dict(body))
            _, second, _ = post(client, url, dict(body))
            a, raw_a = content_of(first)
            b, _ = content_of(second)
            record("A5", identical=(a == b and a is not None),
                   first=(a or "")[:80], second=(b or "")[:80],
                   raw_message_when_no_content=str(raw_a)[:200] if raw_a else None)

        if "A6" in wanted:
            status, payload, _ = post(client, url, {
                "model": model, "messages": SHORT, "max_tokens": 30, "stream": False})
            usage = usage_of(payload)
            record("A6", status=status, usage_keys=sorted(usage),
                   prompt_tokens=usage.get("prompt_tokens"),
                   completion_tokens=usage.get("completion_tokens"))

        if "A7" in wanted:
            status, payload, _ = post(client, url, {
                "model": model, "stream": False, "max_tokens": 10, "messages": BINDING})
            record("A7", status=status, finish_reason=finish_reason_of(payload),
                   completion_tokens=usage_of(payload).get("completion_tokens"))

        if "A8" in wanted:
            # Sized to *exceed* the window, not to dwarf it. Qwen3-8B's context is
            # ~32k tokens; 2,800 repetitions is ~28k words, roughly 37k tokens, so
            # the row still asks "what happens past the limit" while the KV cache
            # stays a few GB. Session 1 sent 12,000 repetitions (~160k tokens, 5x
            # the window): it wedged vllm-mlx for ~20 minutes, drove mlx_lm to
            # 23 GB, and ended in a Metal OOM on the host. Still run this row last.
            filler = "The council reviewed the transit budget and scheduled a vote. " * 2800
            status, payload, _ = post(client, url, {
                "model": model, "stream": False, "max_tokens": 16,
                "messages": [{"role": "user", "content": filler}]}, read=180.0)
            body = payload if isinstance(payload, str) else json.dumps(payload, default=str)[:300]
            record("A8", status=status, body=body[:300], approx_prompt_words=len(filler.split()))

        if "A9" in wanted:
            status, payload, _ = post(client, url, {
                "model": model, "stream": False, "max_tokens": REASONING_BUDGET,
                "messages": [{"role": "user", "content": "Think step by step: what is 17 times 23?"}]})
            message = message_of(payload)
            text, _ = content_of(payload)
            record("A9", status=status,
                   message_keys=sorted(k for k in message if k != "role"),
                   separate_reasoning_field=any(k in message for k in ("reasoning", "reasoning_content")),
                   think_tag_in_content=isinstance(text, str) and "<think" in text,
                   content_sample=(text or "")[:120])

    save()
    print(f"  -> {out}")
    return found


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        raise SystemExit(2)
    rows = set(sys.argv[4:]) or {f"A{n}" for n in range(1, 10)}
    print(f"== Part A: {sys.argv[3]} ({sys.argv[2]}) ==", flush=True)
    run(sys.argv[1], sys.argv[2], sys.argv[3], rows)
