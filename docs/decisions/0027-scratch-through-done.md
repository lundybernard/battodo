# 0027 — A scratch closes a task through done

Status: Accepted (merged 2026-10-13, PR #114)
Date: 2026-10-13

## Context

btodo closes a task two ways. `done` completes it, and `scratch`
abandons it: the block leaves the list, and the completed log records
it as SCRATCHED. The two commands ran through two write objects that
repeated the list, log and journal steps of a close.

Since [ADR 0020](0019-event-attributes/0020-event-attribute-map.md),
every write takes `--note`, so a close can carry the reason it happened.
The owner ruled on 2026-10-13 that a scratch then needs no command of
its own. It is a close with a note that says the task was not
completed.

## Decision

**`done --scratch` closes a task without completing it.** One close
command takes a flag, and one write object carries the scratched state.
The `scratch` command goes. `--note` carries the reason, as on every
write, and `--date` names the day the task was closed.

The journal keeps the `TaskScratched` event type, and the completed log
keeps the SCRATCHED status. A scratch keeps its semantics:

- the whole block goes, its subtasks with it;
- one event and one log record name the task, and nothing cascades to
  its parent;
- a recurring task is removed, not rescheduled;
- a checklist item is dropped with no log record, and it refuses
  attributes.

## Options considered

### A scratch flag on done, event type kept (chosen)

- one command and one write object close a task [pro]
- the journal and the log read as before, so no migration runs [pro]
- the readers that tell a scratch from a completion keep their tests
  [pro]
- `done` now carries two outcomes behind one name [con]

### A reserved attribute key instead of the event type

- the close records only `TaskCompleted`, so the journal holds one
  close type [pro]
- every reader that tells a scratch from a completion moves from the
  type to an attribute value [con]
- the scratches already in the journal need a migration [con]
- a reserved key takes a name from the attribute map, which the user
  owns [con]

### Keep `scratch` as an alias of `done --scratch`

- existing call sites keep working [pro]
- an argparse alias cannot preset the flag, so the alias needs a parser
  of its own [con]
- two spellings of one command cost SKILL.md text, and the agent that
  reads it must learn both [con]

## Rationale

The difference between a completion and a scratch is the outcome of
one close, not a second operation. One write object owns the close, and
a flag selects the outcome, so the shared steps exist once.

The event type and the log status already state the outcome. The
closed test of `history`, which the reopen reads, tests the type, and
the completed digest tests the status. A new attribute key would
restate a fact the type holds and force a migration of the journal,
which is the record of every task
([ADR 0009](0008-journal-authority/0009-journal-becomes-authoritative.md)).

## Consequences

- `btodo scratch` exits with a usage error. A script that called it
  calls `btodo done <selector> --scratch`.
- `done --scratch --date` records the given day in the log and in the
  `TaskScratched` payload, under the key a completion uses, so
  `history` shows the day the log records.
- `completed` still counts DONE records only.

## Amendment — 2026-10-14

The write object of a close keeps the name `Completion`, and the record
of one closed task keeps `TaskCompletion`, though a scratch runs through
both. The names follow the `done` command and the usual outcome of a
close, and a rename would touch every caller with no change in
behaviour. `Completion` composes `CompletionLines`, which holds the
lines a close stamps, checks off and drops. The branches on a scratch
in the line plan sit there, in one object.
