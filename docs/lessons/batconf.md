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

Migration to `NamespaceConfig` + `YamlConfig` is deferred: swapping
`FileConfig` for `YamlConfig` decides the config-file format and would
make pyyaml a runtime dependency, which belongs with the storage design
(ADR 0004) rather than a dev-tooling cycle.
