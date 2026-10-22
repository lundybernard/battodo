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
- `battodo/cli.py`: the argparse parser and the `BATCLI` boundary.
- `battodo/lib.py`: the boundary layer that every UI imports.
- `battodo/logconf.py`: the logging wiring that `cli.py` applies at import.
- `battodo/conf.py`: the batconf configuration dataclasses and `get_config`.

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

### A refusal lists its choices from a declared tuple

A refusal that lists choices reads them from a declared tuple, in declared
order, as `FORMATS` in `battodo/lib.py` and `PERIODS` in
`battodo/completed.py` do. The message reads
`unknown <thing> <value!r>; choose one of <list>`.

### A named intermediate is a property

Inside a class, a value that is computed from the object's state and then
used is its own `@property`. It is `_<name>` when only the class reads it,
and public when another object reads it. The public name is the plain noun for
the value the consumer reads, and a raw input that readers use only in a
derived form is stored as `_raw_<name>`. A local name holds only a loop or
comprehension variable, a value derived from one, or a value that depends
on a method argument. The code reads `self.<attr>` at each use. A
module-level function tells a simple story: its body says what happens to
the objects that it operates on, and the computation lives in their
methods.

**Why:** each step is auditable and testable alone. A test sets the state
and reads the step, so it needs fewer mocks and no `assert_called_with`
check on an intermediate. A traceback names the step, and a debugger reads
the property.

**How to apply:** split a body when the split simplifies the calling code and
its tests. The degree is a judgement call. A function that needs a computed
intermediate marks a missing class or method: move the work behind a method on
the domain object, `<Entity>.<verb>(<args>)`, and keep its helper classes
internal. Read the consumer first: the names it reads are the interface.

## Working rules

- Work on a feature branch, never on `main`. A maintainer reviews each
  branch before merge.
- Run every task as `pixi run <task>`. A PR passes `tests`, `lint`,
  `typecheck`, `fuz`, and `unit-py311` through `unit-py315`.
- Lint before you push. `pixi run lint` runs `ruff check` and
  `ruff format --check` with the repo settings: single quotes, 79-column
  lines. The CI lint job runs the same task.
- At the PR tip, run `pixi run mutate` and `pixi run fuz` (the property
  suite). The mutation target is zero surviving mutants; list each
  survivor in the PR notes. CI does not run `mutate` yet.
- A one-line statement holds at most two nested calls. A deeper inner
  value becomes its own `@property`, or a local name in the cases that
  the named-intermediate rule above keeps.
- Docstrings use the numpydoc sections `Parameters`, `Returns`, and
  `Raises` with underline headers, as `battodo/lib.py` does.
- A code comment states the one constraint that the code cannot show, in
  one or two active-voice sentences. It says only what the code and the
  neighbouring comments leave unsaid.
- Write docstrings, commit bodies, docs, and ADRs in short sentences,
  active voice, and present tense (ASD-STE100).
- Diagnose before you fix: show the failure point before you change the
  code.

## Commits

- Subject: `<type>: <summary>`, 50 characters as the target and 72 as the
  cap. The summary is lowercase and names the symbol or file changed. The
  scope slot stays empty; `(RED)` is the one marker it carries.
- Type: `feat`, `fix`, `refactor`, `test`, `lint`, `docs`, or `chore`.
  A linter-driven change uses `lint`, never `style`.
- Every commit passes `pixi run lint` and `pixi run tests`, not only the
  tip. A `test(RED): <summary>` commit adds a failing test, and the next
  commit turns it green.
- A fix to an earlier commit of the same PR squashes into that commit, so
  each hunk lands once, in its final form. The PR never carries a hunk and
  its later revert.
- Body: the why, in present tense, only when the subject does not carry
  it.
- An issue reference is a trailer, `Resolves: #N` or `Refs: #N`. Code
  comments and test docstrings name the behaviour.
- Every commit carries the author's GPG or SSH signature. `main` accepts only
  signed commits.
- An AI agent that helps write a commit signs a trailer
  `Assisted-by: <tool>:<model> [<agent name>]`, for example
  `Assisted-by: claude-code:claude-opus-5-5 [The Engineer]`. The
  `[<agent name>]` part is optional. `Co-authored-by` names a person.
- The trailers (`Resolves:` or `Refs:`, `Assisted-by:`, `Co-authored-by:`)
  form one contiguous block at the end of the message, with no blank line
  inside the block, so that `git interpret-trailers` reads every line.

## Tests

- Unit tests live in `battodo/**/tests/`. They touch no disk, mock all
  I/O, and carry a 100% coverage gate. The root `tests/` holds the
  integration, behavioral, and property suites.
- A bug fix starts with a test that reproduces the reported behaviour at
  the highest layer that shows it, usually `tests/behavioral/`. The unit
  tests follow.
- One test method per function under test, `test_<fn>`. Each code path is
  a `subTest` inside it, as in `CommandsNoteTests.test_note` in
  `battodo/tests/cli_test.py`.
- Spec every mock: `patch(..., autospec=True)`, and `Mock(spec=...)` or a
  real value where you build a mock by hand.
- Test the unit in isolation. Patch each collaborator, let a
  `return_value` or `side_effect` supply its answer, and assert what the
  unit itself returns, prints, or calls. `BATCLITests` in
  `battodo/tests/cli_test.py` patches `Commands.set_log_level` and
  `Commands.view` this way.
- Assert the full text of a message with `assertEqual`.
- Name a test after the function or behaviour under test
  (`test_command_error`). The `subTest` labels carry the expected outcome.
- A test has three phases: setup, execute, assert. From four statements
  up, blank lines separate them. Call the code under test in the execute
  phase and bind its result; the assert phase reads that name.
- Each `subTest` block repeats the three phases, under the same
  blank-line rule. A mock reused across `subTest` blocks gets
  `reset_mock()` as the first statement of each later block.

## PR notes

- Write about five bullets, decisions first.
- Name the `SKILL.md` hunk, or state that the change is internal.
- The body carries one verification line that names each gate that ran
  and its exit code. It restates no diff hunk.
- Start agent-written GitHub prose with the line
  `:robot: _AI text below_ :robot:`.
