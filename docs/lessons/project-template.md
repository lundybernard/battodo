# project_template lessons

Found during the pristine import + package rename (commits 1–2):

- The package name is hard-coded in CLI *logic*, not just metadata:
  `cli.py` has `usage='bat [<args>] <command>'`, `description='...various
  bat tasks'`, a subparser help string, and — worst — `subprocess.Popen(
  ['bat', 'start'])`, which invokes the console script by literal name.
  Renaming the package silently breaks `run_functional_tests` at runtime.
  The entry-point name should come from one constant (or
  `argparse` `prog=`/`sys.argv[0]`), not be repeated as string literals.
- Packaging carries two sources of truth for two facts. Entry points are
  declared in `pyproject.toml` (`[tool.poetry.scripts]`) and again in
  `setup.py` (`console_scripts`); the version is a literal in
  `pyproject.toml` while `setup.py` does `from bat._version import
  __version__`, which imports the package at build time and hard-codes
  its name in otherwise generic boilerplate. A PEP 621 move with
  hatchling's `[tool.hatch.version] path = ...` collapses both pairs to
  one declaration each — and must carry over the coverage `omit` entry
  for `_version.py`, which nothing imports at runtime once the build
  backend reads it statically and which therefore can never reach 100%.
- `--cov-fail-under=100` sits in default `[tool.pytest.ini_options]
  addopts`, so coverage runs on every invocation and a partial run — one
  test file, one test — fails on coverage rather than on the tests it
  actually ran. The gate belongs in one explicit task.
- Stale metadata and tooling: `description = ''` is empty;
  `[tool.poetry.dev-dependencies]` is the deprecated spelling
  (`[tool.poetry.group.dev.dependencies]` since Poetry 1.2);
  `python = '^3.8'` is EOL; `setup.py`'s distribution name was `"BAT"`
  while pyproject's was `bat`.
- Dead CI: `.travis.yml` targets travis-ci.org (defunct) and the README
  carries a build badge pointing at it. Left in place deliberately —
  removal is a separate, upstreamable modernization commit.
- README documents installation as `python setup.py develop` /
  `python setup.py install`, both long deprecated.

Found during the dev-environment cycle (poetry → PEP 621 + pixi):

- The web service is not separable by deleting a directory. Removing
  `server/` also required pulling the `server` subparser out of `cli.py`,
  deleting `api/` (the connexion spec), the `run_functional_tests` and
  `run_container_tests` subcommands, `Commands.test`, the requests-based
  `common_api_tests.py` helper that `functional_tests/` inherited from,
  `MANIFEST.in` (whose only entry was `bat/api/*`), and every docker and
  compose file. A template that advertises itself as a starting point for
  CLIs *or* services should isolate the service behind one optional
  package plus one optional extra, not thread it through the root CLI.
- `conf_test.py` carried a dead YAML fixture (`EXAMPLE_CONFIG_YAML` /
  `EXAMPLE_CONFIG_DICT`) and a dead `t.config_file_data`, neither ever
  read. The fixture was the suite's only reason to depend on pyyaml.
- `example.config.yaml` does not match the `example.Config` dataclass it
  is supposed to illustrate (the file has `remote_host.api_key/url`; the
  dataclass has a single `parameter: str`).
- `mypy --strict` is the goal but needs a dedicated annotation pass
  first; the non-strict default is close to clean already.
- **Template main is broken against current batconf:** `pyproject.toml`
  declares `batconf = '*'` — unpinned — while `bat/conf.py:3` imports
  `FileConfig`, a class removed in batconf 0.4. A fresh bootstrap
  installs the newest batconf and fails on import. See
  [batconf.md](batconf.md).
- **Apps prune the CI matrix to their real targets at bootstrap:**
  battodo started from another project's workflow, which fanned out over
  `[ubuntu, macos, windows]` — right for a library, wrong by default for
  an app that chose Unix-only primitives (the `flock` journal, ADR 0004).
  Windows CI failed on `import fcntl` plus an 8.3 short-path vs
  resolved-path assertion mismatch: platform cost paid for a user that
  doesn't exist. Dropped in `b026628`. The template ships no CI at all,
  so this is the app's call to make on day one.
- **`dictConfig` silently kills third-party loggers:** the template's
  `logconf.py` uses a schema-version-1 `dictConfig` without setting
  `disable_existing_loggers`, whose default is `True`. `cli.py` imports
  the package's dependencies (batconf via `conf.py`) *before* calling
  `dictConfig`, so every logger those libraries created at import time
  is permanently disabled — batconf's `Config file not found` warning
  never reached stderr through battodo's CLI, while the identical call
  warns fine in a bare interpreter. Found only because an agent's doc
  finding contradicted a live run (2026-08-11). The template should ship
  `'disable_existing_loggers': False`; the import-order trap deserves a
  comment either way.
- **CI must fan out over the whole interpreter range the metadata
  promises.** A single test job runs whatever version the default
  environment pins, and nothing cross-checks that against
  `requires-python`, so the floor is an assertion no run executes —
  battodo said `>=3.10` and had only ever run 3.14. The gap hides well:
  a green check reads as coverage of the supported range rather than of
  one point in it. Metadata and matrix should be built together, a
  feature and env per supported version, or else the range should narrow
  to what is actually tested. Here the claim survived contact — 3.10–3.14
  all pass with no source changes — but until the matrix existed that was
  a guess that happened to be right. The template still declares poetry's
  `python = '^3.8'` and has no CI to check it against.
- **Message catalog for CLI strings:** extracting every user-facing
  argparse string into a pure-data module (`messages.py`, stable
  namespaced keys) gave three wins at once: a future localization
  seam, no string duplication between parser and tests (a conformance
  test walks `parser._actions` against the catalog), and a clean
  mutation-testing boundary — the data file is excluded while every
  reference to it stays mutated. Two-thirds of the baseline surviving
  mutants were display-string noise; this removed them structurally.
  Template candidate: ship the example CLI with a catalog from day
  one.
- **Mutation testing as a pixi feature (contingent):** a `mutation` env
  (mutmut + pytest collecting the stdlib unittest suite unchanged)
  slotted in with no friction — but the slotting described is battodo's,
  and it presumes the template adopts pixi's feature-per-tool layout
  first. Worth upstreaming after that, once the run recipe stabilizes;
  see [mutmut.md](mutmut.md) for the tool-side caveats the recipe has to
  work around.
- **Config lookups depend on where the schema class lives:** the
  template builds `Configuration(source_list, config_class)` with no
  `path=`, so every lookup path, environment variable name, and CLI
  argument prefix silently derives from the schema class's module —
  placement of config dataclasses becomes load-bearing. batconf 0.4.0's
  `Configuration` takes an explicit `path=` and treats the module as a
  fallback only. The template's conf tests also fake `__module__` on
  *nested* schema classes (`bat/tests/conf_test.py:73-74`, "As if
  imported from a module"), which is dead weight in any batconf version:
  nested namespaces are built from the schema's field names, never from
  the nested class's module.

Fixed upstream, from both cycles above:

- `[tool.coverage.run] omit` listed `bat/server.py`, dead since the
  server module became a package.
- `MANIFEST.in`'s `recursive-include bat/api/*` was malformed; the
  directive takes `<dir> <pattern...>`, space-separated.
- The dockerfile ran `python -m unittest discover bat.tests`, so
  `bat/server/tests/` and `bat/example/tests/` never ran in the
  container build.
- The two `argparser` tests were written against `Mock(wraps=...)`
  returning a child mock; modern CPython returns `sentinel.DEFAULT` so
  the wrapped callable supplies the value, and both tests errored.
- TestCase classes were named `Test<Subject>` in the cli/conf/service
  modules and `<Subject>Tests` everywhere else; the `<Subject>Tests`
  convention now also lives in the shared python-style skill.

Resolved: merged upstream in PR #5.
