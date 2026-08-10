# 0006 — Parked lists

Status: Accepted
Date: 2026-08-08

## Context

Extracted from [ADR 0005](0005-computed-rank.md), which decided this
alongside the computed-rank formula and records the bug in full:
`backlog.md` declares itself parked in prose, and the
discover-every-list fix for R4 — correct in itself — swept it up with
the rest. The discovery predicate has no notion of a list opting out.

## Decision

A list opts out of views by carrying the marker `<!-- battodo:parked -->`
anywhere in the file. `discover_lists` still returns it — so `backfill`
and any future mutation cover it — but `build_view` skips it. The
opt-out is opt-in: a live `backlog.md` with no marker keeps appearing
exactly as it does today.

## Options

### Option 1 — In-file marker (chosen)
- [pro] Self-describing and travels with the file — the same place `backlog.md` already states its intent in prose
- [pro] Hand-editable, and keeps the list discoverable for mutations while hiding it from views
- [con] A third extension to the SCHEMA.md grammar, and it needs the live file edited to take effect — so the live bug is only *fixable*, not fixed

### Option 2 — Multiplier-zero (`P:0` on every item)
- [pro] No new grammar; falls out of the multiplier semantics for free
- [con] Rewrites every item and loses their real priorities; conflates "this item is parked" with "this list is parked"

### Option 3 — Exclusion list in batconf config
- [pro] No file edits at all, and no grammar extension
- [con] Out-of-band: the file says it is parked, but the reason it is hidden lives somewhere else entirely
- [con] Config-file configuration is blocked on batconf 0.4.0/`TomlSource`, so this would be env-var-only today

## Rationale

A structural discovery predicate finds every list, including the ones a
human knew to leave alone. Intent that lives in prose needs a
machine-readable form, and the cheapest honest one sits in the file that
already carries the prose. Marking the list rather than filtering it
elsewhere also keeps discovery and visibility separate: parked means
"not shown", not "not known about", so mutations still reach the file.

## Consequences

- **The live bug is fixable, not fixed** — `backlog.md` in `~/todo/`
  keeps appearing until someone adds the marker by hand.
- **`discover_lists` and `build_view` diverge**, so every future
  traversal must pick one; mutations follow discovery.
- **SCHEMA.md gains a third unknown construct**, alongside `ADDED` and
  `ID` — ADR 0005 covers why the live spec is not edited here.
