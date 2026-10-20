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
  command. A due date scales the priority: a task a month or more from
  its due date ranks at half, and the factor rises through the due date
  and past it.
- A view shows every open task, a recurring task before its due date
  included. To mark a task as wanted at once, give it today's date as
  `--due`. `DUE` takes a date only.
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
when the task has none. It carries `repeat` on both too: the
`[REPEAT:]` value, or `null` when the task does not repeat. The text
form of `show` prints a subtask's repeat as `[REPEAT:]` on its line.

`history` lists each close and each reopen of one task, and every
other event of that task that carries attributes, newest first. A
completion and a scratch each close the task, with or without
attributes. Its JSON holds `id`, `title` and `entries`. Each entry
holds `kind` (the event type: `TaskCompleted`, `TaskScratched`,
`TaskAnnotated`, or `TaskUpdated` for a reopen and an update with
attributes), `checklist_item` (true for the close of a checklist item
under the task), `day` and `attrs`.
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
to learn how many open items the selection left out. Each task of
`view --format json`, and the item of `show --format json`, carries
`list`: the filename stem of the list that holds it.

## Write

```text
btodo add <list> <title> [-p N] [--loe N] [--due YYYY-MM-DD]
                         [--repeat R] [--tags a,b] [--description TEXT]
                         [--attrs ATTRS] [--note TEXT]
btodo add <list> <title> --parent <selector>
btodo update <selector> [-p N] [--due YYYY-MM-DD] [--repeat R]
                        [--tags a,b] [--title TITLE] [--description TEXT]
                        [--list <list>] [--with-subtasks]
                        [--attrs ATTRS] [--note TEXT]
btodo done <selector> [--date YYYY-MM-DD] [--scratch]
                      [--attrs ATTRS] [--note TEXT]
btodo note <selector> [TEXT] [--attrs ATTRS]
```

- `<list>` is a filename stem: `chores` for `chores.md`.
- `-p` is the priority multiplier, 0 and up. `--loe` is the level of
  effort: 1, 2, 3, 5 or 8. `--repeat` is `Nd`, `Nw`, `weekly:DAY` or
  `monthly:N`. `--tags` is a comma-separated list.
- `update --repeat R` sets or changes the repeat of a task at any
  depth. `update --repeat None` removes it; btodo refuses an empty
  `--repeat`. `DUE` stays as it is: the new rule applies at the next
  completion, and with no repeat the next `done` completes the task.
- `update --due None` removes the due date, and `update --tags None`
  removes the tags. `update --tags ''` leaves an empty `[TAGS:]`
  instead. `-p` has no clear: btodo refuses `-p None`.
- A value that the task already holds is no change: a `-p`, `--due`,
  `--repeat` or `--tags` value, a `--title` or a `--description`. So is
  a `None` clear of a field that the task does not carry, and
  `--description None` or `''` on a task with no description. btodo
  compares `--due` as a date. It writes only the changes, and the
  journal delta records only them.
  With no change left, `update` on an open task exits 1 with "nothing
  to update" and writes nothing; a closed task still reopens.
- Give the title without `[FIELD:]` markup. Fields go in through their
  own options.
- `--description` sets the description of a task: each line of `TEXT`
  becomes one description line under the task. `update --description
  None` clears it, as `update --description ''` does. A subtask takes a
  description too. btodo refuses a line that is blank, reads as a task,
  a heading or a comment, or holds a carriage return. `show` prints the
  description.
- Before `add`, look for a finished task with the same meaning:
  `btodo history <a key word of the title>`. One match prints that
  task's history. Several matches exit 1 and print one candidate per
  line on stderr, `<id>  <last event day>  <title>`, newest first,
  which is the search result. No match exits 1 and says so. When a
  finished task matches, ask the user whether to reopen or reschedule
  it under its own `[ID:]` instead of adding a new task. One id keeps
  the history of a task in one place, where a new title scatters it
  across names. On a yes, reopen it with `btodo update <id>`, adding
  `--due` for a new due date; see [Reopen and move](#reopen-and-move).
- `add` echoes the line it wrote and the file it wrote to. Read that
  echo to confirm the write. A task with no `-p` gets a neutral
  priority and still ranks by its dates; an explicit `-p 0` parks the
  task out of every view.
- `done` completes the task and logs it. `done --scratch` drops the
  task and logs it as SCRATCHED: give the reason with `--note`.
  `completed` counts only completions, so pick the form that states
  what happened. Both echo the record they log. A record with
  attributes ends with one `[attrs:{...}]` block: the attributes as a
  JSON object in ASCII.
- `done --scratch` drops the whole block of the task, subtasks
  included. It completes no parent and reschedules no repeating task.
- `done` on a repeating task logs it and keeps it open: its `DUE`
  moves to the next date of its repeat, and its subtasks go. The task
  keeps its `[ID:]`.
- `done --date` logs the record under the day the task closed, rather
  than the day it is marked off. A repeating task is rescheduled from
  that day too. A repeating top-level task takes that day as its
  `[ADDED:]`, so its age counts from the last completion.
- Checking off the last open child completes its parent. A repeating
  child never completes, so its parent stays open.
- `done` refuses a task with an open repeating subtask at any depth:
  it exits 1 and writes nothing. The message names the first one,
  `'<task>' has a repeating subtask, '<subtask>' [ID:<id>]: remove its
  repeat first with update <id> --repeat None`. Run that `update`, then
  `done` the task again. A subtask with no `[ID:]` is named by its
  title instead.

## Reopen and move

`done` and `done --scratch` close a task. `update <id>` on a closed task
reopens it under the same id.

- `update` reaches an open task first. When no open task answers, it
  reaches a closed task in the journal, by the selector rule of
  `history`. Name a closed task by its `[ID:]`; take the id from
  `history`.
- The task comes back open, last in the open section of its list, with
  the fields, title and description it closed with. The options of the
  call apply on top. A call with no option reopens it unchanged.
- Its subtasks come back checked off. `--with-subtasks` opens each of
  them too. A closed subtask reopens with each closed task above it;
  its siblings keep their state. A checklist item reopens only with
  its task: naming one exits 1 and names the `[ID:]` of its task.
- `--list <list>` reopens a top-level task into that list.
- `--list <list>` on an open top-level task moves it, its description
  and subtasks with it, to the end of that list. A subtask refuses
  `--list`: it moves with its top-level task. `--list` that names the
  task's own list is no change: with no other option, `update` exits 1
  with "nothing to update" and writes nothing.
- `--with-subtasks` on an open task exits 1.
- Several closed tasks that match exit 1 and print one per line,
  `<id>  <last event day>  <title>`, as `history` does.
- The completed log keeps the record of each closing. A later `done`
  adds a new record on the same id. `history` lists the reopen as a
  `TaskUpdated` entry.

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
- Attributes ride on a change. On an open task, `update` with `--attrs`
  or `--note` and no other change refuses with "nothing to update".
  Record a note alone with `note`.
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
notes through `history`. `update` falls back to the closed tasks of the
journal when no open task matches.

## Subtasks

- `add --parent <selector>` files the new task under its parent, in the
  same list.
- `update`, `done` and `show` reach a task at any depth.
- `-p` is refused on a child: only a top-level task carries a rank.
  `--repeat` works on a child as on a top-level task.
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

The due-date curve is `view.rank_due_curve`, or
`BATTODO_VIEW_RANK_DUE_CURVE`: comma-separated `days:factor` points, a
negative day before the due date. A curve that does not decode makes
`view` and `show` exit 1 and name the bad point on stderr.

The schedule is three fields, each empty by default:

- `view.time_zone` or `BATTODO_VIEW_TIME_ZONE`: the zone of the clock,
  such as `America/Los_Angeles`. Empty reads the zone of the system.
- `view.windows` or `BATTODO_VIEW_WINDOWS`: when each category shows,
  as `work=mon-fri 9-17; chores=mon-fri 17-21, sat-sun 10-20`. Days are
  `mon` to `sun`, single or a forward run; hours are whole, 24-hour,
  end excluded.
- `view.always_active` or `BATTODO_VIEW_ALWAYS_ACTIVE`: a
  comma-separated list of categories that show outside their windows.

With no windows, `view` shows every category, and its header names the
day and the time alone. A category with no window always shows. An
unknown zone or a window that does not decode makes every command that
reads the clock exit 1 and name the field and the bad value.

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
