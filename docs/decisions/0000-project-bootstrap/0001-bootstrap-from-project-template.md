# 0001 — Bootstrap from lundybernard/project_template

Status: Accepted
Date: 2026-08-07

## Context

BatTodo needs a repo skeleton. The author maintains
`lundybernard/project_template` (last touched 2022: poetry-core build,
Python ^3.8, leftover setup.py/requirements.txt/.travis.yml, flat `bat/`
package layout). A stated goal of this project is improving that
template with lessons learned, which requires actually building on it.

## Decision

Bootstrap by importing a pristine snapshot of `project_template` at a
pinned commit, then modernize it in-place as the project progresses.
Every generalizable fix is upstreamed to the template.

## Options

### Option 1 — lundybernard/project_template
- [pro] The author owns it; every fix upstreams directly, which is the point
- [pro] Pinned-snapshot import makes later template diffs easy
- [con] Stale: poetry, old Python floor, dead CI — modernization is real work

### Option 2 — scientific-python/cookie via copier
- [pro] Modern, maintained, reproducible scaffold (used for batconf-tui)
- [con] Upstreaming goes through external review; doesn't serve the template-improvement goal

### Option 3 — monorepo fork (minimal CLI template)
- [pro] Structurally closest to a CLI app (src layout, typer, ruff ALL)
- [con] Upstream isn't the author's; conflicts with the argparse decision (ADR 0003)

## Rationale

The meta-goal outranks convenience: the modernization work Option 1
requires *is* the deliverable for the template. Options 2 and 3 would
produce a nicer skeleton faster but generate no upstreamable output.

## Consequences

- First commits are a pristine template import + minimal rename, so
  `diff` against the template stays meaningful.
- Modernization (build backend, CI, layout) happens as explicit changes,
  upstreamed individually.
