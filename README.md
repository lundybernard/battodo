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
btodo backfill          # one-time migration: stamp [ADDED:today] where missing
```

Items are ordered by a rank computed from the file and the clock —
priority as a multiplier, times how long the item has waited and how
pressing its due date is. Nothing is written to keep that current; see
[ADR 0005](docs/decisions/0000-project-bootstrap/0005-computed-rank.md).

A list opts out of views by carrying `<!-- battodo:parked -->` anywhere
in the file. It stays discoverable, so migrations still reach it, and
it stays out of `--all` too — opting out is not a time window.

### Attributes on a write

`add`, `update`, `done` and `scratch` take `--attrs` and `--note`. The
journal event of the task the command names records them in
`payload.attrs`
([ADR 0020](docs/decisions/0019-event-attributes/0020-event-attribute-map.md)).

```bash
btodo done permit --attrs 'confirmation=A1B2C3, place=Main St, Suite 4'
btodo done permit --note 'Renewed online'
```

`--attrs` takes `key=value` segments. It splits only at a comma
followed by the next `key=`, so a value may hold commas and `=`. A key
is a lowercase letter, then lowercase letters, digits or underscores.
`--note TEXT` enters as the key `note` and is not split. A key given
twice, an empty value, a line break, a segment with no `=` or a key
outside the grammar is refused before anything is written. A checklist
item takes no attributes.

### Notes on a task

`note` records a note on an open task between its writes
([ADR 0023](docs/decisions/0019-event-attributes/0023-note-event.md)).

```bash
btodo note permit 'Waiting on the office'
btodo note permit 'Called the office' --attrs 'contact=Sam, ext. 4'
btodo note permit --attrs 'quote=45.00'
```

`TEXT` enters as the key `note`, beside the `--attrs` grammar above,
and is not split. The note goes on a `TaskAnnotated` event on the
stream of the task, and the task does not change. A task with no
`[ID:]` is given one first, and the echoed line shows it. A call with
neither `TEXT` nor `--attrs` is refused before anything is written, as
is a checklist item. A done task is out of reach.

### History of a task

`history` lists the completions of one task, and every other event
that carries attributes, from the journal
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
names each candidate. Entries run newest first: by day, and on one day
the later event in the journal comes first. A completion falls on the
day it is for, and any other event on the local day it was recorded.
Each attribute follows on a line of its own, in recorded order. The
completion of a checklist item reads `TaskCompleted (checklist item)`.
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
          "id": "k3x9",
          "title": "File the quarterly report",
          "rank": 6.0,
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
`--all`, or a larger `--top`, will show more.

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
