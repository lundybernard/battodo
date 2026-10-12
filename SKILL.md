---
name: battodo
description: Operate the btodo todo-list CLI — read ranked views, add, update, complete and scratch tasks and subtasks, record attributes and notes, read a task's history, and digest completed work. Load whenever a todo list is read or changed.
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
- A refusal or a config error prints one line to stderr and exits 1.
  An argparse usage error (an unknown option, a missing argument, a
  choice outside the list) prints the usage text and the error to
  stderr and exits 2. stdout carries the command output and nothing
  else. Branch on the exit code.
- Rank is computed at read time from priority, age and due date.
  Nothing is written to keep a rank current, and there is no `bump`
  command.
- Name a task to a human by its title. The `[ID:]` value is a random
  key for commands and for an agent's own notes; it means nothing to
  the reader. Shorten a long title; add the list name when it helps.

## Read

```text
btodo view                            # open items, active categories
btodo view --top 10                   # more items a category; default 5
btodo view --all                      # every open item, every category
btodo view --format json              # the same selection as JSON
btodo show <selector>                 # one item: its fields and subtasks
btodo show <selector> --format json
btodo history <selector> [--format text|json]
btodo completed [today|week|month] [--format text|json]
```

`show --format json` carries `description` on the item and on each
entry of `subtasks`: the description lines joined by `\n`, or `null`
when the task has none.

`history` lists each completion of one task, and every other event of
that task that carries attributes, newest first. Its JSON holds `id`,
`title` and `entries`. Each entry holds `kind` (the event type, such as
`TaskCompleted` or `TaskAnnotated`), `checklist_item` (true for the
completion of a checklist item under the task), `day` and `attrs`.
[README.md](README.md#history-of-a-task) states how each entry takes
its day and its place in the order.

`completed` reads the completed log for one period, DONE records only.
`today` is the local day, `week` is seven days ending today, and
`month` reaches back to the first of the month. The period defaults to
`week`. The text form prints the attributes of a record after its title
as `key=value` pairs joined by a comma and a space. A value may hold
that separator, so read attributes from the JSON: each entry carries
`attrs`, an object of text values, `{}` when the record carries none.

The `view` JSON schema is documented in
[README.md](README.md#machine-readable-output). It grows by addition:
new keys appear, existing keys keep their meaning. Read each task array
in the order given rather than re-sorting by `rank`, and read `hidden`
to learn how many open items the selection left out.

## Write

```text
btodo add <list> <title> [-p N] [--loe N] [--due YYYY-MM-DD]
                         [--repeat R] [--tags a,b] [--description TEXT]
                         [--attrs ATTRS] [--note TEXT]
btodo add <list> <title> --parent <selector>
btodo update <selector> [-p N] [--due YYYY-MM-DD] [--tags a,b]
                        [--title TITLE] [--description TEXT]
                        [--attrs ATTRS] [--note TEXT]
btodo done <selector> [--date YYYY-MM-DD] [--attrs ATTRS] [--note TEXT]
btodo scratch <selector> [--attrs ATTRS] [--note TEXT]
btodo note <selector> [TEXT] [--attrs ATTRS]
```

- `<list>` is a filename stem: `chores` for `chores.md`.
- `-p` is the priority multiplier, 0 and up. `--loe` is the level of
  effort: 1, 2, 3, 5 or 8. `--repeat` is `Nd`, `Nw`, `weekly:DAY` or
  `monthly:N`. `--tags` is a comma-separated list.
- Give the title without `[FIELD:]` markup. Fields go in through their
  own options.
- `--description` sets the description of a task: each line of `TEXT`
  becomes one description line under the task. `update --description ''`
  clears it. A subtask takes a description too. btodo refuses a line
  that is blank, reads as a task, a heading or a comment, or holds a
  carriage return. `show` prints the description.
- `add` echoes the line it wrote and the file it wrote to. Read that
  echo to confirm the write. A task with no `-p` gets a neutral
  priority and still ranks by its dates; an explicit `-p 0` parks the
  task out of every view.
- `done` completes the task and logs it. `scratch` drops the task and
  logs it as abandoned. `completed` counts only the first, so pick the
  one that states what happened. Both echo the record they log. A
  record with attributes ends with one `[attrs:{...}]` block: the
  attributes as a JSON object in ASCII.
- `done --date` logs the completion under the day the work finished,
  rather than the day it is marked off. A repeating task is rescheduled
  from that day too.
- Checking off the last open child completes its parent.

## Attributes and notes

`--attrs` and `--note` record attributes on the journal event of the
task the command names. `note` records them with no other change.

- `--attrs` takes one string of `key=value` segments:
  `--attrs 'cost=45.00, place=Main St, Suite 4'`. The string splits
  only at a comma followed by the next `key=`, so a value may hold
  commas and `=`. That example gives `place` the value
  `Main St, Suite 4`.
- A key is a lowercase letter, then lowercase letters, digits or
  underscores.
- `--note TEXT` records `TEXT` as the attribute `note`. The text never
  runs through the split.
- To record no attributes, leave both options off. btodo refuses each
  of these before it writes anything: a key given twice (`note=` in
  `--attrs` beside `--note`, or beside the `TEXT` of `note`, counts),
  an empty value (`--attrs ''` and `--note ''` count), a line break, a
  segment with no `=`, a key outside the grammar, and any attribute on
  a checklist item.
- Attributes ride on a change. `update` with `--attrs` or `--note` and
  no other change refuses with "nothing to update". Record a note alone
  with `note`.
- `note <selector> [TEXT] [--attrs ATTRS]` takes `TEXT` as the
  attribute `note`. It takes no `--note` option. Give it `TEXT`,
  `--attrs`, or both; `note` refuses a call with neither.
- `note` leaves the task unchanged. It reaches an open task at any
  depth. A task with no `[ID:]` gets one first, and the echoed line
  shows it.

## Selectors

A selector is the task's `[ID:]` value, or any part of its title, case
insensitive. An exact id wins over a title match. The search covers
every open task at every depth, in every list, parked lists included.

A selector that matches nothing, or more than one open task, is an
error. The message names the candidates. Narrow the selector, or take
the id from `--format json` output.

`history` resolves its selector against the journal instead of the
lists. A title selector matches the current title of each task, and a
finished task stays in reach. Read a finished task's attributes and
notes through `history`.

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

Every value in the config file is a quoted string. The environment and
the command line carry strings only, so a quoted value gives an option
one type from every source; the command that reads a value decodes it.

```toml
[personal.battodo.view]
top = "3"
```

The table sits under the environment the file names.
[README.md](README.md#configuration) holds the full file skeleton.

An unquoted `top = 3` reaches the decoder as a TOML integer. `btodo
view` then exits 1 and prints `'int' object has no attribute
'isdecimal'` to stderr.

The config file is resolved in this order:

1. the path given to `--conf`,
2. the path in `$BATTODO_CONFIG_FILE`,
3. `./battodo.toml`,
4. `$XDG_CONFIG_HOME/battodo/config.toml`, or
   `~/.config/battodo/config.toml` when that variable is unset.

Finding no config file is normal. Defaults and environment variables
answer on their own. A file named by `--conf` or `$BATTODO_CONFIG_FILE`
must exist; the searched paths (3, 4) are optional.
