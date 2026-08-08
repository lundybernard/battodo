# BatTodo — Requirements

> Author: lundybernard
> Date: 2026-08-07
> Branch: main

## Purpose

Rebuild the plain-text todo system in `~/todo/` (markdown lists, three
helper scripts, and a Claude Code skill) as an installable Python CLI:
**BatTodo**, commands `btodo` and `btd`. The app is a personal tool built
fast and loose.

## Requirements

### R1 — Installable package with CLI entry points
`pip install`-able package `battodo` exposing console commands `btodo`
and `btd` (alias, same callable), built on argparse using the BAT CLI
pattern.

### R2 — Parse the existing list format
Parse todo lists in the current `~/todo/SCHEMA.md` format: task lines
with `[P:N]`, `[LOE:N]`, `[DUE:YYYY-MM-DD]`, `[BUMPED:YYYY-MM-DD]`,
`[REPEAT:...]` (interval `Nd`/`Nw` and schedule `weekly:DAY`/`monthly:N`
variants), `[TAGS:...]`; subtask hierarchy (2-space indent, LOE/DUE only)
vs checklist items (no fields); a node has either subtasks or a
checklist, never both.

### R3 — Views
Render open items as sorted tables: P desc, then nearest DUE, no-DUE
after dated. `top`/`top N`/`all` views. Category time windows
(work/chores blocking rules, Pacific time) filter the default view.
Completed and future-recurring items are hidden.

> Sort criteria amended by [ADR 0005](0005-computed-rank.md): computed
> rank desc, then nearest DUE. Output parity with `view_todos.py` no
> longer applies — the order is intentionally different.

### R4 — Daily bump
Once per day, every open item with `DUE <= today` or no `DUE` gets
`P += 1` and `BUMPED: today`. Must operate on **all discovered lists** —
fixes the current bug where `bump_priorities.py` / `view_todos.py`
hard-code five category files and silently skip `backlog.md` and other
ad-hoc lists.

> Superseded by [ADR 0005](0005-computed-rank.md). Overdue items still
> climb, but by computation at view time rather than a stored,
> accumulated `P`. There is no daily mutation and no `bump` command.

### R5 — Mutations
`add`, `done`/`complete`, `scratch`, `bump` operations implementing
SCHEMA.md rules: completed.md logging with `Parent > Child` ancestry,
block removal only when fully done, REPEAT recompute
(interval-from-completion vs fixed-calendar-schedule), scratch logged
only for items accepted in a prior session.

### R6 — Composable list sources
Views and operations merge multiple list sources: the personal
home-directory list, explicitly configured lists in shared/synced
directories, and lists auto-discovered from the working directory when
inside a project that carries one. (Source discovery/merge semantics are
part of the open storage design, ADR 0004.)

### R7 — Configuration via batconf
All configuration (list source paths, time windows, category rules) goes
through batconf's layered lookup.

### R8 — SessionStart hook parity
`btodo` can replace `view_todos.py` in the Claude Code SessionStart hook
with equivalent (or better) output, including running the daily bump
first.

### R9 — Tests
unittest-based test suite per the user's python-style conventions;
unit-test coverage gates the build.

## Success criteria

- [ ] `btodo` / `btd` installed and answering `--help`
- [ ] Item *selection* parity with `view_todos.py` on the live `~/todo/`
      data (ordering diverges by design, per ADR 0005)
- [ ] Ad-hoc lists (`van-upgrades.md`) are no longer silently skipped,
      and lists that declare themselves parked (`backlog.md`) stay out
      of the daily view — both bugs fixed
