# 0022 — A history command reads the journal

Status: Proposed
Date: 2026-10-01

## Context

Completion attributes ([ADR 0020](0020-completion-attribute-map.md))
leave a per-completion history in the journal. A details view must list
that history for one task, and the ranked view must not show it
([R2](REQUIREMENTS.md)).

Two existing surfaces read one task or many, and neither reaches the
history:

- `show` reads one task from the markdown. Its selector reaches open
  tasks only, and a finished one-shot task leaves its list when its
  block goes, so `show` cannot name it.
- `view` ranks open tasks, one row each, and R2 keeps history out of
  it.

After the flip
([ADR 0009](../0008-journal-authority/0009-journal-becomes-authoritative.md))
the journal is the record and the markdown a render of it. The history
exists in the journal and nowhere else.

## Decision

**A `history` command lists one task's completion events from the
journal.** It shows them newest first, each with its day and its
attributes. It resolves its task from the journal, so it reaches a
finished one-shot task that no longer appears in any list. `show` and
`view` do not change.

[DESIGN.md](DESIGN.md#history-command) specifies the selector and the
output.

## Options considered

### A `history` command over the journal (chosen)

- reads the record, not a render of it [pro]
- reaches finished tasks, which only the journal still holds [pro]
- leaves `view` and `show` as they are [pro]
- one more command, with a selector that resolves against the journal
  instead of the markdown [con]

### Extend `show` as the only surface

- one command per task and no new name to learn [pro]
- its selector reaches open tasks only, so finished tasks stay out of
  reach [con]
- it reads the markdown, which holds no history [con]

### Render the history under the item in the markdown

- the history shows wherever the list is read [pro]
- the block of a repeating item grows without bound [con]
- the markdown is a render, not the record, so the history becomes a
  second copy of the journal [con]

## Rationale

The history is a journal fact, and the command that shows it reads the
journal. Both alternatives route it through the markdown. `show` reads
the markdown and so sees only open tasks. A rendered history makes the
markdown carry a growing copy of what the journal already holds, and
the item that repeats most grows the longest block.

A separate command also keeps the details out of the ranked view,
which is the split R2 asks for.

## Consequences

- `history` is the first command that resolves a task from the journal
  rather than from the markdown. DESIGN.md states its selector.
- `history` depends on the flip. Before it, a completion made by hand
  edit writes no event, so a history read from the journal would miss
  it.
