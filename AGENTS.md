# BatTodo contributor guide

battodo is a personal CLI todo tool. It keeps todo lists as markdown files
and records every change in a JSONL journal. It is a Python package
(`battodo/` at the repo root) with batconf configuration and a pixi
environment. The project is also a test-bed for batconf and for the
project template, so its design rules are stricter than its size suggests.

## Where things are

- `README.md`: the human guide.
- `SKILL.md`: the manual for an agent that operates `btodo`. It ships
  with the project.
- `docs/decisions/`: the ADRs.
- `docs/lessons/`: the informal findings log.

## Design rules

### Every configuration value is a string

Every configuration value is a string: in the TOML file, in the
environment, and on the command line. The consumer decodes what it needs.
The 2026-09-19 amendment to `docs/decisions/0007-toml-config-file.md`
records the rule.

**Why:** an environment variable holds only a string. One type from every
source keeps each decoder to a single case. A typed file value would force
every decoder to handle `0` as well as `"0"`.

**How to apply:** a new config field is a `str` dataclass field with a
`str` default, and the consumer that reads it decodes it. Keep the input
of each decoder a `str`. A typed TOML value is input outside the contract:
its exit-1 error is a config error to fix in the file, not a decoder bug.

### SKILL.md is the operating agent's manual

An agent that runs `btodo` loads `SKILL.md` and reads nothing else, so a
command absent from it is invisible to that agent. A user-facing change
lands in `SKILL.md` in the same PR: a new or changed command, option,
selector rule, output key, refusal, or exit code. Internal changes stay
out: refactors, object design, test layout. `README.md` and `SKILL.md`
share no text. Lint both with `markdownlint-cli2`.

## Working rules

- Work on a feature branch, never on `main`. A maintainer reviews each
  branch before merge.
- Run every task as `pixi run <task>`. A PR passes `tests`, `lint`,
  `typecheck`, `fuz`, and `unit-py311` through `unit-py315`.
- Every commit keeps `pixi run tests` green. The one exception is a commit
  whose subject carries `(RED)`: it adds a failing test, and the next
  commit turns it green.
- Unit tests live in `battodo/**/tests/`. They touch no disk, mock all
  I/O, and carry a 100% coverage gate. The root `tests/` holds the
  integration, behavioral, and property suites.
- A commit subject is `<type>: <summary>`, with a lowercase summary that
  names the symbol or file changed. Add a `Refs: #N` or `Resolves: #N`
  trailer when an issue applies.
- Write docstrings, commit bodies, docs, and ADRs in short sentences,
  active voice, and present tense (ASD-STE100).
- Diagnose before you fix: show the failure point before you change the
  code.

## PR notes

- Write about five bullets, decisions first.
- Name the `SKILL.md` hunk, or state that the change is internal.
- Start agent-written GitHub prose with the line
  `:robot: _AI text below_ :robot:`.
