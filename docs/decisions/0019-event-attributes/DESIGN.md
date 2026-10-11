# Event attributes — Design

> Author: lundybernard
> Date: 2026-10-01
> Branch: adr-event-attributes

The specification behind ADRs
[0020](0020-event-attribute-map.md),
[0021](0021-task-description-field.md),
[0022](0022-history-command.md) and
[0023](0023-note-event.md). It extends the event vocabulary of
[DESIGN.md ## Journal](../0000-project-bootstrap/DESIGN.md#journal).
The work lands before the journal-authority flip; the group README's
[After the flip](README.md#after-the-flip) lists the part that waits
for it.

## Command surface

```text
btodo add <list> <title> [--description TEXT] [--attrs ATTRS] [--note TEXT] ...
btodo update <selector> [--description TEXT] [--attrs ATTRS] [--note TEXT] ...
btodo done <selector> [--attrs ATTRS] [--note TEXT] [--date DATE]
btodo scratch <selector> [--attrs ATTRS] [--note TEXT]
btodo note <selector> [TEXT] [--attrs ATTRS]
btodo history <selector> [--format text|json]
```

`--attrs` takes every attribute in one string. `--note TEXT` enters the
map as `note=TEXT`. The `TEXT` of `note` is its note
([Note event](#note-event)).

**Inputs.** The selector, `--date`, `--attrs` and `--note` are command
inputs, not configuration. The CLI passes them to the command beside
`conf`, under the convention of ADR 0024.

## Event attributes

**Grammar.** `--attrs` takes one string of `key=value` segments:
`--attrs='k=v, k=v'`. The string splits only at a comma followed by
`key=`, where the key is a lowercase identifier: a letter, then
letters, digits or underscores. A value may therefore hold `=` and
commas. `--attrs='place=Main St, Suite 4, cost=45.00'` gives `place`
the value `Main St, Suite 4` and `cost` the value `45.00`.

`--note TEXT` is sugar for the key `note`. Its text enters the map as
`note=TEXT` and never runs through the split.

**Refusals.** The command refuses each of these before it writes
anything, as `add` validates before it writes:

- a key given twice, including `note=` in `--attrs` beside `--note`, or
  beside the `TEXT` of `note`
- an empty value
- a line break in a key or a value
- a segment with no `=`
- a key outside the grammar

**Payload.** `payload.attrs` holds the attributes as a JSON object of
string keys to string values, on every event type. The key is absent
when the event carries no attributes.

`TaskCompleted.payload.completed_on` holds the local day the completion
is for, as an ISO date: the `--date` value when the user gives one, the
clock's local day otherwise. Every event of a cascade carries it.
`occurred_at` keeps the time the command ran.
[ADR 0010](../0008-journal-authority/0010-event-ordering-key.md) makes
`occurred_at` the ordering key, so a backdated `occurred_at` would
reorder the journal. The completion day is therefore a payload key of
its own.

**Reschedule.** The reschedule of a repeating task reads `completed_on`
as its anchor, so the day on the event and the new `DUE` agree. A
`TaskCompleted` that reschedules its own stream carries the `DUE`
change in its delta, so a reader finds the new `DUE` from the event
alone. The rescheduling node is one property of the completion: today
it returns the root, and a later slice, subtask schedules, changes
which node it returns.

```json
{
  "type": "TaskCompleted",
  "stream_id": "task/3usdig",
  "payload": {
    "delta": {
      "done": [false, true],
      "DUE": ["2026-10-01", "2026-11-01"]
    },
    "snapshot": {
      "title": "Renew the parking permit",
      "done": false,
      "fields": {
        "DUE": "2026-10-01",
        "REPEAT": "monthly:1",
        "ID": "3usdig"
      }
    },
    "ancestry": "Renew the parking permit",
    "completed_on": "2026-10-01",
    "attrs": {
      "confirmation": "A1B2C3",
      "cost": "45.00",
      "note": "Renewed online"
    }
  }
}
```

Envelope fields not shown are as the bootstrap DESIGN.md tables them.

**Versioning.** Both keys are additive, and an event without them stays
valid. A reader treats a missing `attrs` as an empty map, and a missing
`completed_on` as the local day of `occurred_at`. The bootstrap
DESIGN.md states that additive envelope fields do not need a
`schema_version` bump, and its `TaskAdded` payloads already carry a key,
`backfilled`, whose absence readers tolerate. This design extends that
rule to the two payload keys: `schema_version` stays `1`.

**Cascade.** A completion that finishes an ancestor writes one event per
finished task
([ADR 0014](../0014-subtask-journal-events.md)). The attributes go on
the event of the task the user named. Each ancestor event that the
cascade writes carries `completed_on` and no `attrs`.

**Checklist items.** A checklist item carries no `[ID:]`, so its events
go on the stream of its nearest ancestor that has one, with the item
named in the event's `ancestry`. A checklist item takes no attributes.
Its events carry a checklist marker, so a reader tells them apart from
the ancestor's own events.

**Completed log.** Completion attributes appear in the completed log.
The log is a render of the journal: its records derive from journal
events, and btodo never rebuilds journal state from the log. The record
line carries the attributes of its completion, after the SCHEMA.md
fields, as one block that holds a JSON object in ASCII:

```text
2026-10-01 | errands | DONE | Renew the permit [attrs:{"cost": "45.00"}]
```

The digest reader takes the block off before it reads the title. The
block starts at the first `[attrs:` from which the rest of the line
reads as a JSON object of text values and a closing `]`. JSON escapes
every quote and every line break in a value, so a title or a value may
hold `|`, `=`, commas and brackets. A record without attributes carries
no block and reads as before. A cascade ancestor's record carries none.
A SCRATCHED record carries the attributes of its scratch the same way.

## Note event

**Event.** `TaskAnnotated` goes on the stream of the task the user
named. Its payload carries `attrs` and no `delta`. `occurred_at` dates
the note, and `note` takes no `--date`.

**Write.** The write object `Annotation` builds the event, and the
`lib` entry point `annotate_item` writes it. The selector reaches an
open task. A task without an `[ID:]` gets its id stamped first, on an
event of its own, as a subtask add stamps its parent.

**Input.** `note` takes a positional `TEXT` and `--attrs`, and no
`--note`. `TEXT` is the note: it enters the map as `note=TEXT` and
never runs through the split. `note` refuses a call with no `TEXT` and
no `--attrs` before it writes anything.

## Task description

**Snapshot.** The snapshot gains `description`: the text of the task's
description lines, one line of text per description line, joined by
newlines. btodo stores each line stripped, without its indent. The key
is absent when the task has no description.

**Writes.** `add --description` sets it. Like the title, it does not
appear in an `add` delta; the post-state snapshot carries it.
`update --description` changes it, and `TaskUpdated.delta.description`
records the change as `[before, after]`. It is a pseudo-key on the same
footing as `title`: not a field, but a value a reverse-applier needs.
`update --description ''` clears it, and the delta records the change
as `[before, null]`.

**Refusals.** `add` and `update` refuse a description before any write
when one of its lines:

- is blank
- matches the checkbox pattern
- starts with `##` and a space, or with `<!--`
- holds `\r`

**Scope.** A subtask may carry a description. A checklist item may not.

**Render.** The renderer writes the description lines directly under
the task line and before its children, at the task's indent plus the
field indent, in the form the parser already reads
([DESIGN.md ## Parser](../0000-project-bootstrap/DESIGN.md#parser)).

**Show.** `show` gains a description row, and `show --format json` a
`description` key.

**Recurrence.** A repeating task keeps its description lines when it is
rescheduled; `complete` drops the children of a rescheduled task, not
its description lines. The description survives each completion
unchanged, and no completion writes to it.

## History command

**Selector.** `history` resolves its selector against the journal, not
the markdown. An `[ID:]` names a stream. A case-insensitive part of a
title matches against the current title of each stream, the snapshot
title with the title deltas applied, and must match exactly one stream.
A finished one-shot task stays reachable after its block leaves the
list. A task with no stream is an error.

**Text output.** A header line with the task's title and `[ID:]`, then
one entry per completion on the stream and one per other event that
carries attributes. Each entry shows its kind, its day, and each
attribute as `key=value`, in recorded order. The kind is the event
type; the checklist marker labels the completion of a checklist item.
A completion's day is `completed_on`; any other entry's day is the
local day of `occurred_at`. Entries run newest first by day; journal
order ([ADR 0010](../0008-journal-authority/0010-event-ordering-key.md))
breaks ties. A stream with no entries gives the header and an empty
list.

**JSON output.** `--format json` serializes the document that the text
format lays out, as `show --format json` does.

## Show

**Notes.** `show` lists the notes of the task's current cycle: every
note that the stream's events carry after its last completion, newest
first, each with its day. `show --format json` gains a `notes` key.
`view` does not change.
