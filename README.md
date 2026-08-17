# BatTodo
Personal todo-list CLI (BAT ecosystem test-bed)

## Installation

Development environment (pixi manages the interpreter and tools):

```
pixi install
```

Or install the package on its own:

```
pip install -e .
```

Either way the CLI is available as `btodo`, or `btd` for short:

```
btodo --help
```

## Usage

```
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

- `view.source_dir` — the directory the lists are read from. `~/todo`.
- `view.top` — how many items a category shows. `5`, and `--top` on the
  command line overrides it.

An environment variable is the config path in caps:

```
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

btodo reads `config.toml` from the working directory. `--conf FILE`
names another file, and `--env NAME` picks an environment from it.

## Development

### Pointing btodo at a different source

The source directory defaults to `~/todo`. Override it through batconf's
environment source — the variable is the config path in caps:

```
export BATTODO_VIEW_SOURCE_DIR=/path/to/battodo/sandbox/todo
btodo view
```

That is the intended dev loop: work against a copy, never the live
lists. Clone them with `cp -rL` — `~/todo` is a symlink, so plain
`cp -r` copies the link and every "sandbox" write lands on real data.
Verify the target is a real directory (`ls -ld`) before running anything
that mutates.

Tasks run through pixi; each one uses its own isolated environment.

```
pixi run tests      # the full gate: unit + typecheck + lint
pixi run unit       # unit suite under coverage, gated at 100%
pixi run test       # unit suite only, no coverage, no gate
pixi run typecheck  # mypy
pixi run lint       # ruff check + ruff format --check
```

Tests are stdlib `unittest`. Unit tests live beside the code they cover,
under `battodo/**/tests/`.
