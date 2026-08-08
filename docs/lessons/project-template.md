# project_template lessons

Found during the pristine import + package rename (commits 1–2):

- The package name is hard-coded in CLI *logic*, not just metadata:
  `cli.py` has `usage='bat [<args>] <command>'`, `description='...various
  bat tasks'`, a subparser help string, and — worst — `subprocess.Popen(
  ['bat', 'start'])`, which invokes the console script by literal name.
  Renaming the package silently breaks `run_functional_tests` at runtime.
  The entry-point name should come from one constant (or
  `argparse` `prog=`/`sys.argv[0]`), not be repeated as string literals.
- Entry points are declared twice, in `pyproject.toml`
  (`[tool.poetry.scripts]`) and in `setup.py` (`console_scripts`), and
  must be hand-synced. Same for the version: `pyproject.toml` hard-codes
  `version = '0.0.1'` while `setup.py` reads it from `bat/_version.py` —
  two sources of truth that can drift.
- `setup.py` does `from bat._version import __version__`, importing the
  package at build time (chicken-and-egg) and hard-coding the package
  name in a file that is otherwise generic boilerplate.
- `[tool.coverage.run] omit` lists `bat/server.py`, which does not exist —
  the real file is `bat/server/server.py`. The omit entry has been dead
  since the server module became a package.
- `MANIFEST.in` says `recursive-include bat/api/*`. The directive syntax
  is `recursive-include <dir> <pattern...>` (space-separated), so this
  line is malformed and includes nothing.
- Renaming requires a repo-wide sweep, not a `bat/`-scoped one: live
  references also sit in `functional_tests/service_test.py`,
  `bat/api/api.yaml` (`operationId: bat.lib.hello_world`, which connexion
  resolves as an import path), `MANIFEST.in`, and the `dockerfile`.
- The dockerfile runs `python -m unittest discover bat.tests`, which only
  discovers `bat/tests/` — `bat/server/tests/` and `bat/example/tests/`
  never run in the container build.
- `--cov-fail-under=100` sits in default `addopts`, so any bare `pytest`
  invocation (including running a single test file) fails on coverage.
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
- Container/compose identity is spread across files that must change
  together: `/opt/bat` in the `dockerfile` is bind-mounted as
  `./:/opt/bat` by `docker-compose.dev.yaml`, and both compose files name
  the service `bat`. Left as-is for now (cosmetic, and only correct as a
  set).

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
- Version had two sources of truth (a `pyproject.toml` literal and a
  `setup.py` import of `_version.py`). Hatchling's `[tool.hatch.version]
  path = ...` hook collapses them to one — a clean upstream fix.
- The poetry manifest's `[tool.pytest.ini_options] addopts` carried
  `--cov=... --cov-fail-under=100`, so coverage ran on every invocation
  and any partial run failed. Moving the gate into a single explicit
  task (OFK's pattern) makes ordinary runs usable.
- `battodo/_version.py` cannot reach 100% coverage: nothing imports it at
  runtime, since the build backend reads it statically. It needs a
  coverage `omit` entry (the poetry manifest had one; a template moving
  to PEP 621 must carry it over).
- The two `argparser` tests were written against
  `Mock(wraps=...).return_value` returning a child mock. Modern CPython
  returns `sentinel.DEFAULT` so the wrapped callable supplies the value,
  and both tests error. The template's test suite is broken on current
  Python and nobody noticed, because the suite could not import at all
  without its dependencies installed.
- `conf_test.py` carried a dead YAML fixture (`EXAMPLE_CONFIG_YAML` /
  `EXAMPLE_CONFIG_DICT`) and a dead `t.config_file_data`, neither ever
  read. The fixture was the suite's only reason to depend on pyyaml.
- `example.config.yaml` does not match the `example.Config` dataclass it
  is supposed to illustrate (the file has `remote_host.api_key/url`; the
  dataclass has a single `parameter: str`).
- ruff 0.16 broadened its default rule set considerably. The imported
  code produced 14 findings under the OFK ruff profile — implicit
  `Optional`, a `dict()` call, unsorted imports, an unsafe yaml loader,
  a bare expression statement. Worth noting that OpenFrameKeeper's lock
  still pins ruff 0.15.22, so it has not met these defaults yet.
- `mypy --strict` reports 74 errors against the template code; the
  non-strict default reports 5 (all implicit-`Optional` in `get_config`
  plus a missing stub). Strict mode is the goal but needs a dedicated
  annotation pass.
- The template pins the deprecated batconf `FileConfig`; see
  [batconf.md](batconf.md).
