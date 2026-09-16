# ADR-029: Release 0.1.0 to Real PyPI, Published by the Repository and Not by a Token

**Status:** Accepted
**Date:** 2026-09-16
**Depends on:** ADR-002 (scope, the name), ADR-005 / ADR-013 / ADR-027 (the three
`schema_version`s), ADR-028 §9 (the Python surface is pre-1.0; the JSON is the
contract), B7's packaging gate
**Supersedes:** CLAUDE.md's "**Not published to real PyPI** … that step needs its
own decision." This is that decision.

## Context

B7 published `0.1.0.dev0` to **TestPyPI** on 2026-09-14 and verified it the only
way that counts: installed *from the index* into a fresh virtualenv and ran a
full debate and judge from that install, reproducing the source tree's output
exactly — same seed, same scores, across a packaging boundary.

What was left undone was deliberate. The name was unclaimed on real PyPI (a 404
on the JSON API, re-checked and still 404 on 2026-09-16), and claiming it is
permanent in a way nothing else in this project is.

Two facts constrain everything below:

- **PyPI never lets a version be re-uploaded.** Not after a delete, not after a
  yank. `0.1.0` is one attempt, forever.
- **This project has already leaked two PyPI tokens** into a working transcript
  (both since revoked). That is the specific failure a release process here has
  to be designed against, not a hypothetical one.

## Decision

### 1. The released version is `0.1.0`, not `0.1.0.dev0`

A `.dev0` suffix makes the release a *development* release, which `pip install
debatebench` will not select — it needs `--pre`. Publishing the current version
string to real PyPI would put a package on the index that the README's own
install line cannot install. The version is bumped in `pyproject.toml` as part
of this decision.

### 2. PyPI Trusted Publishing, not an API token

The release job authenticates to PyPI by OpenID Connect from GitHub Actions.
**No long-lived PyPI credential exists anywhere** — not in the repo, not in
Actions secrets, not on the development machine, not in a transcript.

This is chosen over an API token specifically because two tokens have already
been exposed here. A token that is stored more carefully is a smaller version of
the same problem; a release process with no token removes the class. The
secondary benefit is that a publish is attributable to a commit and a workflow
run rather than to whoever holds a secret.

### 3. A release is a tag, built in CI from a clean checkout

`.github/workflows/release.yml` runs on a published GitHub Release, builds the
wheel and sdist with `uv build`, and uploads both. The artifact is therefore
built from what is committed at that tag, not from a developer's working tree —
which is how the TestPyPI artifact was built, and is one more thing that cannot
be verified after the fact.

The job runs in a GitHub **environment** named `pypi`, so the trusted-publisher
binding names an environment as well as a workflow, and a release can be given a
required reviewer later without touching this ADR.

There is **no `workflow_dispatch`** on the release workflow. A manual run would
publish from whatever `main` happens to be at that moment, which is the same
accident this clause rules out for a stray tag push, reached another way. A
failed release is not re-run; it becomes a new version, because PyPI will not
accept `0.1.0` a second time however the first attempt ended.

**The README at the tagged commit is the PyPI page, permanently.** `readme =
"README.md"` copies the file into the artifact's metadata at build time; PyPI
renders that copy, offers no way to edit it, and will not accept the version
again. So every document the release freezes has to be true *at the tag*, not
shortly afterwards.

`0.1.0` got this wrong. Its README was deliberately left saying "Published to
**TestPyPI** only — not to the real PyPI", on the reasoning that it stayed true
until an upload succeeded and should not claim otherwise in advance. The
reasoning was sound about the repository and wrong about the artifact: a branch
is momentarily behind reality for a few minutes and then corrected, while the
published page is wrong forever and is the first thing a reader sees. It shipped
a PyPI page telling people the package was not on PyPI, and instructing them to
install it from TestPyPI with two index flags.

The correct order is: fix the README **in the release commit**, then tag. The
window where `main` describes a release that has not happened yet is closed by
the release itself, minutes later. `tests/test_packaging.py` now enforces it —
for a non-pre-release version the README must carry a plain `pip install
debatebench` and must not mention `test.pypi.org` — and the guard was checked
against the README that actually shipped, which it fails.

**A version bump relocks in the same commit.** `uv.lock` pins this project at
its own version, and both workflows use `uv sync --locked` on purpose — a lock
that has drifted from `pyproject.toml` should fail rather than be re-resolved
into something untested. The consequence is that an un-relocked bump breaks the
*release* job, after the tag exists, where the only remedy is §6. So the
invariant is a test rather than a note: `tests/test_packaging.py` compares the
two and fails on the bump commit, locally and in CI, where relocking is free.
It was verified by simulating the bump it is meant to catch.

### 4. What `0.1.0` claims, and what it does not

It does **not** claim the tool is finished. B6's live gate is unmet: no judge
tested produces all three fact-check clauses at once, and `--fact-check` is on
by default. The README states that at the flag itself rather than in a footnote,
and that stays true at 0.1.0.

`0.1.0` claims exactly this much: the two commands, their flags and the three
file formats are stable enough to depend on within the 0.1.x line, and the
`schema_version` in each file is the thing to check. `debatebench.api` is
pre-1.0 on ADR-028 §9's terms and may change with a minor version.

### 5. The release verifies its own upload before anyone depends on it

`twine check` validates metadata, not that the artifact installs and runs. B7's
gate clause was *install from an index and run*, and that is the clause that
produced this project's only determinism evidence spanning build and publish.
So a third job repeats it against real PyPI: install `debatebench==<version>`
into a virtualenv that has never seen the source, run both console scripts, and
import `debatebench.api`. It retries, because the index can lag an upload by
under a minute and a release should not fail on CDN timing.

This cannot prevent a bad upload — nothing can, given §6. It converts "we will
find out when someone reports it" into "we know within a minute whether to
yank", which is the difference between the remedy being available and being
used.

### 6. A bad release is yanked, never replaced

If `0.1.0` is wrong, the fix is `0.1.1`. The broken version is yanked — which
leaves it installable by exact pin, so an existing lockfile does not break,
while removing it from fresh resolution. Deleting it is not an option worth
reaching for: it frees nothing, since the version can never be reused.

### 7. Claiming the name is deliberate, and the collision is unchanged

`debatebench` on PyPI becomes permanent on first upload. The unrelated
**DebateBench** benchmark (arXiv 2502.06279) is a dataset, not a package, and
does not hold this name — so publishing does not take anything from it. It does
make this project the answer to `pip install debatebench`, which is a real
consequence and is accepted on the same grounds ADR-002 accepted the name: the
README's second section names the collision and links the paper before it
describes anything else.

## Why

**Because the deferral had one reason and it has expired.** B7 left this open
because the step needed a decision, not because anything was missing: the wheel
was built, installed from an index, and run end to end. The only genuinely new
thing since is that a public repository now exists — which is what makes
trusted publishing possible at all.

**Because the token problem has a structural fix and this is the moment to take
it.** Setting up a token now would work, and would leave a credential that has
to be kept safe for the life of the project. The alternative costs one
configuration step on PyPI's website and then never again.

## Consequences

- **`pyproject.toml` version becomes `0.1.0`.** Every transcript and score file
  written after this records `debatebench_version: "0.1.0"`; the probe artifacts
  in this repo keep `0.1.0.dev0`, which is correct — they were written by it.
- **The README's Status section is rewritten.** "Published to TestPyPI only —
  not to the real PyPI" becomes false at first upload, and the two-index install
  incantation is replaced by `pip install debatebench`.
- **One manual step remains, and only the account owner can do it:** creating
  the *pending publisher* on PyPI, binding project `debatebench` to owner
  `robert-e-roy`, repository `debatebench`, workflow `release.yml`, environment
  `pypi`. Until that exists, the release job cannot authenticate, and that is
  the intended failure mode — nothing can publish by accident.
- **TestPyPI stays as it is.** `0.1.0.dev0` remains there as the record of B7's
  gate. Nothing is deleted.
- **Release is not automatic on tag push**, only on a *published* GitHub
  Release. Pushing a tag by mistake does not publish anything.

## Open questions this doesn't resolve

- Whether a `0.1.x` line is maintained at all, or whether the next release is
  simply `0.2.0` when B6 closes.
- Whether the release workflow should publish to TestPyPI *first* and verify an
  install from there before touching PyPI. §5 now verifies the real upload
  instead, which is cheaper and tests the artifact people actually get; a
  TestPyPI rehearsal would catch a broken package *before* it is permanent,
  which §5 explicitly cannot. Left open because it doubles the number of
  permanent name commitments, and nothing has yet gone wrong that it would have
  caught.
- Whether `debatebench.api` reaching 1.0 should coincide with the package
  reaching 1.0. ADR-028 §9 ties the API's promise to the package version, which
  may prove too coarse.
