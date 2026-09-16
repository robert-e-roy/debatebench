# ADR-027: `--events` Streams JSONL on stdout, as a Contract for Other Programs

**Status:** Accepted
**Date:** 2026-09-15
**Depends on:** ADR-001 (the `events.py` shape, a design lift), ADR-005 (the
transcript and its `schema_version`), ADR-002 ("CLI shape"), ADR-014 §2 (prep
privacy), Hard Rule 7
**Does not amend:** Hard Rule 7. See §6.

## Context — the only live view of a run is prose meant for a human

`debate` reports progress per turn on **stderr**, through the typed event bus
`events.py` calls "the seam a live dashboard or fact-check panel attaches to".
The transcript, by contrast, is written once at the end and atomically, because
Hard Rule 1 requires that a failed run leave no file.

So a program that wants to watch a run as it happens has two options today, and
both are bad. It can scrape stderr — a format with no stability promise, which
changed on 2026-09-14 when `9cb8aa2` added `(pro)`/`(con)` labels to the exact
line such a scraper would parse. Or it can import `debatebench` and subscribe to
the bus, which works but couples it to internal module paths that
`__init__.py` deliberately does not export.

`debate` writes **nothing at all to stdout**. That stream is free, and it is the
natural place for output meant for a program rather than a person.

## Decision

### 1. `debate --events` writes one JSON object per line to stdout

Off by default; nothing changes for anyone who does not pass it. It does not
suppress or alter the stderr log, which stays the human view. The two streams
carry the same events for different readers.

```bash
debate run.yaml --events | my-viewer
debate run.yaml --events > events.jsonl 2> run.log
```

### 2. Each line is flushed as it is written

Non-negotiable, and the thing most likely to be got wrong. Python block-buffers
stdout when it is a pipe rather than a terminal, so an unflushed stream delivers
nothing until several kilobytes have accumulated — which for a debate is most of
the run. A stream that arrives at the end is the transcript, which already
exists. **Every line is flushed before the next model call begins.**

### 3. The first line describes the run; the rest are events

The bus's `RUN_STARTED` carries no payload — every field is `None` — so a
consumer subscribing to it alone cannot render a heading until the first turn
lands. Rather than change the event dataclass, which other consumers share, the
**writer emits a `run` line first**, built from the resolved config:

```jsonc
{"event":"run","schema_version":1,"topic":"…","seed":864296665,
 "phases":["opening","rebuttal","conclusion"],
 "sides":[{"side_index":0,"side":"pro","team":"Social Democrat","model":"qwen3:8b"},
          {"side_index":1,"side":"con","team":"Tea Party Constitutionalist","model":"qwen3:8b"}]}
```

Then one line per event, each naming its side by **label as well as index**, so
a reader never has to hold the mapping:

```jsonc
{"event":"phase_started","phase_index":0,"phase":"opening"}
{"event":"turn_started","phase_index":0,"phase":"opening","side_index":0,"side":"pro"}
{"event":"turn_completed","phase_index":0,"phase":"opening","side_index":0,"side":"pro",
 "order":0,"text":"…","length":"medium","budget":2000,"hit_budget":false,
 "usage":{"prompt_tokens":106,"completion_tokens":378},"latency_ms":14064}
{"event":"phase_completed","phase_index":0,"phase":"opening"}
{"event":"run_completed","turns":6}
```

A failed run ends with `{"event":"run_failed","error":"…"}` and **no more lines**.

### 4. `schema_version` is on the `run` line, and this is version 1

A consumer reads line one and knows what it is reading. It is not repeated per
line: this is a pipe from a process the consumer started, so line one cannot be
missed, and repeating it on every line would be noise for the one case that
cannot happen.

The version moves independently of ADR-005's transcript version. They describe
different documents and there is no reason to couple them.

### 5. `turn_completed` carries the turn's text, and prep turns carry evidence

A live view needs the speech before the file exists, so the text is in the
stream. Prep turns carry their `evidence` for the same reason.

**A consumer of this stream sees both sides' evidence, which neither debater
does.** That is not a breach of ADR-014 §2 — prep privacy is about what reaches
a *model*, and the transcript has always recorded both sides for the judge to
read — but it is a property worth stating, because a viewer that renders the
stream naively will show each side the other's research.

### 6. This does not touch Hard Rule 7, and the stream is not a transcript

The transcript still goes only to `run.yaml`'s `output:` path, written once,
atomically, and never on a failed run. The event stream is a different thing on
a different channel, and it has none of the transcript's guarantees: it is not
rotated, not atomic, and **a failed run leaves a partial stream describing turns
that were never written anywhere**.

So a consumer must not reconstruct a transcript from the stream and treat it as
one. If it wants the durable record it reads `output:` after `run_completed` —
and it must wait for that line, because on failure the file it would otherwise
find is the *previous* run's.

That last point is not hypothetical. On 2026-09-15 a measurement harness assumed
a failed debate would leave no readable transcript, judged the stale file left by
the run before it, and produced a result that looked valid — caught only because
two artifacts shared a seed. A second program consuming this stream is in exactly
that position, and `run_completed` is what tells it the file is real.

### 7. `judge` does not get this

`judge` has no event bus and no loop to report from — it is one or two model
calls and a result. Adding a stream there would mean inventing events for
something that has none, for a command whose whole output is already a file.

## Why

The choice was between blessing stderr's format as an interface and giving
programs their own channel. Blessing stderr would freeze a message that exists
to be read aloud to a human — it has already been improved twice for
readability, and both changes would have been breaking.

stdout was free precisely because Hard Rule 7 pushed the transcript into a named
file rather than a redirect. That rule was written against a different problem
and left exactly the right gap.

## Consequences

- **`debate` gains one flag.** No behaviour changes without it.
- **`events.py` is unchanged.** The enrichment in §3 lives in the writer, so the
  bus stays the shape ADR-001 lifted and every consumer sees the same events.
- **A second project can depend on this** without importing `debatebench`, and
  without the coupling `__init__.py` deliberately avoids.
- **The stderr log stays free to change**, which is the point.
- **ADR-021's override list is not touched**: `--events` changes nothing about
  what runs, only what is reported, so it is outside that ADR's category in the
  same way ADR-025 §5 argued for `--timeout`.

## Open questions this doesn't resolve

- Whether the per-turn `text` should be omitted behind a flag for a consumer
  that only wants timings. No measurement suggests the volume is a problem.
- Whether a future `judge` stream is worth inventing events for, if per-claim
  fact-check progress ever becomes visible mid-call.
- ~~Whether this stream should eventually be the *only* machine-readable seam,
  with the internal bus kept private. That depends on the public-API question
  `__init__.py` still leaves open.~~ **Answered by ADR-028 (2026-09-16): it is
  not.** `debatebench.api` exports `EventBus`, `DebateEvent` and `EventType`, so
  an in-process consumer subscribes directly and an out-of-process one reads this
  stream. `make_event_writer` is exported too, so a library caller can produce
  exactly this format on a stream of its own choosing — one format, two seams.
