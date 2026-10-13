# 0026 — A due-date factor on the priority

Status: Proposed
Date: 2026-10-13

## Context

[ADR 0005](0000-project-bootstrap/0005-computed-rank.md) ranks a task as
`P × (1 + age_score + due_score)`. The due term is additive. It is 0 at
a fortnight or more before the due date, so a due date far away does
not lower a task, and a task near its due date gains at most one
multiplier's worth.

The view also hides every open recurring task with a future `DUE`
(R3). A recurring task then gives no warning: it is invisible until the
day it is due, and it appears at full urgency on that day. Four
prescription refills added with `--repeat 90d` showed the defect: three
of them were due 10 to 21 days ahead, and no view showed them
([#58](https://github.com/lundybernard/battodo/issues/58)).

The owner wants the due date to act on the priority as a multiplier.
The factor is below 1 for a task far from its due date, rises as the
date comes nearer, and keeps rising after the date passes. With that
factor in place, the view does not need to hide a task.

## Decision

`rank.py` multiplies the priority by a due-date factor:

```text
rank = P × due_factor × (1 + age_score)
```

`P` and `age_score` keep their ADR 0005 definitions. `due_factor` is a
piecewise-linear curve over `days = today − due`. The day axis reads as
a launch countdown: a negative day is before the due date, 0 is the due
date, and a positive day is past it. The default curve:

| `days` | Meaning | `due_factor` |
| ------ | ------- | ------------ |
| no `DUE`, or unreadable | undated | 1.0 |
| −30 and below | a month or more ahead | 0.5 (floor) |
| −30 … −7 | the month before | 0.5 rising to 1.0 |
| −7 … 0 | the week before | 1.0 rising to 2.0 |
| 0 … 14 | overdue | 2.0 rising to 4.0 |
| 14 and above | two weeks or more late | 4.0 (cap) |

The curve is the configuration value `view.rank_due_curve`, a string of
comma-separated `days:factor` points. Its default,
`-30:0.5, -7:1.0, 0:2.0, 14:4.0`, is the one source of these numbers.
The curve holds the first point's factor below the first point and the
last point's factor above the last point. A string that does not decode
is a configuration error.

The view shows every open top-level task. The suppression of recurring
tasks with a future `DUE` goes, and the factor takes its place: a
recurring task far from its due date ranks low but stays visible.

`ASAP` is not a `DUE` value, and `DUE` stays a date. A task wanted at
once takes today's date as `DUE` and keeps its own `P`.

## Options considered

### A multiplicative factor with a floor (chosen)

- A far due date lowers a task, and a near one raises it, in the same proportion
  at every priority [pro]
- The floor keeps a task visible however far off its date is [pro]
- One factor replaces both `due_score` and the view suppression [pro]
- Every dated rank changes scale, so the owner retunes the curve against the
  live view [con]

### Keep the additive `due_score` and the suppression

- No rank changes, and no requirement changes [pro]
- A recurring task stays invisible until it is due, which is the defect in #58
  [con]

### A factor that falls toward 0 far from the due date

- A task a year off ranks near the bottom of every list [pro]
- A task far off ranks as low as a parked `P:0` task, so it drops out of the top
  of every list and the view hides it again [con]
- The curve needs a decay constant that has no meaning to the owner [con]

### An `ASAP` value for `DUE`

- One word marks a task as wanted at once [pro]
- `DUE` stops being a date, so every reader of the field needs a second case
  [con]
- A due date of today with the task's own `P` says the same thing [con]

## Rationale

ADR 0005 made `P` a multiplier so that urgency cannot bury priority.
An additive due term works against that: it adds the same amount to a
`P:1` task and to a `P:5` task. A multiplier scales both by the same
proportion, and the bounded curve keeps the ADR 0005 property that
no term grows without limit.

The far end takes a floor of 0.5. A task a month or more away ranks
at half its undated rank. It sinks, but it stays in
the view, so the view needs no rule of its own to hide it.

The curve is configuration because its points are tuning values. The
owner moves them after reading the live view, and a value in the config
file changes without a release. Every configuration value is a string
([ADR 0007](0007-toml-config-file.md), amendment of 2026-09-19), so the
curve is a string that the rank module decodes.

## Consequences

- A task far from its due date ranks at half the rank of the same task
  with no `DUE`.
- A recurring task shows in the view from the day it is rescheduled.
  It starts at the floor and climbs as its next due date comes nearer.
- Every dated rank changes scale. The owner retunes
  `view.rank_due_curve` by reading the view.
- The `hidden` count of the JSON view is unchanged. The item limit
  feeds it, not the suppression, so it now counts every open task the
  view leaves out.
- R3 is amended: the view shows every open task.
- The live SCHEMA.md describes the old rank and the suppression. Its
  owner updates it; this project does not edit it.
