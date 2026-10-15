# 0028 — update sets, changes and clears the repeat of a task

Status: Proposed
Date: 2026-10-13

## Context

Only `add --repeat` writes a `[REPEAT:]` field. `update` names `P`,
`DUE` and `TAGS`, and the bootstrap design deferred `REPEAT`: a changed
repeat reschedules the task at its next completion, which needed a
decision of its own
([DESIGN.md](0000-project-bootstrap/DESIGN.md)). An agent that had to
set, change or remove a repeat had one path: scratch the task
(`done --scratch` since ADR 0027) and add it again. The scratch logs an
abandonment that did not happen, and the new task takes a new id,
which splits the history of one task across two streams
([ADR 0025](0025-reopen-by-update.md) keeps one id per task for the
same reason).

Issue #88 records the owner's decisions: a repeat change leaves `DUE`
as it is, and a cleared repeat lets the next `done` complete the task.

## Decision

**`update --repeat R` sets or changes the repeat of a top-level task,
and `update --repeat None` clears it.** The literal `None`, case
sensitive, removes the `[REPEAT:]` field. btodo reads any other value as
`add --repeat` reads it, and refuses an unreadable value, the empty
string included, before it writes. `DUE` stays as it is: the repeat
takes effect at the next completion. One `TaskUpdated` on the task's
own stream records the change in its delta, as every other `update`
field does. A repeat that the task already carries, or a clear on a
task with none, is no change.

`None` is the clear token of the CLI. `update --description None`
clears the description, as `--description ""` already does, and both
forms stay accepted for the description. `--due` and `--tags` have no
clear form today; when one is added, it takes `None`.

A subtask refuses `--repeat`, as `add --repeat` refuses one on a child.
The owner ruled that a subtask may carry a repeat of its own, and that a
repeating subtask keeps its parent open: the parent closes only after
the repeat of the subtask is removed. A later slice implements that
rule, because the completion of a repeating child changes `Completion`,
which another open PR edits.

## Options considered

### The token `None` clears (chosen)

- an explicit word cannot be confused with an argument left unset or
  emptied by a shell variable [pro]
- `None` never reads as a repeat, so it cannot collide with a valid
  one [pro]
- a value whose whole text is the word `None` cannot be written
  through the option [con]

### The empty value clears, as `--description ""` does

- one convention for every value `update` can remove [pro]
- an empty argument is easy to miss on a command line, and an unset
  variable produces one by accident [con]

### A separate flag, `--no-repeat`

- states the intent with no special value [pro]
- adds a flag per clearable field [con]

### Scratch and add again, the former workaround

- needs no change [pro]
- logs an abandonment that did not happen, and a new id splits the
  history [con]

## Rationale

The owner prefers an explicit token. A clear removes the rule that
reschedules a task at each completion, so the call states that intent.
The empty string also reaches btodo from a variable that expanded to
nothing, and there it would remove a repeat by accident. As an
unreadable repeat, the empty string is refused instead.

One token serves every option that `update` can clear, so an agent
learns one form. The description keeps the empty value as well, because
callers already use it.

The token has one limitation. argparse receives the string that the
shell expanded, so `--description="None"` arrives as `--description
None`, and a description whose whole text is the word `None` cannot be
written through the option. A repeat never reads as `None`, and a
one-word description of `None` carries no meaning, so the project
accepts the limitation.

A repeat is a rule for the next completion, not a date. Changing it
leaves the current `DUE` alone, so `update --repeat` never moves a task
in the ranking, and the next completion is where the rule applies.

## Consequences

- An agent changes a repeat in place, and the task keeps its id, its
  `ADDED` date and its history.
- `update --repeat` on a closed task reopens it with that repeat, as
  every other `update` field does on a reopen.
- A no-op repeat refuses with "nothing to update" when nothing else is
  named, as a `--list` that names the task's own list does.
- The repeating-subtask slice lifts the child refusal and changes the
  rule that the last open child completes its parent.
- A clear form for `--due` or `--tags` is a follow-up, and it takes
  `None`.
- `--loe` stays out of `update`; it is a separate feature.

## Amendment — 2026-10-13

[ADR 0029](0029-subtask-repeat.md) closes the subtask question. A
subtask takes `update --repeat` and `add --repeat`, and the rest of
this decision applies to it unchanged. A repeating subtask keeps its
parent open, and `done` refuses the parent until the repeat is removed.

## Amendment — 2026-10-14

The no-change rule covers every input of `update`, not the repeat
alone. A `P`, `DUE`, `REPEAT` or `TAGS` value that the task holds is no
change, and so are the title and the description that it holds. A clear
of a field or a description that the task does not carry is no change
either. btodo reads each value before it compares it, so a `DUE` in
another ISO form compares as the date it names. The delta records only
the changes, and an update with no change left refuses with "nothing to
update". A reopen applies the same rule
([ADR 0025](0025-reopen-by-update.md)).

## Amendment — 2026-10-15

`update --due None` and `update --tags None` clear their fields, the
clear form that the Decision deferred. btodo decodes the token for
`DUE`, `REPEAT` and `TAGS` in one place and reads it as a value for any
other field, so `-p None` stays refused. `--tags ''` still writes an
empty `[TAGS:]`, which btodo reads as no tags. The no-change rule of
the 2026-10-14 amendment covers both clears.
