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

## Development

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
