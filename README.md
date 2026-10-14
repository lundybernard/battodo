# BatTodo

Personal todo-list CLI (BAT ecosystem test-bed)

## Installation

Development environment (pixi manages the interpreter and tools):

```bash
pixi install
```

Or install the package on its own:

```bash
pip install -e .
```

Either way the CLI is available as `btodo`, or `btd` for short:

```bash
btodo --help
```

## Usage

```bash
btodo view              # open items for the currently active categories
btodo view --top 10     # ten items a category, rather than the default five
btodo view --all        # every open item, and every category, active or not
btodo view --format json  # the same view as JSON, for agents
btodo show permit       # one task: its fields, description and subtasks
btodo add chores 'Renew the parking permit' --due 2026-10-01
btodo add chores 'Find the old sticker' --parent permit  # a subtask
btodo add chores 'Check the mail' --parent permit --repeat 7d  # it repeats
btodo update permit -p 2 --due 2026-10-15  # new field values
btodo update permit --description 'Bring the old permit.'
btodo update permit --list errands  # move it, its subtasks with it
btodo update permit --repeat 90d  # set or change its repeat
btodo update permit --repeat None  # and clear it again
btodo note permit 'Called the office'  # a note; the task does not change
btodo done permit       # complete the task and log it to completed.md
btodo done permit --date 2026-10-01  # log it under the day it finished
btodo done permit --scratch --note 'Moved'  # log it as SCRATCHED
btodo update 3usdig --due 2026-11-01  # reopen a closed task by its id
btodo history permit    # closes, reopens and attributes, newest first
btodo completed month   # the DONE records since the first of the month
btodo backfill          # one-time migration: stamp [ADDED:today] where missing
```

`None` is the clear token of `update`: `--repeat None` removes the
repeat and `--description None` the description
([ADR 0028](docs/decisions/0028-update-repeat.md)). A new repeat leaves
the due date alone and applies from the next completion. An option that
names what the task already holds changes nothing, and the journal
records only what changed. An update of an open task with nothing left
to change exits 1; a reopen still opens the task.

A subtask can repeat as well. Its `done` moves its due date on and
leaves it open, so its parent stays open too. `done` on the parent
exits 1 and names the repeating subtask until its repeat is cleared
([ADR 0029](docs/decisions/0029-subtask-repeat.md)).

`btodo <command> --help` lists the options of each command.
[SKILL.md](SKILL.md) states the rules and the refusals of each command
for an agent.

Items are ordered by a rank computed from the file and the clock —
priority as a multiplier, scaled by how near its due date is and by how
long the item has waited. Nothing is written to keep that current; see
[ADR 0005](docs/decisions/0000-project-bootstrap/0005-computed-rank.md)
and [ADR 0026](docs/decisions/0026-due-date-factor.md).

A view shows every open item. A recurring task shows from the day it is
rescheduled: it ranks low while its due date is far off and climbs as
the date comes near. `done` moves its `[ADDED:]` to the completion day,
so its wait starts again; its `[ID:]` and its history stay.

A list opts out of views by carrying `<!-- battodo:parked -->` anywhere
in the file. It stays discoverable, so migrations still reach it, and
it stays out of `--all` too — opting out is not a time window.

### Attributes on a write

`add`, `update` and `done` take `--attrs` and `--note`. The
journal event of the task the command names records them in
`payload.attrs`
([ADR 0020](docs/decisions/0019-event-attributes/0020-event-attribute-map.md)).

```bash
btodo done permit --attrs 'confirmation=A1B2C3, place=Main St, Suite 4'
btodo done permit --note 'Renewed online'
```

`--attrs` takes `key=value` segments, and a value may hold commas and
`=`: the first example records `place` as `Main St, Suite 4`.
`--note TEXT` records the attribute `note`.
[SKILL.md](SKILL.md#attributes-and-notes) states the grammar and the
inputs that btodo refuses before it writes anything.

`done` also writes the attributes on the record it adds to
`completed.md`, as one JSON block after the fields:

```text
2026-10-01 | errands | DONE | Renew the permit [attrs:{"cost": "45.00"}]
```

`btodo completed` shows them after the title as `key=value` pairs.

`done` also writes the attributes on the record it adds to
`completed.md`, as one JSON block after the fields:

```text
2026-10-01 | errands | DONE | Renew the permit [attrs:{"cost": "45.00"}]
```

`btodo completed` shows them after the title as `key=value` pairs, and
`--format json` gives each entry an `attrs` object, empty where the
record carries none.

### Notes on a task

`note` records a note on an open task between its writes
([ADR 0023](docs/decisions/0019-event-attributes/0023-note-event.md)).

```bash
btodo note permit 'Waiting on the office'
btodo note permit 'Called the office' --attrs 'contact=Sam, ext. 4'
btodo note permit --attrs 'quote=45.00'
```

`TEXT` enters as the key `note`, beside the `--attrs` grammar above,
and btodo never splits it. The note goes on a `TaskAnnotated` event on the
stream of the task, and the task does not change. btodo first stamps
an `[ID:]` on a task that has none, and the echoed line shows it.
[SKILL.md](SKILL.md#attributes-and-notes) lists the calls that `note`
refuses.

### Reopen a task

`done` closes a task; `update` on its `[ID:]` reopens it
([ADR 0025](docs/decisions/0025-reopen-by-update.md)). The task keeps
its id, so `history` reads its whole life as one task.

```bash
btodo done permit --date 2026-10-01
btodo update 3usdig --due 2026-11-01  # back in its list, open
btodo update 3usdig --list errands    # or back in another list
btodo update 3usdig --with-subtasks   # and its subtasks open too
```

`update` reaches an open task first. When none answers the selector, it
reaches a closed task in the journal, by the rule of `history`. The
task comes back last in the open section of its list, with the fields,
title and description it closed with and the changes the update names.
With no option, it comes back unchanged. Its subtasks come back checked
off; `--with-subtasks` opens them. A closed subtask opens with each
closed task above it, and its siblings stay as they are. A checklist
item opens only with its task.

The completed log keeps the record of each closing, and a later `done`
adds a new one under the same id.

`update --list <list>` also moves an open top-level task to another
list, its description and subtasks with it. The journal records the
move as the list the task left and the list it joined.

### History of a task

`history` lists the completions, scratches and reopens of one task,
and every other event that carries attributes, from the journal
([ADR 0022](docs/decisions/0019-event-attributes/0022-history-command.md)).

```bash
btodo done permit --date 2026-09-01
btodo note permit 'Waiting on the office'
btodo done permit --date 2026-10-01 \
  --attrs 'confirmation=A1B2C3, place=Main St, Suite 4'
btodo history permit
```

```text
Renew the parking permit [ID:3usdig]
  2026-10-11  TaskAnnotated
    note=Waiting on the office
  2026-10-01  TaskCompleted
    confirmation=A1B2C3
    place=Main St, Suite 4
  2026-09-01  TaskCompleted
```

The selector is the `[ID:]` of the task, or a case-insensitive part of
its current title. It reads the journal, not the lists, so a finished
one-shot task stays in reach. A selector that names no task is
refused. A selector that names several is refused, and the message
names each candidate on a line of its own: its id, the day of its last
event and its title, newest first. Entries run newest first: by day,
and on one day the later event in the journal comes first. A completion
falls on the day it is for, and any other event on the local day it was
recorded.
Each attribute follows on a line of its own, in recorded order. The
close of a checklist item reads `TaskCompleted (checklist item)` or
`TaskScratched (checklist item)`.
`--format json` gives the same document. A completion made by hand
edit writes no event, so `history` does not list it.

### Machine-readable output

`btodo view --format json` writes the same selection to stdout as a
JSON document, so an agent never has to scrape the table:

```json
{
  "date": "2026-08-05",
  "active": ["career", "events", "study", "work"],
  "categories": [
    {
      "name": "work",
      "hidden": 2,
      "tasks": [
        {
          "list": "work",
          "id": "k3x9",
          "title": "File the quarterly report",
          "rank": 10.29,
          "priority": 2.0,
          "loe": 3,
          "due": "2026-08-07",
          "added": "2026-05-10",
          "repeat": null,
          "tags": ["admin"],
          "subtasks": 1
        }
      ]
    }
  ]
}
```

Fields carry the stored values verbatim: `due` is the date as written,
never an `OVERDUE`/`TODAY` label, and an absent field is `null`.
`priority` is `P` folded on to the 0–5 multiplier scale (ADR 0005) —
the number the text view prints in its `P` column. `rank` is rounded
for display; each task array is already in rank order, so read the
order rather than re-sorting by the number. `subtasks` counts open
children. `hidden` is how many of the category's open items were left
out — `0` means the array is the whole of it, and anything higher means
`--all`, or a larger `--top`, will show more. `list` names the list
that holds each task, as `show --format json` does.

The schema grows by addition only: new keys may appear, existing ones
keep their meaning.

## Configuration

A value comes from the first source that carries it: a command-line
argument, then an environment variable, then a config file, then the
built-in default. Every value is a string, which is all the environment
can hold; the command that reads one decodes it.

A command input, such as a selector, `--date` or `--all`, is not
configuration: it comes from the command line only
([ADR 0024](docs/decisions/0024-cli-inputs-config-and-command.md)).

- `view.source_dir` — the directory the lists are read from. `~/todo`.
- `view.top` — how many items a category shows. `5`, and `--top` on the
  command line overrides it.
- `loglevel` — the level records are logged at. `ERROR`, and
  `--verbose` or `--debug` on the command line overrides it.
- `format` — the form `view`, `show` and `completed` write: `text` or
  `json`. `text`, and `--format` on the command line overrides it.
- `view.rank_due_curve` — the curve the due date scales a rank by.
  `-30:0.5, -7:1.0, 0:2.0, 14:4.0`.

`view.rank_due_curve` is a comma-separated list of `days:factor` points.
`days` counts like a launch countdown: a negative day is before the due
date, `0` is the due date, and a positive day is past it. Between two
points the factor runs in a straight line. Before the first point it
holds the first factor, and after the last point it holds the last
factor. Each point names a day of its own, and a factor is a number of
0 or more. A task with no due date takes a factor of 1. The default ranks
a task a month or more ahead at half, a week ahead at 1, due today at 2,
and two weeks late at 4. A value that does not decode stops the command
with exit 1 and names the bad point.

An environment variable is the config path in caps:

```bash
export BATTODO_VIEW_TOP=10
```

A config file names an environment, then holds the same paths under it:

```toml
[batconf]
default_env = "personal"

[personal.battodo.view]
source_dir = "~/todo"
top = "10"
```

### Where the config file lives

`btodo` runs from any directory, so it reads the first config file it
finds of:

1. the path given to `--conf`,
2. the path in `$BATTODO_CONFIG_FILE`,
3. `./battodo.toml`, for a checkout that keeps its own lists,
4. `$XDG_CONFIG_HOME/battodo/config.toml`, or
   `~/.config/battodo/config.toml` when that variable is unset.

Finding none is normal: defaults and environment variables answer on
their own. `example.config.toml` is the file to copy into place, and
`--env NAME` picks an environment from whichever file is read. The
order is [ADR 0015](docs/decisions/0015-config-file-location.md).

## Development

### Pointing btodo at a different source

The source directory defaults to `~/todo`. Override it through batconf's
environment source — the variable is the config path in caps:

```bash
export BATTODO_VIEW_SOURCE_DIR=/path/to/battodo/sandbox/todo
btodo view
```

That is the intended dev loop: work against a copy, never the live
lists. Clone them with `cp -rL` — `~/todo` is a symlink, so plain
`cp -r` copies the link and every "sandbox" write lands on real data.
Verify the target is a real directory (`ls -ld`) before running anything
that mutates.

A config file sets the same value; see
[Configuration](#configuration).

Tasks run through pixi; each one uses its own isolated environment.

```bash
pixi run tests      # the full gate: unit + typecheck + lint
pixi run unit       # unit suite under coverage, gated at 100%
pixi run test       # unit suite only, no coverage, no gate
pixi run typecheck  # mypy
pixi run lint       # ruff check + ruff format --check
```

Tests are stdlib `unittest`. Unit tests live beside the code they cover,
under `battodo/**/tests/`.
