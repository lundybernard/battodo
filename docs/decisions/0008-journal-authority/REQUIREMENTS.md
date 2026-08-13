# Journal authority — Requirements

> Author: lundybernard
> Date: 2026-08-13
> Branch: journal-authority-adrs

## Purpose

Flip storage authority: the event journal becomes the source of truth
and the markdown lists become a generated projection, reversing the
hybrid that [ADR 0004](../0000-project-bootstrap/0004-storage-architecture.md)
established. These are the acceptance criteria the flip must satisfy;
the decisions behind them are ADRs 0009–0012, and the implementing spec
lands with the refactor, not here.

**Timing.** None of this blocks the imminent daily-driver cutover — the
owner is sole user and rewrites history files freely until then. It must
land before the tool is shared with a second user. Interim rule:
btd-mediated mutations only.

## Requirements

### R1 — Exit guarantee

> The markdown projection must always be complete enough that deleting
> the tsdb loses only history, never state.

(The tsdb is the journal store — the authoritative event log plus
anything derived from it.) A user who removes btd from a project keeps a
working todo list; only the time series is lost.

### R2 — Gap-free time series once flipped

After the flip, every state change to a journaled list is represented by
an event. No mutation path produces state that the journal did not
record. Lists that have not adopted btd are read-only and out of scope —
they are merged into views and never journaled.

### R3 — Merge convergence

Merging any two journals for the same source, in any order, yields byte-
identical files and an identical projected state. Replaying a journal in
any received order converges to the same state as replaying it in
authoritative order.

### R4 — Epoch ordering

Event timestamps are epoch numbers, and the authoritative order of a
journal is a total order derived from them plus the event id — computed,
never read from a stored line position.

## Success criteria

- [ ] `export` produces a markdown tree that satisfies R1 with the
      journal directory deleted
- [ ] A property test shuffles a journal and asserts identical projected
      state (R3)
- [ ] Round-trip parsing, lazy `[ID:]` allocation, and `backfill` are
      deleted, not merely unused
- [ ] CI green on the final commit
