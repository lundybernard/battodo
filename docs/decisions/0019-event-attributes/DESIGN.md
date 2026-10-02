# Event attributes — Design

> Author: lundybernard
> Date: 2026-10-01
> Branch: adr-event-attributes

The specification behind ADRs
[0020](0020-completion-attribute-map.md),
[0021](0021-task-description-field.md) and
[0022](0022-history-command.md). It assumes the journal is
authoritative
([ADR 0009](../0008-journal-authority/0009-journal-becomes-authoritative.md))
and extends the event vocabulary of
[DESIGN.md ## Journal](../0000-project-bootstrap/DESIGN.md#journal).

## Command surface

```text
btodo done <selector> [--attr KEY=VALUE]... [--note TEXT] [--date DATE]
btodo add <list> <title> [--description TEXT] ...
btodo update <selector> [--description TEXT] ...
btodo history <selector> [--format text|json]
```

`--attr` repeats. `--note TEXT` is shorthand for `--attr note=TEXT`.

## Completion attributes

**Grammar.** An attribute splits on its first `=`. The key is a
lowercase identifier: a letter, then letters, digits or underscores.
The value is text and may hold `=`. `done` refuses an attribute with no
`=` or a key outside the grammar before it writes anything, as `add`
validates before it writes.

**Payload.** `TaskCompleted.payload.attrs` holds the attributes as a
JSON object of string keys to string values. The key is absent when the
completion carries no attributes.

`TaskCompleted.payload.completed_on` holds the completion day as an ISO
date in the user's local day: the `--date` value when the user gives
one, today otherwise. `done --date` reaches the completed log today but
not the event. The event carries the time the command ran, as
`occurred_at`, and no completion day.
[ADR 0010](../0008-journal-authority/0010-event-ordering-key.md) makes
`occurred_at` the ordering key, so a backdated `occurred_at` would
reorder the journal. The completion day is therefore a payload key of
its own.

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
the target's event only. An ancestor that the cascade completes gets
none.

**Completed log.** Completion attributes appear in the completed log.
The log is a render of the journal: its records derive from journal
events, and btodo never rebuilds journal state from the log. The record
line carries the attributes of its completion. Today the digest reader
splits a record into four fields on the first three separators, folds
the rest into the title, and strips `[FIELD:]` markup from that title,
so attributes on the line would read as title text or vanish. The
implementing work sets the attribute syntax on the line and changes the
reader in the same change. The four-field split is a render detail, not
a compatibility constraint.

## Task description

**Snapshot.** The snapshot gains `description`: the text of the task's
note lines, one line of text per note line, joined by newlines. The key
is absent when the task has no description.

**Writes.** `add --description` sets it. Like the title, it does not
appear in an `add` delta; the post-state snapshot carries it.
`update --description` changes it, and `TaskUpdated.delta.description`
records the change as `[before, after]`. It is a pseudo-key on the same
footing as `title`: not a field, but a value a reverse-applier needs.

**Render.** The renderer writes the description as note lines under the
task line, in the form the parser already reads
([DESIGN.md ## Parser](../0000-project-bootstrap/DESIGN.md#parser)).

**Recurrence.** A repeating task keeps its note lines when it is
rescheduled; `complete` drops the children of a rescheduled task, not
its notes. The description survives each completion unchanged, and no
completion writes to it.

**Flip.** The importer that writes genesis events at the flip
([ADR 0009](../0008-journal-authority/0009-journal-becomes-authoritative.md))
reads existing note lines into `snapshot.description`. After the flip,
no command reads a note line back from the markdown.

## History command

**Selector.** `history` resolves its selector against the journal, not
the markdown. An `[ID:]` names a stream. A case-insensitive part of a
title matches against the latest snapshot title of each stream and must
match exactly one stream. A finished one-shot task stays reachable
after its block leaves the list.

**Text output.** A header line with the task's title and `[ID:]`, then
one entry per `TaskCompleted` event on the stream. Each entry shows the
completion day and each attribute as `key=value`, in recorded order.
Entries run newest first by completion day; journal order
([ADR 0010](../0008-journal-authority/0010-event-ordering-key.md))
breaks ties.

**JSON output.** `--format json` serializes the document that the text
format lays out, as `show --format json` does.

## Open questions

- **Checklist item completions.** A checklist item carries no `[ID:]`,
  so its completion event goes on the stream of its nearest ancestor
  that has one, with the item named in the event's `ancestry`. That
  stream then holds completion events for the item beside the
  ancestor's own. Whether the item's completion takes attributes, and
  how `history` tells the two kinds of entry apart, is open.
- **A key given twice.** `--attr` given twice with one key, or `--note`
  beside `--attr note=`: refuse, or keep the last value. Issue #67
  records the same question for markdown fields.
