# 0019 — Event attributes

**The decision this group names: facts a user records about a task live
in the journal, and a command that reads the journal shows them.** Facts
ride on the journal events as an open attribute map, so a new kind of
fact does not need a schema change. A fact about one completion rides
on that completion's event. The static description of a task is a field
on the task's own stream.

ADRs 0020–0023 are the component decisions: the attribute map on every
event, the journaled task description, the history command, and the
note event.

Branch: `adr-event-attributes` — Issue: #79

**Status: Accepted.** The group lands before the journal-authority flip
([ADR group 0008](../0008-journal-authority/README.md)).
[After the flip](#after-the-flip) lists the two items that wait for it.
S4, the notes in `show` ([ADR 0022](0022-history-command.md),
[DESIGN.md](DESIGN.md#show)), is pending. The history command and the
subtask schedules that it waits on have merged, so S4 is unblocked.
The property refactor
([ADR group 0016](../0016-property-refactor/README.md)) is complete,
apart from ADR 0018.

## Terms

The group uses one word for each meaning:

- **description:** the static text of a task. In the markdown it is the
  indented lines under the task line that carry no checkbox
  ([ADR 0021](0021-task-description-field.md)).
- **note:** a dated annotation in the journal, and the attribute key
  `note` that carries it ([ADR 0023](0023-note-event.md)).

## Requirements

ADRs 0020–0023 answer these requirements, and cite them by label.

### R1 — Facts per completion

A completion records zero or more facts about that completion, once per
completion. A repeating task accumulates one set of facts per cycle. No
completion overwrites the facts of an earlier cycle.

### R2 — A details view of the history

A details view lists the per-completion history of one task. The ranked
view does not show that history.

### R3 — A static description

A task may carry a static description. The description is a fact about
the task, and its mechanism is separate from R1. No completion appends
to it.

### R4 — Journal first

Every write is a journal event that carries the whole fact it records,
so the journal can rebuild each fact when the markdown becomes a render
of the journal at the flip.

### R5 — Open vocabulary

A new kind of fact does not need a schema change or a code change.

### R6 — Facts on any write

A user records facts on an add, an update, a scratch or a completion,
on the event of the task the user names. A user also records a note on
an open task without a change to that task.

## Planning docs

| File | Purpose |
| ---- | ------- |
| [DESIGN.md](DESIGN.md) | Command surface, payload keys, attribute grammar |

## Component ADRs

| # | Title | Status |
| - | ----- | ------ |
| [0020](0020-event-attribute-map.md) | Every journal event carries an open attribute map | Accepted |
| [0021](0021-task-description-field.md) | A task description is a journaled item field | Accepted |
| [0022](0022-history-command.md) | A history command reads the journal | Accepted |
| [0023](0023-note-event.md) | A note event annotates an open task | Accepted |

## After the flip

Two items need the journal-authority flip
([ADR group 0008](../0008-journal-authority/README.md)) and land with
it:

- The importer that writes the genesis events at the flip reads the
  existing description lines into `snapshot.description`. After the
  flip, no command reads a description line back from the markdown.
- Success criterion for [R4](#r4--journal-first): a
  render from the journal alone restores every description.
