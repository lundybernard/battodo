# 0014 — Subtask journal events

Status: Proposed
Date: 2026-08-17

## Context

Subtask `add` and `update` are entering the CLI. Until now btodo mutated
top-level tasks only, so hierarchy never reached the journal.

The delta contract
([DESIGN.md ## Journal](0000-project-bootstrap/DESIGN.md)) requires an
event for every mutation.
[ADR 0009](0008-journal-authority/0009-journal-becomes-authoritative.md)
is accepted, so after the flip the markdown is a projection of the
journal: a fact the events cannot reconstruct is a fact that is lost.

Hierarchy is such a fact. The file states it as indentation. A subtask
write that records the child but not its parent leaves the projection
unable to rebuild the tree.

## Decision

Every task carries a unique `[ID:]`, subtasks included, stamped at
creation by subtask add.

The parent/child relation is recorded in one place only: the event
payload, as the parent's id. Subtask add derives it from the indentation
of the line it writes. Markdown gets no `PARENT` field.

One event per affected task stream, never one event for several tasks.
When subtask add must stamp an `[ID:]` onto a parent line that has none,
that write gets a minimal id-assigned event on the parent's own stream.

## Options considered

### Parent-by-id in the event payload (chosen)

- hierarchy keeps one home in the file and one in the journal, and the
  two cannot disagree [pro]
- the projection rebuilds the tree from events alone [pro]
- the parent's id must exist at write time, which forces the extra
  id-assigned event [con]

### A `[PARENT:]` field in the markdown

- explicit; no derivation step at write time [pro]
- a second copy of the hierarchy, which contradicts the indentation the
  first time a line moves, with no rule for which copy wins [con]
- a grammar addition every reader and every hand-editor must honour
  [con]

### One aggregate event covering several items

- a subtask add that also stamps its parent stays a single event [pro]
- breaks the per-stream model: a task's stream no longer holds every
  change to that task [con]
- reverse-apply and merge need per-item unpacking that no other event
  type requires [con]

### Stamp the parent, emit no event

- the smallest change; the stamp is bookkeeping, not user state [pro]
- a carve-out in the delta contract: post-flip the parent's id exists in
  the file and nowhere in the log [con]

### Require `backfill` before subtask add

- every parent already has an id, so no stamping case exists [pro]
- friction on the user, and a new error path for the run they skip
  [con]

## Rationale

Indentation is already the file's statement of hierarchy, and the
round-trip guarantee keeps it verbatim. A second statement of the same
fact is a statement that can disagree with the first. Deriving the
relation at write time reads the source the human reads.

The alternatives that avoid the parent's id-assigned event are cheap now
and expensive after the flip. ADR 0009's exit guarantee runs both ways:
deleting the journal must lose only history, and the projection must be
derivable from the journal alone. An unlogged stamp breaks the second
half. A mandatory backfill pays the same cost in user friction instead.

## Consequences

- One subtask add can write two events: the child's, and an id-assigned
  event on the parent when that line had no id.
- Every journal reader handles the id-assigned event type.
  [DESIGN.md ## Journal](0000-project-bootstrap/DESIGN.md) carries its
  name and payload shape.
- Hierarchy is derivable from the journal, so the flip needs no separate
  hierarchy migration.
- Lazy `[ID:]` injection now reaches child lines. The `update` rule that
  refuses nested targets
  ([DESIGN.md](0000-project-bootstrap/DESIGN.md)) is untouched — what
  promotes a fieldless checklist item stays open.
- A hand edit that re-indents a line still produces no event. That gap
  closes with the flip, not here.
