---
name: battodo
description: Operate the btodo todo-list CLI — read ranked views, add, update, complete and scratch tasks and subtasks, and digest completed work. Load whenever a todo list is read or changed.
---

# BatTodo

`btodo` owns the todo lists. Read them and change them through the CLI.
This file ships with the project; link it into an agent's skills
directory to load it.

## Rules

- Never hand-edit the markdown lists. Every change goes through
  `btodo`, so the journal records it. A hand edit produces no event and
  does not survive the next render of the list.
- Parse `--format json`. Never scrape the text table: it is laid out
  for a human terminal and its columns move with the content.
- Errors print to stderr and the exit code is 1. stdout carries the
  command output and nothing else. Branch on the exit code.
- Rank is computed at read time from priority, age and due date.
  Nothing is written to keep a rank current, and there is no `bump`
  command.

## Read

```
btodo view                            # open items, active categories
btodo view --top 10                   # more items a category; default 5
btodo view --all                      # every open item, every category
btodo view --format json              # the same selection as JSON
btodo show <selector>                 # one item: its fields and subtasks
btodo show <selector> --format json
btodo completed [today|week|month] [--format text|json]
```

`completed` reads the completed log for one period, DONE records only.
`today` is the local day, `week` is seven days ending today, and
`month` reaches back to the first of the month. The period defaults to
`week`.

The `view` JSON schema is documented in
[README.md](README.md#machine-readable-output). It grows by addition:
new keys appear, existing keys keep their meaning. Read each task array
in the order given rather than re-sorting by `rank`, and read `hidden`
to learn how many open items the selection left out.

## Write

```
btodo add <list> <title> [-p N] [--loe N] [--due YYYY-MM-DD]
                         [--repeat R] [--tags a,b]
btodo add <list> <title> --parent <selector>
btodo update <selector> [-p N] [--due YYYY-MM-DD] [--tags a,b]
                        [--title TITLE]
btodo done <selector> [--date YYYY-MM-DD]
btodo scratch <selector>
```

- `<list>` is a filename stem: `chores` for `chores.md`.
- `-p` is the priority multiplier, 0 and up. `--loe` is the level of
  effort: 1, 2, 3, 5 or 8. `--repeat` is `Nd`, `Nw`, `weekly:DAY` or
  `monthly:N`. `--tags` is a comma-separated list.
- Give the title without `[FIELD:]` markup. Fields go in through their
  own options.
- `add` echoes the line it wrote and the file it wrote to. A task with
  no `-p` ranks near zero and does not appear in a view, so read that
  echo to confirm the write.
- `done` completes the task and logs it. `scratch` drops the task and
  logs it as abandoned. `completed` counts only the first, so pick the
  one that states what happened.
- `done --date` logs the completion under the day the work finished,
  rather than the day it is marked off. A repeating task is rescheduled
  from that day too.
- Checking off the last open child completes its parent.

## Selectors

A selector is the task's `[ID:]` value, or any part of its title, case
insensitive. An exact id wins over a title match. The search covers
every open task at every depth, in every list, parked lists included.

A selector that matches nothing, or more than one open task, is an
error. The message names the candidates. Narrow the selector, or take
the id from `--format json` output.

## Subtasks

- `add --parent <selector>` files the new task under its parent, in the
  same list.
- `update`, `done`, `scratch` and `show` reach a task at any depth.
- `-p` and `--repeat` are refused on a child. Only a top-level task
  carries a rank, and only the root task is rescheduled.
- A checklist item is a child line with no fields. It cannot be a
  parent and it cannot be updated: writing a field to it would promote
  it to a subtask.

## Configuration

The source directory holds the lists. It defaults to `~/todo`.
Override it with `BATTODO_VIEW_SOURCE_DIR`, or set `view.source_dir` in
a config file.

The config file is resolved in this order:

1. the path given to `--conf`,
2. the path in `$BATTODO_CONFIG_FILE`,
3. `./battodo.toml`,
4. `$XDG_CONFIG_HOME/battodo/config.toml`, or
   `~/.config/battodo/config.toml` when that variable is unset.

Finding no config file is normal. Defaults and environment variables
answer on their own. A file named by `--conf` or `$BATTODO_CONFIG_FILE`
must exist; the searched paths (3, 4) are optional.
