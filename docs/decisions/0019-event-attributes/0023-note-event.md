# 0023 — A note event annotates an open task

Status: Proposed
Date: 2026-10-11

## Context

[ADR 0020](0020-event-attribute-map.md) lets every journal event carry
an open attribute map, and the key `note` carries a note. A note can
therefore ride on an add, an update, a completion or a scratch.

A user also records a note on an open task between those writes: a step
taken toward the task, or a reason it waits ([R6](REQUIREMENTS.md)).
Such a note belongs to no change of task state, so no existing event
fits it. An `update` that carries only a note would write a
`TaskUpdated` event that changes nothing.

The journal already stamps every event with its time, as `occurred_at`
([ADR 0010](../0008-journal-authority/0010-event-ordering-key.md)), so
an event dates a note without a key of its own.

## Decision

**A `TaskAnnotated` event carries a note on an open task.** The event
changes no task state. It exists to carry a note and its attributes on
the task's stream, and its timestamp comes from the journal. The `note`
command writes it. A note on a task without an `[ID:]` stamps the id
first, on an event of its own. `note` takes no `--date`.

[DESIGN.md](DESIGN.md#note-event) specifies the command, the write
object and the payload.

## Options considered

### A note event of its own (chosen)

- a note on an open task gets a record of its own, dated by the
  journal [pro]
- every event that changes task state still changes it [pro]
- one more event type for every journal reader to accept [con]

### An update that carries only attributes

- no new event type [pro]
- a `TaskUpdated` event with an empty delta records a change that
  changed nothing [con]
- a reader that lists the changes to a task must filter out the empty
  ones [con]

### A note field on the item

- the note shows wherever the item renders [pro]
- a later note overwrites an earlier one, or the field grows into a
  log of notes [con]
- the field holds no date unless the user writes one into it [con]

## Rationale

A note between writes is a fact of its own kind: it records something
about the task and changes nothing in it. A separate event type keeps
that kind apart from the events that change state, so a reader that
rebuilds a task from its deltas does not meet an empty one.

The note keeps the shape ADR 0020 gives every fact: the key `note` in
the attribute map, beside any other attribute the user gives. The
journal timestamp dates it, as it dates every event.

## Consequences

- The journal gains the `TaskAnnotated` event type. A reader that
  rebuilds task state skips it, because it carries no delta.
- A note on a task without an `[ID:]` writes two events: the id stamp,
  then the note.
- The date of a note is the time the command ran. A user cannot
  backdate a note.
