# 0029 — A subtask may repeat, and keeps its parent open

Status: Accepted (merged 2026-10-13, PR #120)
Date: 2026-10-13

## Context

A `[REPEAT:]` reschedules a top-level task when its completion finishes
it. A subtask could not carry one: `add --repeat` and `update --repeat`
refused it on a child, because btodo rescheduled only the root task.
Some chores need a step with its own interval, for example a monthly
step inside a quarterly chore. [ADR 0028](0028-update-repeat.md) left
that case open.

Checking off the last open child completes its parent (SCHEMA.md). A
child that reschedules does not close, so the design must say what its
completion does to the parent. Issue #88 asked the question, and the
owner ruled on 2026-10-13: a subtask may repeat, a repeating subtask
keeps its parent open, and the parent closes only after the repeat is
removed.

## Decision

**Any task may carry a repeat. The completion of a repeating task
reschedules it in place and finishes no parent.** A repeating subtask
stays open with its next due date, computed from the completion day
as for a top-level task. Its completion logs a DONE record and a
`TaskCompleted` event, as a top-level recurrence does. A subtask has no
add date, so the reschedule writes none. The cascade stops at the
repeating task, so the parent stays open, and a completion of the
last plain sibling leaves it open too.

**`done` refuses a task that has an open repeating subtask at any
depth.** The refusal comes before any write and names the subtask, so
the caller can remove its repeat with `update --repeat None` and then
close the parent. `done --scratch` still drops the whole block: a
scratch completes nothing, so no repeat holds it back. The priority
stays a field of the top-level task alone.

## Options considered

### The repeating subtask holds its parent open (chosen)

- the parent closes only when no step of it recurs [pro]
- a completion never changes a repeat that the caller did not name [pro]
- closing the parent takes one more command per repeating subtask [con]

### The completion of a repeating subtask cascades

- the rule "the last open child completes its parent" stays without an
  exception [pro]
- the parent closes while one of its steps still recurs, so a chore
  leaves the list with work still due [con]

### `done` on the parent clears the repeat of each subtask

- the parent closes in one command [pro]
- a completion silently removes a rule that the caller set, and the
  journal records a change that nobody asked for [con]

### Subtasks keep refusing a repeat

- needs no change [pro]
- a recurring step needs a top-level task of its own, and the relation
  to its chore is lost [con]

## Rationale

A repeating subtask is a step that is never finished for good. Its
parent is complete only when all its steps are, so a step that recurs
keeps the parent open. Cascading would close a chore whose step is
still due, and the closed parent would drop the step with it.

Clearing the repeat on the parent's completion would close the chore,
but it changes a field as a side effect of another command. btodo
writes only what a command names. A refusal that names the subtask and
the command that clears its repeat keeps each change explicit and
costs one extra call.

A scratch abandons the block. It completes nothing, so the repeat of a
step does not concern it.

## Consequences

- An agent sets, changes and clears the repeat of a subtask with the
  same options as for a top-level task.
- The completion of a repeating subtask leaves its parent open. The
  parent's `done` exits 1 while the repeat stays.
- The refusal also covers a repeating top-level task: its own
  completion reschedules it only when no subtask below it repeats.
- The reschedule of a repeating task drops its children, at any depth,
  as the top-level reschedule already does.
