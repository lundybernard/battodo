# batconf lessons

Found during the dev-environment cycle (first real install of batconf as
a dependency):

- `FileConfig` emits a `UserWarning` on construction in the released
  0.3.1: "deprecated and will be removed a future release ...
  `batconf.sources.yaml.YamlConfig` should be a direct replacement."
  `get_config` builds one unconditionally, so **every** `btodo`
  invocation prints a deprecation warning to stderr before doing any
  work. Two issues worth filing upstream: the warning fires on a default
  code path rather than on an opt-in one, and `UserWarning` is the wrong
  category — `DeprecationWarning` is hidden from end users by default
  and shown to developers, which is exactly the desired behavior here.
- `CliArgsConfig` is *not* deprecated in released 0.3.1 but *is* in the
  local 0.4.0+dev tree. The BAT architecture notes already say to prefer
  `NamespaceConfig` (`batconf.sources.argparse`), which does exist in
  0.3.1 — so the guidance is ahead of the released deprecation. Anyone
  following the architecture doc against 0.3.1 gets the right answer by
  luck, not because the release tells them.
- Released 0.3.1 lags the local working tree noticeably (0.4.0+dev).
  Evaluating "current batconf" from the repo checkout gives a different
  API surface than `pip install batconf` does; the deprecation state in
  particular differs between them.
- `pyyaml` is an optional extra (`batconf[yaml]`), and `FileConfig`
  imports its YAML support lazily, so a project that only constructs
  `FileConfig` without loading a YAML file needs no yaml dependency.
  That is good layering — worth keeping when `YamlConfig` replaces it.

Found during the computed-rank cycle:

- `EnvConfig` is a win: `BATTODO_VIEW_SOURCE_DIR` overrides the `view`
  config section's `source_dir` with no code at all, which is what makes
  a sandbox dev loop possible while config-file support is still
  deferred. The gap is discoverability — the variable name is *derived*
  (package, config path, caps) and never documented or printed, so it
  has to be reverse-engineered from the source list. A `--show-config`
  dump, or the naming rule stated in the README, would close it.

Migration to `NamespaceConfig` + `YamlConfig` is deferred: swapping
`FileConfig` for `YamlConfig` decides the config-file format and would
make pyyaml a runtime dependency, which belongs with the storage design
(ADR 0004) rather than a dev-tooling cycle.

Found during the batconf-0.4 migration cycle (2026-08-11). This cycle
was run deliberately docs-first by AI agents, logging every place the
documentation failed them — each item names the failure mode an agent
actually hit, since that is what upstream wants to fix:

- **0.3→0.4 is a hard break, not a deprecation window.** `FileConfig`
  and `ConfigProtocol` are removed outright in the release immediately
  after 0.3.1's warning said "will be removed a future release" —
  `import battodo.conf` died with `ImportError` before any migration
  work started. An agent told "migrate off the deprecated API" plans for
  warnings and instead debugs import errors. Python's own hint
  (`Did you mean: 'Configuration'?`) actively misleads.
- **Deprecation messages name identifiers that don't match the docs.**
  0.3.1's `FileConfig` warning points at `batconf.sources.yaml.
  YamlConfig`; 0.4 ships `YamlSource`. `CliArgsConfig`'s warning says
  "Use NamespaceConfig from batconf.sources.argparse" while README and
  migration.rst say `NamespaceSource` from `batconf`. Runtime makes it
  worse: `NamespaceSource.__qualname__` prints `NamespaceConfig`,
  `EnvSource.__qualname__` prints `EnvConfig`, and the docstring
  examples still use the old names. An agent cross-checking names
  against the live package concludes the docs are wrong.
- **migration.rst misdescribes its own renames.** It says the
  "``Proto``-suffixed type names were removed" — but the 0.3 export is
  `ConfigProtocol`, *Protocol*-suffixed, so grepping the guide for the
  name in the traceback finds nothing. The replacement
  (`batconf.types.ConfigP`) is never stated as an old→new mapping.
- **`DataclassConfig` is silently obsolete.** `Configuration` now
  resolves dataclass defaults with no source in the list (verified
  empirically); the quickstart's `get_config` just omits it, and the
  migration guide never says the 0.3 `DataclassConfig(config_class)`
  line is dead. Nothing tells a migrating agent to delete it.
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
  imports fine and mocked suites stay green; the first real parse
  raises `ImportError: ... install the optional extra batconf[toml]`.
  Only the README's install section mentions the extra —
  migration.rst and quickstart.rst recommend `TomlSource` without the
  caveat. The fallback also targets the unmaintained `toml` package
  rather than `tomli`, the actual `tomllib` backport. battodo's fix:
  depend on `batconf[toml]` (the marker no-ops it on 3.11+).
- **Config-file conventions are thin.** Quickstart shows only an
  app-level constant (`CONFIG_FILE_NAME = str(Path.cwd() /
  "config.ini")`); no search order, no env-var override — it suggests
  wiring `--config-file`/`--env` CLI options yourself. battodo
  therefore defines its own `config.toml` constant and invents no env
  var. The `environments` file format (`[batconf]` + `default_env`,
  then env-prefixed tables) had to be reconstructed from source and
  verified end-to-end.
- **Smaller gaps:** `TomlSource.__init__`/`.get` docstrings empty; bad
  inputs give raw `TypeError`/`IsADirectoryError`, not batconf errors.
  Docs-site hole: `/en/latest/sources.html` 404s and the homepage has
  no quickstart code — working examples live only in the GitHub README
  and `docs/source/*.rst`. No null/empty source ships for tests, so
  consumers write ad-hoc doubles just like batconf's own suite does.
- **`missing_file_option` semantics are undocumented, and two of the
  three policies surprised us.** `'warn'` uses `logging`, not
  `warnings` — right call for warning-gates, but the message only
  reaches stderr if the host app's logging lets it through (battodo's
  own `dictConfig` was silently eating it; see project-template.md).
  `'error'` raises a bare `FileNotFoundError` — no batconf exception
  type — and fires *lazily at first `.get()`*, not at construction, so
  a CLI accepting `--conf /bad/path` launches fine and dies later. The
  message carries no config context (`[Errno 2] No such file or
  directory: '<path>'`), unlike the genuinely good `[toml]`-extra
  message that names both cause and fix. A contextual
  `ConfigFileNotFound` raised eagerly would fix every consumer at
  once. battodo's chosen policy: `'ignore'` for the default cwd path,
  `'error'` for an explicitly requested file.
- **The `[toml]` lazy trap reproduced in our own repo within a day** —
  the strongest evidence for the extra-trap finding above: battodo's
  py310 suite was fully green *before* the extra was declared, because
  every test mocked `TomlSource`. Import succeeds, mocked tests pass,
  first real read explodes. The guard is a real-parse test (tmpdir
  `config.toml` resolved through `get_config`, no mocks) run across
  the version matrix.
- **Fixed since 0.3.1, verified:** the "speicfy" typo is gone.

Wins worth keeping: the source-list composition survived the migration
untouched — priority order (CLI > env > file > defaults) is still the
model an agent guesses correctly on the first try; and `pixi`'s 3-day
`exclude-newer` cooldown needed a per-package override
(`[tool.pixi.pypi-exclude-newer]`) to install a 2-day-old release of
our own upstream, which is the cooldown working as designed.
