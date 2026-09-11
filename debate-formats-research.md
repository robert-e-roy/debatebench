# Real Debate Formats — Research for debatebench's Phase Design

*All formats below fall under the umbrella term "competitive debate" (or
"competitive speech and debate") — the term to search if more format detail
is needed later; it surfaces tournament rule sets rather than general-audience
explainers.*

*Corrected 2026-09-11: prep-time, cross-examination, speech-time and
team-structure details checked against NSDA and tournament rules. Sources are
listed at the end.*

## Summary table

| Format | Sides | Topic scope | Structure | Prep time | Notable mechanic |
|---|---|---|---|---|---|
| **Presidential (US, e.g. ABC, Sept 2024)** | 2, solo | Multiple topics per debate, moderator-selected | Per topic: question → 2min response → 2min rebuttal → 1min follow-up; no opening statement (recent cycles), one closing statement each at the end | None during the debate — candidates prepare in advance, not live | Moderator picks and sequences topics live; strict equal time per turn, enforced by visual cues |
| **Lincoln-Douglas (LD)** | 2, solo | One resolution, fixed for ~2 months of competition | 5 speeches + 2 cross-examination periods; Affirmative gets more speeches than Negative but **equal total speaking time** (13 min each) | Extensive research before the round, **plus a 4–5 minute in-round prep pool** (NSDA standard: 4) each debater spends between speeches as they choose | Values/philosophy-focused, not policy-focused |
| **Policy / CX (NDT/CEDA)** | 2 teams of 2 | One resolution, policy-oriented | 8 speeches: 4 constructives, each followed by a 3-minute cross-examination, then 4 rebuttals with no cross-examination | Extensive pre-round research (this is where "evidence caches" like DebateSum's source data come from), **plus an in-round prep pool** (8 minutes per team under NSDA rules) | Dense, evidence-heavy, high speaking speed — built for judges who value depth over accessibility |
| **Public Forum (PF)** | 2 teams of 2 | One resolution, current-events focused | Shorter speeches (constructive 4 min, rebuttal 4, summary 3, final focus 2), "crossfire" Q&A periods | Less pre-round research than Policy/LD, **plus a 3-minute in-round prep pool** per team | Explicitly designed as the accessible/broadcast-friendly reaction to Policy and LD's technical density |
| **Parliamentary (NPDA/BP)** | Teams of 2 — NPDA: 2 teams; BP: 4 teams, two per side | Motion revealed shortly before the round | Sequence of speeches, format varies by variant (e.g. 7-8-8-8-4-5 minutes) | **15-20 minutes only**, between getting the motion and speaking | Points of Information — brief live interjections into an opponent's speech, opponent may accept or decline |
| **World Schools (WSDC)** | 3 vs 3 | Mix of prepared and impromptu motions | 8-minute speeches, then a 4-minute reply speech per team | Impromptu motions get very short prep; prepared motions get real research time | International championship format, combines both prep styles in one competition |
| **Oxford-style** | 2 sides (often teams), formal | One motion | Strict alternating speeches, formal and eloquence-focused | Standard | **Audience votes before and after** — the actual "win" metric is whether the debate moved opinion, not a judge's score |

## What this validates in the current design

- **The single-topic, 1-on-1, fixed-resolution shape (your default) maps closely to Lincoln-Douglas**, not to Presidential debates. That's a good match for the steelman premise — LD's whole point is two people building sustained, competing cases on one resolution, exactly your architecture. The match is structural only: the table above calls LD values-focused, while debatebench's example topic and datasets are policy-focused (IBM-Rank-30k's contested policy topics; DebateSum, drawn from Policy evidence).
- **The Prep phase is directly validated by Parliamentary/World Schools' bounded prep time** — a real, competitive format runs on 15-20 minutes of prep before speaking, confirming a bounded, timed prep phase (rather than unlimited pre-gathered evidence) is a legitimate, tested constraint, not an invented one.
- **LD's speech-count asymmetry with equal total time** is a refinement worth considering for the per-side budget design: rather than only varying *how much* budget each side gets, a side could also get a different *shape* of budget (more, shorter turns vs. fewer, longer ones) while holding total budget equal — a genuinely different asymmetry axis than what's currently planned.
- **Real formats use both of the budget mechanics ADR-002 currently mixes.** Every speech has a fixed time limit (a per-phase cap), and LD, Policy and PF also give each side a prep pool it spends whenever it chooses (a chess clock). ADR-002 invokes both without saying which it means. That stays an open question; this research doesn't settle it.

## What Presidential debate format would actually mean for debatebench

This is a **structurally different format**, not a variant of the current one: multiple topics per debate, each getting its own short, self-contained cycle (question → response → rebuttal → follow-up) rather than one topic sustained through a full opening-to-conclusion arc. A moderator (arguably a role debatebench doesn't currently have — the judge is post-hoc, not topic-directing) selects and sequences the topics live.

If this format is wanted, it's a second, distinct format type in `run.yaml` — e.g. `multi-topic`, with a `topics: [...]` list and a short per-topic cycle — alongside today's single-topic arc (the LD-style default, which has no type name yet), not a modification of the existing phase list. ADR-002's `format:` is already an object (`prep`, `rounds`, `phases`), so a format type has to live inside it (e.g. `format.type`) rather than replace it with a string. Implications:
- Each topic's cycle is much shorter than the full 5-6 phase arc — closer to 3-4 exchanges per topic.
- Steelman fidelity and evidence grounding get measured *per topic*, not once over a whole debate — the rubric would need to aggregate across topics rather than score a single arc.
- A "moderator" role (topic selection/sequencing) doesn't exist in the current design at all and would need to be added, likely as a lightweight, config-driven topic list rather than a fourth live agent — closer to a playlist than a personality.

**Not recommending this for v1** — it's a meaningfully larger scope addition (aggregated per-topic scoring, topic sequencing) rather than a config tweak. Worth flagging as a genuine v2 candidate rather than folding into the current build guide.

## Other real mechanics noted, not currently planned

- **Points of Information** (Parliamentary) — brief live interjection during an opponent's turn, accepted or declined by the speaker. Would add real complexity (turn-taking within a turn) for uncertain value at MVP stage. Worth naming as a deliberately deferred feature rather than an oversight.
- **Audience voting as the win metric** (Oxford) — an entirely different notion of "winning" than a rubric judge: did the debate change minds, not who argued better by fixed criteria. Not a replacement for the rubric judge, but a plausible *additional* v2 metric if the app ever supports live user voting alongside automated judging.

## Net effect on current plan

No changes to the settled B0-B7 build guide or ADR-002 — the current single-topic, phase-as-data, per-side-budget design is validated as structurally matching a real, well-established format (LD) rather than an invented shape. The multi-topic/presidential-style format and Points-of-Information mechanic are logged here as considered, well-understood v2 candidates, not gaps in the current design.

## Sources consulted (added 2026-09-11)

- NSDA, *Start Here: Teaching Lincoln-Douglas* — https://www.speechanddebate.org/wp-content/uploads/Start-Here-Teaching-Lincoln-Douglas.pdf
- NSDA, *Start Here: Teaching Public Forum* — https://www.speechanddebate.org/wp-content/uploads/Start-Here-Teaching-Public-Forum.pdf
- Debate Clock, Lincoln-Douglas format — https://www.debateclock.org/formats/lincoln-douglas/
- Structure of policy debate (Wikipedia) — https://en.wikipedia.org/wiki/Structure_of_policy_debate
- National Parliamentary Debate Association (Wikipedia) — https://en.wikipedia.org/wiki/National_Parliamentary_Debate_Association
- World Schools Debating Championships (Wikipedia) — https://en.wikipedia.org/wiki/World_Schools_Debating_Championships
- World Universities Debating Championship, BP format (Wikipedia) — https://en.wikipedia.org/wiki/World_Universities_Debating_Championship
- ABC News, debate rules for Sept 10, 2024 — https://abc.com/news/5e38600c-4732-4cd2-a99c-3dedfa81beb0/category/1138628
