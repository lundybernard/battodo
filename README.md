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
btodo view          # open items for the currently active categories
btodo view --all    # every open item, not just the top few per category
btodo backfill      # one-time migration: stamp [ADDED:today] where missing
```

Items are ordered by a rank computed from the file and the clock —
priority as a multiplier, times how long the item has waited and how
pressing its due date is. Nothing is written to keep that current; see
[ADR 0005](docs/decisions/0001-project-bootstrap/0005-computed-rank.md).

A list opts out of views by carrying `<!-- battodo:parked -->` anywhere
in the file. It stays discoverable, so migrations still reach it.

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

Setting the same value from a config file is blocked on batconf 0.4.0
and its `TomlSource`; the env var and CLI arguments work today.

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
