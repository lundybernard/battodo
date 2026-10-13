# 0025 — A closed task reopens through update

Status: Proposed
Date: 2026-10-12

## Context

`done` and `scratch` close a task. A one-shot task then leaves its list,
and only the journal keeps it
([ADR 0022](0019-event-attributes/0022-history-command.md)). A task that
comes back, such as a renewal or a repair that returns, had one way
back: `add` it again. The new task took a new id, so its history split
across two streams and often two titles. `history` could find the old
stream, but no command could put it back.

The owner ruled on 2026-10-12 that btodo never removes a task from the
journal. `done` and `scratch` close it, and a later change reopens it.
The vocabulary is open and close, complete and reopen.

A reopen must know three things that the journal alone can hold once the
block has left the file: the state of the task when it closed, its
subtasks, and the list it lived in.

## Decision

**`update` reopens a closed task from its journal record.** When no
open task answers the selector, `update` resolves it against the closed
streams of the journal, as `history` does. The task comes back open,
under its own id, in the list its record names, with the changes the
update names. One `TaskUpdated` on the same stream records the
reopening beside those changes.

The snapshot of every event records the list of the task and its
subtasks, so the record of a closed task holds what a reopen restores.
A move between lists is an update too: `update --list` names the list,
and the delta records the change.

[DESIGN.md](0019-event-attributes/DESIGN.md#reopen) specifies the
selector, the restore, the deltas and the refusals.

## Options considered

### Reopen through update, from the journal record (chosen)

- one id keeps the whole life of a task, so `history` reads it whole
  [pro]
- the journal already holds the closing snapshot, so no new store is
  needed [pro]
- `update` already writes fields, a title and a description, so a
  reopen with changes is one command [pro]
- `update` gains a second selector scope and a second write path [con]

### A dedicated `reopen` command

- the name states the intent at the call site [pro]
- it repeats every option of `update`, or takes none and forces a
  second command for a new due date [con]
- the owner ruled `reopen` and `reschedule` sugar, to add only once
  they earn their place [con]

### Add the task again, as today

- needs no change [pro]
- a new id splits the history of one task across streams [con]

### Restore from the completed log

- the log holds a record of each closed task [pro]
- the log is a render of the journal and never rebuilds journal state
  ([DESIGN.md](0019-event-attributes/DESIGN.md#event-attributes)) [con]
- it records no description, no subtasks and no id [con]

## Rationale

A task that comes back is the same task. Its id is what ties its
events into one stream, and every reader that follows a task, `history`
first, follows that id. Reopening under the same id keeps one record per
task, where a second `add` starts a second one.

`update` is the command that already changes a task, so a reopen with a
new due date is one call. The selector rule of `history` already reaches
a closed task, so `update` borrows it rather than a new grammar. The
journal is the record after the flip
([ADR 0009](0008-journal-authority/0009-journal-becomes-authoritative.md)),
so the record of a closed task must carry what the file no longer
holds. The list and the subtasks are that part, which is why every
snapshot gains them.

## Consequences

- A closed task closed before this change carries no list in its
  snapshot. Its reopen needs `--list`. Each event's `source_file` names
  the list as well; this ADR does not read it.
- A parent closed before this change carries no subtasks in its
  snapshot, so it comes back without them.
- A reopened parent brings its subtasks back closed. `--with-subtasks`
  opens them too. A closed subtask reopens with each closed task above
  it. A checklist item has no stream and opens only with its task.
- The completed log keeps the record of each closing. A task reopened
  and completed again logs a second record on the same id.
- `history` lists a reopen as an entry of its own.
- `reopen` and `reschedule` stay open as names over `update`.

## Amendment — 2026-10-12

The first Consequences bullet is withdrawn. A snapshot without `list` is
outside the schema. The owner's journal was migrated in place by a
one-off local script that is not part of the project, so every snapshot
in it names its list. The reader does not fall back to `source_file`,
and it does not refuse a record without a list.
