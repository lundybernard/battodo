# 0030 — Every indented child is a subtask

Status: Proposed
Date: 2026-10-25

## Context

An indented child line under a task is one of two things. A subtask
carries fields. A checklist item carries none. `TaskNode.is_subtask` in
`battodo/parser.py` tells them apart, and no production code reads it.
The owner's four live lists hold 18 fieldless children.

The two kinds take two paths through the parser, the views, and the
journal. The completion of a checklist item writes no log record, so
an empty `Task.completed` reads two ways: the task never closed, or it
is a checklist item. Issue #40 reports that ambiguity.

## Decision

**btodo drops the checklist concept. Every indented child is a
subtask.** A fieldless child is promoted: the parser reads it as a
subtask with no fields, and the next write that touches it stamps it
as `add` stamps a new subtask. `TaskNode.is_subtask` and its tests
leave with the concept. The list-format contract, SCHEMA.md, drops its
checklist line.

## Options considered

### Drop the concept: every child is a subtask (chosen)

- one kind of child keeps the parser, the views, and the journal to
  one case [pro]
- every completion of a child writes a log record, so an empty record
  means one thing [pro]
- the first write that touches a fieldless child adds a field to a line
  that a person wrote by hand [con]

### Keep both concepts with distinct syntax

- a line states its kind by its syntax, with or without fields [pro]
- every reader keeps two cases, and the list format gains a construct
  [con]

### Keep the checklist as a view-only child

- a quick step stays plain text and never enters the journal [pro]
- its completion still leaves no history, so the ambiguity that issue #40
  reports stays [con]
- the views still carry a second kind of child [con]

## Rationale

Subtasks cover every use of a checklist item, and they add fields,
scheduling, and journal history. One kind of child keeps the parser,
the views, and the journal to one case. Each alternative keeps a second
kind of child, and with it a second case in every reader. A checklist
returns later as a task template (issue #27) whose items are subtasks.

## Consequences

- Issue #40 closes on this ADR.
- The parser change lands in a later PR.
