# 0021 — A task description is a journaled item field

Status: Proposed
Date: 2026-10-01

## Context

Some tasks want a static description: a fact about the task, not about
any one completion ([R3](REQUIREMENTS.md)).

The lists already hold text of that kind. The parser reads the lines
under a task that carry no checkbox as the task's note lines, every
write keeps them verbatim, and a repeating task keeps them across
cycles. No command writes or shows them, and the journal does not hold
them: the event snapshot carries the title, the done state and the
fields, and no note text.

After the flip
([ADR 0009](../0008-journal-authority/0009-journal-becomes-authoritative.md))
the markdown is a render of the journal. Note lines are state the
journal cannot rebuild, so the first render after the flip would drop
them ([R4](REQUIREMENTS.md)).

## Decision

**A task's description is an item field in the journal, separate from
completion attributes.** `add` sets it and `update` changes it. Each
write records it on the task's own event stream, as the title is
recorded. The renderer writes it as the note lines the parser already
reads. At the flip, existing note lines enter the journal through the
genesis events.

[DESIGN.md](DESIGN.md#task-description) specifies the snapshot key, the
delta, and the render.

## Options considered

### Journaled item field, rendered as note lines (chosen)

- the description becomes state the journal can rebuild [pro]
- the markdown keeps the note-line form the parser already reads [pro]
- a description and a completion record cannot mix [pro]
- the snapshot and the `add` and `update` writes each gain a key [con]

### Keep note lines as unjournaled markdown

- no work; note lines keep working as they do today [pro]
- after the flip the render overwrites them, and their text is lost,
  which fails R4 [con]
- the projection is no longer derivable from the journal alone [con]

### A description attribute on completion events

- one mechanism instead of two [pro]
- a description is a fact about the task, not about one completion,
  which fails R3 [con]
- a repeating task would carry a copy per cycle, and a reader would
  have to pick one [con]

## Rationale

The description and the completion attributes answer different
questions. A completion attribute says what happened on one cycle and
never changes after. A description says what the task is and changes
only when the user edits it. Two mechanisms keep each fact where its
lifetime puts it: the description on the item, the attributes on the
completion ([ADR 0020](0020-completion-attribute-map.md)).

The title already sets the pattern for item text that is not a field.
`update` records a rename on the task's stream, and a reverse-applier
restores it from the delta. The description takes the same path, so
the journal gains a key and no new mechanism.

Rendering to note lines keeps the markdown in the form users and the
parser already know. The flip makes the markdown a render, not a
different file.

## Consequences

- The snapshot gains a description key, and the `update` delta carries
  a changed description beside `title` (DESIGN.md).
- `add` and `update` gain a description option.
- The genesis events at the flip carry existing note lines, so the flip
  loses no note text.
- No completion writes to the description, so a repeating task keeps
  it unchanged across every cycle.
- After the flip, btodo does not read back a hand edit to a note line,
  as for every other line of the projection (ADR 0009).
