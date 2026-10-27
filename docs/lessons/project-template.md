# project_template lessons

Findings from battodo's start on lundybernard/project_template, grouped by
status. Upstream state read 2026-10-19 at template `main` 4acd6a4.
Nothing changed upstream after PR #5.

## Open, ranked

- Example config and fixtures: `example.config.yaml` does not match the
  `example.Config` dataclass that it illustrates, and `conf_test.py`
  carries a dead YAML fixture that is the suite's only reason to depend
  on pyyaml. Why: an example that disagrees with its code teaches the
  wrong schema.
- Packaging: move to PEP 621 with hatchling's
  `[tool.hatch.version] path`, and drop `setup.py`. The entry points and
  the version each have two declarations today, and `setup.py` imports
  the package at build time. Keep the coverage `omit` for
  `_version.py`. Fill `description`, replace the EOL `python = '^3.8'`,
  and replace the `setup.py develop` install text in the README. Why:
  one declaration per fact cannot drift.
- CI over the interpreter range: build the CI matrix and the
  `requires-python` range together, one feature and env per supported
  version, and remove `.travis.yml` and its badge. An app prunes the
  matrix to its real targets at bootstrap. Why: a single job tests the
  one version that the default env pins, so the floor is a claim that no
  run checks. battodo's per-version envs caught two defects that the
  default env passed: argparse quoting on 3.12 only (#62), and a
  `NameError` from eager annotations on 3.10 to 3.13 (#82). A range bump
  follows battodo #110: drop the EOL interpreter everywhere, add the new
  one in the same shape, lock after the cooldown, and apply the ruff
  rules that the new floor enables in the same commit. A battodo ruling
  puts the default env on 3.15 and keeps the `mutation` env on 3.14
  until PyYAML ships a 3.15 wheel (battodo #151). Open battodo ruling:
  the floor version's unit task in the local gate.
- Lint and types: run ruff at its current release, then a mypy
  `--strict` annotation pass. The non-strict default is close to clean.
- Service separation: removing the web service took `server/`, `api/`,
  two CLI subcommands, a test helper, `MANIFEST.in` and every docker
  file. Why: a template for CLIs or services isolates the service behind
  one optional package and one extra. Template issue first.
- Message catalog: every user-facing CLI string in a pure-data module
  with stable keys, and a conformance test that walks the parser against
  it. Why: one seam serves localization, test strings, and the
  mutation-testing boundary, where the catalog is excluded and every
  lookup stays mutated. Template issue first.
- pixi-optional extras: a `mutation` env (mutmut, with pytest collecting
  the unittest suite) and a Hypothesis profile scaffold (`dev` at 100
  examples, `ci` at 1000 with `print_blob`). Condition: the template's
  pixi support stays optional metadata, never a required toolchain. See
  [mutmut.md](mutmut.md) for the tool caveats.

## Filed

- project_template #7: the template fails to import with batconf 0.4.0
  (`FileConfig` and `ConfigProtocol` are gone, and `batconf = '*'` is
  unpinned). The port passes an explicit `Configuration(..., path=)`,
  because the `__module__` fallback goes in batconf 0.5.0. Its checklist
  holds three small fixes: `disable_existing_loggers: False` in
  `logconf.py`, one source for the console-script name in `cli.py`, and
  the coverage gate moved out of the default pytest `addopts`.
- project_template #6: container and service identity is written by hand
  in every docker, compose, server and test file.

## Resolved upstream

- PR #5 (merged 2026-08-27) fixed five items: a stale coverage `omit`,
  the malformed `MANIFEST.in` directive, the dockerfile test discovery,
  two `Mock(wraps=...)` argparser tests, and the TestCase naming.
