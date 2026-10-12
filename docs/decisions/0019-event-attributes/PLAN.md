# Event attributes — Plan

> Author: lundybernard
> Date: 2026-10-11
> Branch: adr-event-attributes
> Issue: #79

Implements ADRs [0020](0020-event-attribute-map.md),
[0021](0021-task-description-field.md),
[0022](0022-history-command.md) and [0023](0023-note-event.md) against
the criteria in [REQUIREMENTS.md](REQUIREMENTS.md), to the
specification in [DESIGN.md](DESIGN.md).

## How the sequence is chosen

One slice is one PR. A slice starts when the slices it needs have
merged. Two pieces of work outside this group fit into the sequence:
the CLI split and subtask schedules.

| Slice | Needs | Status |
| ----- | ----- | ------ |
| S1a — completion event payload | — | In progress (#90) |
| CLI split (ADR 0024) | — | In progress, parallel PR |
| S1b — attributes on every write event | S1a, CLI split | In progress |
| S2 — note event and command | S1b | Planned |
| S3 — history command | S2 | Planned |
| S4 — notes in `show` | S3, subtask schedules | Planned |
| S5 — attributes in the completed log | S1b | Planned |
| S6 — task description | — (runs before #88) | In review |

Subtask schedules (owner design, 2026-10-11) run after S1a and before
S4. #88 runs after subtask schedules and after S6.

## S1a — Completion event payload

Completion events gain `completed_on` and the checklist marker, and
the completion gains the rescheduling-node property
([DESIGN.md](DESIGN.md#event-attributes)). The reschedule reads
`completed_on` as its anchor. In progress in #90.

## CLI split (ADR 0024)

Command inputs (the selector, `--date`, `--attrs`, `--note`) stop
passing as configuration and pass to the command beside `conf`. ADR
0024 lands in a parallel PR and sets the convention.

## S1b — Attributes on every write event

`add`, `update`, `done` and `scratch` gain `--attrs` and `--note`, and
each event they write carries `payload.attrs`
([ADR 0020](0020-event-attribute-map.md)). The grammar and the
refusals are in [DESIGN.md](DESIGN.md#event-attributes).

## S2 — Note event and command

The `TaskAnnotated` event, the `Annotation` write object, the
`annotate_item` entry point and the `note` command
([ADR 0023](0023-note-event.md)).

## S3 — History command

The `history` command over the journal
([ADR 0022](0022-history-command.md)).

## S4 — Notes in show

`show` lists the notes of the current cycle, and its JSON gains a
`notes` key ([DESIGN.md](DESIGN.md#show)).

## S5 — Attributes in the completed log

The completed log builds each entry from its completion event, and the
entry carries the attributes. The digest reader changes in the same
slice ([DESIGN.md](DESIGN.md#event-attributes)).

## S6 — Task description

The `description` snapshot key, `--description` on `add` and `update`,
the refusals, the render and the `show` row
([ADR 0021](0021-task-description-field.md)). S6 does not depend on
another slice. It changes `Update`, as #88 does, so S6 runs first and
issue #88 follows it.

## After the flip

Two items wait for the journal-authority flip. The group README lists
them under [After the flip](README.md#after-the-flip).

## Issue tracker

- #79 tracks the group.
- #90 is the S1a PR.
- #88 adds commands to set, change and clear the repeat of a task, and
  shares `Update` with S6.
- #52 records that command inputs reach the configuration object
  undeclared.
