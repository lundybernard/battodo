# Event attributes — Requirements

> Author: lundybernard
> Date: 2026-10-01
> Branch: adr-event-attributes
> Issue: #79

## Purpose

Let a user record facts about a task in the journal: facts on any
write, facts about one completion kept once per completion, and a
static description of the task itself. The decisions behind these
criteria are ADRs 0020–0022, and the specification is
[DESIGN.md](DESIGN.md).

## Requirements

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

## Success criteria

- [ ] Two completions of a repeating task, each with different facts,
      leave both sets in the journal (R1)
- [ ] The history of a task lists every completion, newest first, with
      its day and its facts, and `view` output does not change (R2)
- [ ] The history of a finished one-shot task lists its completion
      after the task has left its list (R2)
- [ ] A description set through `add` or `update` survives a completion
      of a repeating task unchanged (R3)
- [ ] A fact under a new key records and reads back without a code
      change (R5)
- [ ] CI green on the final commit
