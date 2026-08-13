# 0004 — Storage architecture

Status: Accepted
Date: 2026-08-08

## Context

Storage carries the project's hardest requirements. Constraints:

- Multiple todo lists in different directories must compose into one
  view: a home-directory list, explicitly-added lists in shared/synced
  directories, and lists auto-discovered from a project working
  directory (R6).
- The current system is human-edited markdown, synced by Syncthing, and
  stays in daily use throughout — a SessionStart hook reads `~/todo/`
  every session. Hand-editability and sync-friendliness have real value
  today.
- The author is inclined toward an immutable event store, as in
  OpenFrameKeeper, and sees BatTodo as a test-bed for it. `completed.md`
  is already an append-only log; only the category files are mutable.

The tension: an event log is the desired end state, but a flag-day
migration would break hand-editing and the live hook on day one.

## Decision

**Hybrid, with the markdown files authoritative and a journal recorded
alongside.** Markdown remains the source of truth for open items; every
btodo-mediated mutation additionally appends an event to
`<source_dir>/.journal/log.jsonl`. The journal is designed so that
making *it* authoritative later is a migration, not a redesign.
Envelope, durability, and parser mechanics: [DESIGN.md](DESIGN.md).

### The journal is a partial record, on purpose

Hand-edits bypass btodo and therefore bypass the journal: it records
what btodo did, not everything that happened. This is the single most
important caveat about the data, and two rules follow.

- Nothing may be derived from the journal alone while markdown is
  authoritative. It is an audit trail and a migration asset.
- Every event carries a **full task snapshot** at event time, not just
  the field delta, so replay after an authority flip does not depend on
  having observed every prior change — a snapshot re-anchors state even
  when unjournaled hand-edits happened in between. That is what makes
  the flip survivable despite the partial record.

### One journal per source directory

Not one global log. Per-source journals make R6 composability structural
rather than a later retrofit: adding a source adds a journal, and no
global file becomes a contention point between directories that sync
independently. The envelope is OpenFrameKeeper's (OFK ADR 0002), so the
two projects share one event vocabulary: JSONL, one event per line,
types `TaskAdded`, `TaskCompleted`, `TaskScratched`, and `TaskBumped`
(retired by ADR 0005). OFK's hash chain and commit-boundary fields are
deferred — BatTodo emits single-event commits only. Spec:
[DESIGN.md](DESIGN.md).

### Task identity: lazy ID injection

Tasks get a stable 6-char base36 `[ID:…]` so events can reference a task
across renames, written the first time btodo mediates a mutation on it;
hand-added tasks have none until then. This extends the
`~/todo/SCHEMA.md` item grammar. The live SCHEMA.md is deliberately
**not** edited here — adopting the extension there is its owner's call.

### Round-trip safety is the enabling constraint

Because markdown stays authoritative and hand-edited, btodo must never
reformat a file it did not mean to change: **parse → serialize is
byte-identical for any valid file.** Rebuilding lines from parsed fields
is not an option — field order varies line to line in the live data, so
a canonical-order serializer would rewrite every line it touched. The
mechanism is in [DESIGN.md](DESIGN.md).

### List discovery

A markdown file is a todo list if it contains a `## Open` heading — the
predicate behind the R4 fix, where the current scripts hard-code five
category filenames and silently skip `backlog.md` and other ad-hoc
lists. It correctly excludes `SCHEMA.md`, `CLAUDE.md`, `completed.md`
(a different format), and templates.

## Options

### Option 1 — Hybrid: markdown authoritative, journal recorded alongside (chosen)
- [pro] Zero migration risk; hand-editing, Syncthing, and the live SessionStart hook keep working unchanged
- [pro] Starts accumulating real event data immediately, which is what makes a later flip evaluable rather than theoretical
- [con] Two representations to keep consistent; btodo must be round-trip-safe or it corrupts hand-edited files, and the journal is knowingly incomplete meanwhile

### Option 2 — Markdown files in place, no journal
- [pro] Simplest possible; nothing new to maintain
- [con] Produces no event data and no audit trail, so the event-log question stays permanently theoretical

### Option 3 — Immutable event log authoritative from day one
- [pro] The end-state design, reached directly with no hybrid era
- [con] Breaks hand-editing and the live hook on day one — unacceptable for a system in daily use — and is the biggest build before any usable feature ships

### Option 4 — SQLite
- [pro] Real query and transaction semantics
- [con] Breaks hand-editing and clean file sync; binary blobs conflict badly under Syncthing

## Rationale

The hybrid is the only option that satisfies the hard constraint — the
live system must keep working, unchanged, throughout — while still
answering the question the project exists to explore. Option 3 is the
destination; the hybrid is how to reach it with evidence rather than
conviction, and the snapshot-per-event rule is what keeps that path open
despite a partial log. The composability requirement (R6) resolves in
the same move: sources compose by union, each carrying its own history.

## Consequences

- btodo owns a round-trip guarantee. Parse→serialize byte-identity over
  the live files is a standing gate; breaking it means btodo can corrupt
  hand-edited data.
- The journal cannot be trusted as a complete history and must not be
  read as one until after an authority flip.
- Adding the deferred envelope fields later (hash chain, commit
  boundaries) is additive and needs no `schema_version` bump, per OFK's
  versioning rule 1 — which is precisely what keeps the flip a migration
  rather than a redesign.
- `[ID:…]` makes BatTodo's files a superset of SCHEMA.md's grammar. Any
  other tool reading these files must tolerate an unknown field; the
  live system's own scripts already ignore unrecognized bracket fields.
- R6 is schema-ready but not wired: the prototype resolves exactly one
  source.
- **Revisit — authority flip.** When hand-edits have become rare, or
  btodo covers every mutation the user performs, markdown becomes a
  projection and the log becomes the source of truth.
- Concurrent writes are not merged: Syncthing conflict files on
  `log.jsonl` are cleaned up by hand.
- **Revisit — per-device log splitting.** One log per source fails if
  two devices append concurrently and Syncthing produces conflict files
  faster than they can be cleaned up by hand; recurring conflict files
  on `log.jsonl` are the trigger. The fix is one log per device,
  `log.<device>.jsonl`, merged on read — the envelope already supports
  it ([DESIGN.md](DESIGN.md)).
