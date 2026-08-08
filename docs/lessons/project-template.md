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
