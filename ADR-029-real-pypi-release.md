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

### 4. What `0.1.0` claims, and what it does not

It does **not** claim the tool is finished. B6's live gate is unmet: no judge
tested produces all three fact-check clauses at once, and `--fact-check` is on
by default. The README states that at the flag itself rather than in a footnote,
and that stays true at 0.1.0.

`0.1.0` claims exactly this much: the two commands, their flags and the three
file formats are stable enough to depend on within the 0.1.x line, and the
`schema_version` in each file is the thing to check. `debatebench.api` is
pre-1.0 on ADR-028 §9's terms and may change with a minor version.

### 5. A bad release is yanked, never replaced

If `0.1.0` is wrong, the fix is `0.1.1`. The broken version is yanked — which
leaves it installable by exact pin, so an existing lockfile does not break,
while removing it from fresh resolution. Deleting it is not an option worth
reaching for: it frees nothing, since the version can never be reused.

### 6. Claiming the name is deliberate, and the collision is unchanged

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
- Whether the release workflow should publish to TestPyPI first and verify an
  install from there before touching PyPI. It would have caught nothing so far,
  and it doubles the number of permanent name commitments.
- Whether `debatebench.api` reaching 1.0 should coincide with the package
  reaching 1.0. ADR-028 §9 ties the API's promise to the package version, which
  may prove too coarse.
