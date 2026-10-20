# batconf lessons

Findings from battodo's use of batconf, grouped by status. Upstream state
read 2026-10-19 at batconf `main` 5431c24 (0.4.1 docs). battodo locks
0.4.0.

## Open asks

- The quickstart omits the rule that derives an environment variable
  name from the package, the config path, and capitals
  (`BATTODO_VIEW_SOURCE_DIR`). The `EnvSource` docstring
  (`env.py:23-27`) and `migration.rst:307-340` state it. Why: a consumer
  reads the quickstart first, and without the rule reverse-engineers the
  name from source.
- An exemplar pass: docstrings on every descriptor, and annotations in
  the example project (`tests/example/project/`). Why: batconf does not
  yet exemplify its own property-chain pattern. #227 covers only the
  shared Toml/Yaml walk.

## Filed upstream

Issues #254, #255 and #256 date from 2026-10-19.

- #225: `Configuration` has no optional-key access, so each
  `from_config` reads an absent option as
  `getattr(conf, 'name', default)`. The maintainer chooses between a
  falsy missing-sentinel and an explicit `.get`.
- #226: a non-`str` schema default is dropped silently
  (`_default_values` keeps `str` only), and the read raises
  `AttributeError` as though no default existed. battodo keeps every
  config value a string (CLAUDE.md; ADR 0007 amendment). Why: the error
  sends a reader hunting for a missing source.
- #254: an empty TOML file raises `KeyError: 'batconf'`, not a clear
  error. `_config_env` reads `['batconf']['default_env']`, and `_data`
  reads `_config_env` again in its error message, so the second
  `KeyError` escapes (`toml.py:89-95,101-107`; `YamlSource` has the same
  shape, `yaml.py:78,93`).
- #255: `SourceList.get` returns the first truthy value (`source.py:44`)
  where its docstring says the first non-`None` one (`source.py:24`). An
  argparse option with a truthy `default=` shadows the env and file
  sources for good, so battodo leaves such a default unset and lets the
  schema default answer (`--top`).
- #256: file-source errors are raw stdlib exceptions.
  `missing_file_option='error'` raises a bare `FileNotFoundError` at the
  first `.get()`, not at construction, and bad inputs raise `TypeError`
  or `IsADirectoryError`. `'warn'` goes through `logging`, so a host
  `dictConfig` can drop it. No empty source ships for tests. Why: a CLI
  that takes `--conf /bad/path` starts, then fails later with no config
  context.
- #208 (conda-forge package): with no conda package, battodo declares
  batconf as a pixi path source dependency. That costs a filesystem path
  in the dependent's manifest, the `pixi-build` preview in batconf's
  manifest, and a built recipe whose unbounded `batconf` drops the
  `>=0.4.0` bound and the `[toml]` extra. battodo's data point is not
  posted.
- #196 (config file search order): batconf has no search-order or
  env-override convention for a config file, so battodo wrote its own
  (ADR 0015). battodo's data point is not posted.
- #240 (drop Python 3.10): removes the `[toml]` lazy trap, where
  `TomlSource` imports fine and the first real parse on 3.10 raises
  `ImportError`. battodo's floor is 3.11 since battodo #110. The
  fallback still names `toml`, not `tomli` (`pyproject.toml:43`).

## Resolved upstream

- 0.3.1 `FileConfig` printed a deprecation warning on every `btodo`
  run. Removed in 0.4 (#162).
- `pyyaml` stays an optional extra, and `yaml.py` imports it lazily.
- No API reported a derived env name or the resolved source list.
  `EnvSource.env_name` and the reprs landed (#123).
- A deprecated class was removed one release after its first warning.
  0.4.1 deprecates the 0.5.0 removals in advance (#230).
- Deprecation messages and `__qualname__` named the old classes.
  `NamespaceSource` is the class name (`argparse.py:10`), old names
  resolve through `_compat`, and #237 covers the BAT prefix text.
- `migration.rst` called the removed names `Proto`-suffixed. The heading
  is gone from `docs/source`.
- `DataclassConfig` was obsolete, and only the changelog said so.
  `migration.rst:174` says so now.
- `NamespaceSource`'s flat dotted-`getattr` lookup was undocumented. The
  0.4.1 docs state it (`migration.rst:143-172`).
- A 0.3.1 message misspelled "specify". Fixed (#122).
- The migration off the deprecated file source landed: `NamespaceSource`,
  `TomlSource` and `EnvSource` (battodo ADRs 0007, 0015).
