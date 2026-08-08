# 0004 — Storage architecture

Status: Accepted
Date: 2026-08-08

## Context

Storage carries the project's hardest requirements. Constraints:

- Multiple todo lists in different directories must compose into one
  view: a personal home-directory list, explicitly-added lists in
  shared/synced directories, and lists auto-discovered from the working
  directory in project repos (R6).
- The current system is human-edited markdown, synced by Syncthing.
  Hand-editability and sync-friendliness have real value today, and the
  live `~/todo/` system stays in daily use through the transition — a
  SessionStart hook reads it every session.
- The author is inclined toward an immutable, time-series-style record,
  similar to OpenFrameKeeper's event store, and sees BatTodo as a
  test-bed for that design.
- `completed.md` is already an append-only log; the mutable state lives
  in the category files.

The tension: an event log is the desired end state, but a flag-day
migration would break hand-editing and the live hook on day one.

## Decision

**Hybrid, with the markdown files authoritative and a journal recorded
alongside.** Markdown remains the source of truth for open items. Every
btodo-mediated mutation additionally appends an event to a journal. The
journal is designed so that making *it* authoritative later is a
migration, not a redesign.

### The journal is a partial record, on purpose

Hand-edits bypass btodo and therefore bypass the journal. During the
hybrid era the journal is **not** a complete history: it records what
btodo did, not everything that happened. This is stated plainly rather
than papered over, and it is the single most important caveat about the
data. Two consequences follow directly:

- Nothing may be derived from the journal alone while markdown is
  authoritative. The journal is an audit trail and a migration asset.
- Every event carries a **full task snapshot** at event time, not just
  the field delta. Replay after an authority flip therefore does not
  depend on having observed every prior change — a snapshot re-anchors
  state even when unjournaled hand-edits happened in between. This is
  what makes the flip survivable despite the partial record.

### Layout: one journal per source directory

```
<source_dir>/.journal/log.jsonl
```

One journal per source directory rather than one global log. The
prototype only wires `~/todo/`, but per-source journals make R6
composability structural rather than a later retrofit: adding a source
adds a journal, and no global file becomes a contention point between
directories that sync independently.

### Envelope

JSONL, one event per line, adopting OpenFrameKeeper's envelope
(OFK ADR 0002) so the two projects share one event vocabulary:

`seq` (1-based, equals line number), `event_id` (uuid4), `stream_id`
(`task/<id>`), `stream_seq`, `type`, `schema_version: 1`, `occurred_at`,
`recorded_at`, `prev_hash`/`hash` (both `null`, reserved), `metadata`
(actor `user`|`agent`, source file), `payload` (field deltas + full task
snapshot).

Event types: `TaskAdded`, `TaskCompleted`, `TaskScratched`,
`TaskBumped`.

Deferred from OFK's envelope: the hash chain (null, as OFK also does in
v1) and the `correlation_id`/`commit_len`/`commit_index` commit-boundary
machinery. The prototype emits single-event commits only, so there is no
partial-commit hazard to detect yet.

### Task identity: lazy ID injection

Tasks get a stable `[ID:xxxxxx]` field (6-char base36) so events can
reference a task across renames. IDs are injected **lazily**: btodo adds
one to a task line the first time it mediates a mutation on that task.
Hand-added tasks simply have no ID until btodo first touches them.

The parser accepts lines with and without an ID. On injection the field
is appended at the end of the existing field list, leaving every other
field in its original position.

This is an extension to the `~/todo/SCHEMA.md` item grammar. The live
SCHEMA.md is deliberately **not** edited here; adopting the extension on
the live system is a separate decision for its owner.

### Round-trip safety is the enabling constraint

Because markdown stays authoritative and hand-edited, btodo must never
reformat a file it did not mean to change. **Parse → serialize is
byte-identical for any valid file.** The parser retains each line
verbatim and uses it as the serialization source; mutations perform
targeted substring replacement on that raw line rather than rebuilding
it from parsed fields.

Rebuilding is not an option: field order varies line to line in the live
data (`[P:95] [BUMPED:…] [LOE:8] [TAGS:…]` next to
`[P:33] [BUMPED:…] [DUE:…] [LOE:1]`), so any canonical-order serializer
would rewrite every line it touched. Note also that notes/continuation
lines are indented 6 spaces while subtasks are indented 2 — the
discriminator between them is the presence of a `- [ ]`/`- [x]`
checkbox, not the indent width.

### Concurrency: keep it simple

- One log file per source, appended with `O_APPEND` under an advisory
  `flock`, `fsync` on write (OFK's durability rules 1–2).
- Syncthing conflict files are accepted as manual cleanup. No merge
  logic.

### List discovery

A markdown file is a todo list if it contains a `## Open` heading. This
is the predicate behind the R4 fix: the current scripts hard-code five
category filenames and silently skip `backlog.md` and other ad-hoc
lists. The heading test picks those up while correctly excluding
`SCHEMA.md`, `CLAUDE.md`, `completed.md` (a different format), and
templates.

### Revisit triggers

Named now so the next decision is a checkpoint, not a surprise:

- **Authority flip** — when the journal is complete enough to trust,
  markdown becomes a projection and the log becomes source of truth.
  Trigger: hand-edits have become rare, or btodo covers every mutation
  the user performs.
- **Per-device log splitting** — the single-log-per-source choice fails
  if two devices append concurrently and Syncthing produces conflict
  files faster than they can be cleaned up by hand. Trigger: recurring
  conflict files on `log.jsonl`. The fix is a log file per device
  (`log.<device>.jsonl`) merged on read, which the envelope already
  supports because ordering is reconstructable from `occurred_at` plus
  `stream_seq`.

## Options

### Option 1 — Hybrid: markdown authoritative, journal recorded alongside (chosen)
- [pro] Zero migration risk; hand-editing, Syncthing, and the live SessionStart hook keep working unchanged
- [pro] Starts accumulating real event data immediately, which is what makes a later flip evaluable rather than theoretical
- [pro] Snapshot-carrying events make the authority flip a migration, not a redesign
- [con] Two representations to keep consistent; btodo must be round-trip-safe or it corrupts hand-edited files
- [con] The journal is knowingly incomplete during the hybrid era

### Option 2 — Markdown files in place, no journal
- [pro] Simplest possible; nothing new to maintain
- [con] Produces no event data, so the event-log question stays permanently theoretical
- [con] No audit trail; concurrent edits and sync conflicts land on mutable files with no history

### Option 3 — Immutable event log authoritative from day one
- [pro] The end-state design, reached directly with no hybrid era
- [con] Breaks hand-editing and the live hook on day one — unacceptable for a system in daily use
- [con] Biggest build (projections, compaction) before any usable feature ships

### Option 4 — SQLite
- [pro] Real query and transaction semantics
- [con] Breaks hand-editing and clean file sync; binary blobs conflict badly under Syncthing

## Rationale

The hybrid is the only option that satisfies the hard constraint — the
live system must keep working, unchanged, throughout — while still
answering the question the project exists to explore. Option 3 is the
destination; the hybrid is how to reach it with evidence rather than
conviction, and the snapshot-per-event rule is what keeps that path open
despite a partial log.

The composability requirement (R6) interacts here, and the per-source
journal layout resolves it structurally: sources compose by union, and
each carries its own history.

## Consequences

- btodo owns a round-trip guarantee. A parse→serialize byte-identity
  test over the live files is a standing gate; breaking it means btodo
  can corrupt hand-edited data.
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
- SCHEMA.md's prose ("surface open items where `DUE` is absent or
  `DUE <= today`") is stricter than both R3 and `view_todos.py`, which
  hide only *future-recurring* items. btodo follows R3 and the script.
  The inconsistency is in the live template of record and is the
  owner's to reconcile.
