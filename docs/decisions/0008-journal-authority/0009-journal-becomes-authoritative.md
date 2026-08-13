# 0009 — Journal becomes authoritative

Status: Accepted
Date: 2026-08-13

Supersedes the storage-authority decision of
[ADR 0004](../0000-project-bootstrap/0004-storage-architecture.md).

## Context

ADR 0004 made the markdown lists authoritative and the journal a derived
audit trail, betting that hand-editability had to survive because the
system was in daily human use. Usage since then says otherwise. The
primary driver is an AI agent operating the CLI; a TUI for quick human
add and check-off comes later, and it will speak to btd, not to the
files. The time series exists to be analyzed and reported on. Hand-
editing the markdown turned out interesting, not critical.

Tolerating hand edits is not free. It buys three pieces of machinery:
the parse→serialize byte-identity guarantee, lazy `[ID:]` allocation
with title-based selection as a fallback for tasks that have no id yet,
and the `backfill` command. It also makes the time series lossy in a way
no amount of care fixes — a hand edit is a state change that produces no
event, which is exactly what ADR 0004 recorded as the journal's "single
most important caveat".

The cost is paid continuously; the thing it protects is no longer used.

## Decision

**The event journal is authoritative. The markdown lists become a
generated projection of it.** btd writes events; the markdown is
rendered from the fold over those events. Hand edits to the projection
are not read back — they are overwritten on the next render.

The markdown parser survives as an **importer**: it reads foreign or
pre-adoption markdown once, to produce genesis events
([ADR 0012](0012-optional-per-project-tool.md)). It is no longer part of
the read path.

## Options

### Option 1 — Flip: journal authoritative, markdown a projection (chosen)
- [pro] The time series becomes gap-free, which is the reason the journal exists
- [pro] Deletes the round-trip guarantee, lazy id allocation, and `backfill` outright — machinery whose only job was tolerating hand edits
- [pro] Matches how the tool is actually driven: an agent through the CLI, a TUI later
- [con] Hand-editing stops working; a mistake in the projection can only be corrected through btd
- [con] The projection must stay complete enough to stand alone if btd is removed

### Option 2 — Status quo: markdown authoritative, journal derived
- [pro] Zero work, and hand-editing keeps working
- [con] The time series stays permanently incomplete, so analysis over it is unsound
- [con] The tolerance machinery is a permanent tax on every feature that touches storage

### Option 3 — Middle ground: editable projection reconciled back
Keep the projection hand-editable, detect divergence with a content
hash, and add a `reconcile` command that imports the diff as events.
- [pro] Keeps hand-editing and still closes the time-series gap
- [con] More machinery than the status quo, not less — a differ and an event synthesizer on top of everything already there
- [con] Only worth building if hand-editing is actually missed, which is not yet known

## Rationale

ADR 0004 was right for its constraints and is being superseded because
the constraints changed, not because it was wrong. Its hedge worked: the
journal was designed so that making it authoritative would be a
migration rather than a redesign, and full task snapshots per event mean
replay does not depend on having observed every prior change.

Between the flip and the middle ground, the deciding question is whether
hand-editing is missed. Option 3 is strictly more machinery than
Option 1, so building it now would be paying for an answer nobody has
asked for. Flipping first makes the question empirical: if the owner
reaches for a text editor and resents the tool, Option 3 is still there,
and by then it is a known need instead of a guess.

## Consequences

- The parse→serialize byte-identity guarantee is deleted. It was a
  standing gate in ADR 0004; it protects nothing once the projection is
  generated.
- Lazy `[ID:]` allocation and title-based selection go away — every task
  gets an id at its `TaskAdded` event. `backfill` goes with them.
- The projection carries an exit guarantee: deleting the journal store
  must lose only history, never state
  ([R1](REQUIREMENTS.md), [ADR 0012](0012-optional-per-project-tool.md)).
- Nothing blocks the daily-driver cutover. The owner is sole user and
  rewrites history files freely until the flip lands; the interim rule
  is btd-mediated mutations only. The flip must precede sharing the tool
  with a second user.
- **Revisit — reconcile.** If hand-editing is missed in practice,
  Option 3 is the fix, and the content-hash check is where it starts.
