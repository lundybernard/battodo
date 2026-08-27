# batconf lessons

Found during the dev-environment cycle (first real install of batconf as
a dependency):

- `FileConfig` emitted a `UserWarning` on construction in released
  0.3.1, and `get_config` built one unconditionally, so every `btodo`
  invocation printed a deprecation warning to stderr before doing any
  work. Resolved: FileConfig removed upstream in 0.4, issue #162 closed.
- `pyyaml` is an optional extra and the file source imports its YAML
  support lazily, so a project that never loads a YAML file needs no
  yaml dependency. Resolved: kept upstream, yaml.py imports lazily,
  extra still declared.

Found during the computed-rank cycle:

- `EnvConfig` is a win: `BATTODO_VIEW_SOURCE_DIR` overrides the `view`
  config section's `source_dir` with no code at all. The gap is
  discoverability — the variable name is *derived* (package, config
  path, caps), and the derivation rule appears in neither the README nor
  the quickstart, so a consumer reverse-engineers it from the source
  list.
- Nothing let a running program report the derived name or the resolved
  source list. Resolved: `EnvSource.env_name` is public and
  `Configuration`/`SourceList` reprs landed, upstream issue #123 closed.
- Migration off the deprecated file source was deferred here, because
  choosing its replacement also chooses the config-file format.
  Resolved: migration landed; battodo chose TOML via `NamespaceSource` +
  `TomlSource` + `EnvSource`, ADRs 0007 and 0015.

Found during the batconf-0.4 migration cycle (2026-08-11). This cycle
was run deliberately docs-first by AI agents, logging every place the
documentation failed them — each item names the failure mode an agent
actually hit, since that is what upstream wants to fix:

- **A deprecated class was removed one release after its first
  warning.** `FileConfig` and `ConfigProtocol` carried 0.3.1's "will be
  removed a future release" warning and were gone in 0.4, so
  `import battodo.conf` died with `ImportError` before any migration
  work started. Resolved: batconf 0.4 released; battodo migrated (ADRs
  0007, 0015). The upstream ask stands: a deprecated class should
  survive one full release cycle between its first warning and its
  removal, and the `Did you mean: 'Configuration'?` hint Python offers
  once it is gone points a migrator at the wrong replacement.
- **Deprecation messages name identifiers that don't match the docs.**
  0.3.1's `FileConfig` warning points at `batconf.sources.yaml.
  YamlConfig`; 0.4 ships `YamlSource`. `CliArgsConfig`'s warning says
  "Use NamespaceConfig from batconf.sources.argparse" while README and
  migration.rst say `NamespaceSource` from `batconf`. Runtime makes it
  worse: `NamespaceSource.__qualname__` prints `NamespaceConfig`,
  `EnvSource.__qualname__` prints `EnvConfig`, and the docstring
  examples still use the old names. An agent cross-checking names
  against the live package concludes the docs are wrong.
- **migration.rst misdescribes its own renames.** It calls the removed
  names `Proto`-suffixed (line 138) when the 0.3 export in the traceback
  is `ConfigProtocol` — *Protocol*-suffixed. The old→new table below it
  is correct; only the prose heading misleads a reader grepping for the
  name they crashed on.
- **`DataclassConfig` is silently obsolete, and only the changelog says
  so.** migration.rst mentions the class solely under the deprecated
  `module=` kwarg, and never tells the migrator that the 0.3
  `DataclassConfig(config_class)` line is dead. That belongs in the
  migration guide, where someone porting a source list will read it.
- **`NamespaceSource`'s lookup rule is documented nowhere** — the
  highest-value gap; it forced a source dive. `get` does
  `attr = '.'.join((path, key)) if path else key` then a *flat*
  `getattr` on the dotted string: nested namespaces resolve to nothing
  and there is no bare-key fallback, while 0.3's `CliArgsConfig`
  ignored the path entirely, so plain argparse dests that worked for
  years silently stop resolving. In battodo this surfaced as a real
  regression (commands raising, flags no-oping) caught only by TDD;
  fix was renaming every dest to the dotted form
  (`battodo.<field>`). The docstring example (`dest='root.host'`)
  implies the rule but never states it.
- **The `[toml]` extra is a lazy trap on Python ≤3.10.** `TomlSource`
  imports fine and mocked suites stay green; the first real parse raises
  `ImportError: ... install the optional extra batconf[toml]`.
  migration.rst documents the extra; quickstart.rst recommends
  `TomlSource` with no caveat. The fallback also targets the
  unmaintained `toml` package rather than `tomli`, the actual `tomllib`
  backport (batconf's `pyproject.toml:43`). Our guard: a real-parse test
  (tmpdir `config.toml` through `get_config`, no mocks) across the
  version matrix — our own py310 suite was green before the extra was
  declared, because every test mocked `TomlSource`.
- **Config-file conventions are thin.** Quickstart shows only an
  app-level constant (`CONFIG_FILE_NAME = str(Path.cwd() /
  "config.ini")`), and no search-order or env-var-override convention
  exists anywhere, so a CLI that runs from any directory has to write
  its own (battodo's ADR 0015).
- **Smaller gaps:** no null/empty source ships for tests, so consumers
  write ad-hoc doubles just like batconf's own suite does; and bad
  inputs give raw `TypeError`/`IsADirectoryError`, not batconf errors.
- **Two of the three `missing_file_option` policies surprised us.**
  `'warn'` routes through `logging`, not `warnings` — the right call for
  warning-gates, but the message reaches stderr only if the host app's
  logging lets it through, and a host `dictConfig` can eat it silently.
  `'error'` raises a bare `FileNotFoundError` — no batconf exception
  type — *lazily at first `.get()`* rather than at construction, so a
  CLI accepting `--conf /bad/path` launches fine and dies later with a
  message carrying no config context. A contextual `ConfigFileNotFound`
  raised eagerly would fix every consumer at once.
- A message in 0.3.1 misspelled "specify" as "speicfy". Resolved:
  upstream issue #122 closed.

Wins worth keeping: the source-list composition survived the migration
untouched — priority order (CLI > env > file > defaults) is still the
model an agent guesses correctly on the first try. And pixi's 3-day
`exclude-newer` cooldown did its job: installing a 2-day-old release of
our own upstream needed a deliberate per-package override
(`[tool.pixi.pypi-exclude-newer]`), so the supply-chain delay held for
everything else while a first-party dependency was exempted on purpose.

Found during the view `--top` cycle:

- **`SourceList.get` returns the first *truthy* value, not the first
  non-`None` one**, though its docstring says non-`None`. An argparse
  option with a non-falsy `default=` fills its namespace key on every
  run, so it shadows the env and file sources under it for good:
  `BATTODO_VIEW_TOP=99` leaves the view at 5, while
  `BATTODO_SHOW_ALL=1` works, because `store_true` defaults to `False`
  and a falsy value falls through. An option that is also a config
  value must therefore leave its argparse default unset and let the
  schema default answer, which is what `--top` does.
- **Config values are strings by design, and the schema enforces it.**
  `_default_values` keeps a field default only when
  `isinstance(f.default, str)`, so `top: int = 5` on a config schema
  never reaches a lookup: the read raises `AttributeError`, as though
  the field carried no default. The rule is right — the environment
  source carries strings and nothing else — and decoding a value to
  the type its consumer needs is the consumer's job, conventionally a
  `from_config` method on the class that requires it. The gap is that
  neither the rule nor this failure mode is documented: the
  `AttributeError` reports a missing value rather than a rejected
  default, which sends a reader hunting for a missing source.

Found during the backdate-completion cycle:

- **`Configuration` has no optional-key access.** `__getattr__` raises
  on a missing key and there is no public `.get`, so an option the user
  left off is read as `getattr(conf, 'name', default)`. Every consumer
  carries the idiom at the point it decodes configuration:
  `Selection.from_config`, `Digest.from_config`, and now
  `Task.from_config`. Convention keeps it contained — decoding lives
  only in `from_config` classmethods, and typed attributes flow out of
  them — but the idiom is the dict workaround, not an API. Two shapes
  are worth weighing against each other: a falsy missing-sentinel,
  which would read as `conf.x or DEFAULT` and therefore needs access
  that does not raise before any operator syntax can help, since a
  plain `or` never calls `__or__`; and an explicit `.get`. The choice
  is the upstream maintainer's, so nothing was routed upstream this
  cycle.
