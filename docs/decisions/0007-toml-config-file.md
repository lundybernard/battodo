# 0007 — TOML config file

Status: Accepted
Date: 2026-08-11

## Context

battodo config has been env-var-only since bootstrap. batconf 0.4.0
ships format-specific file sources — `TomlSource`, `YamlSource`,
`IniSource` — and drops the 0.3 sources battodo imports today, so
`battodo/conf.py` must be rewritten against the new ones this cycle.
Picking the file format is the first decision of that migration.

The gap is already on record: [ADR 0006](0001-project-bootstrap/0006-parked-lists.md)
rejected a config-based exclusion list partly because "config-file
configuration is blocked on batconf 0.4.0/`TomlSource`, so this would
be env-var-only today". That block is now lifted.

## Decision

battodo's config file is TOML, read through batconf's `TomlSource`.

## Options

### Option 1 — TOML via `TomlSource` (chosen)
- [pro] Stdlib `tomllib` on Python 3.11+ — no runtime dependency on the interpreters battodo mostly runs on
- [pro] The repo already speaks TOML (`pyproject.toml`), so contributors need no second config dialect
- [pro] ADR 0006 named `TomlSource` specifically as the thing being waited on
- [con] `tomllib` is 3.11+; battodo's floor is 3.10, where `TomlSource` falls back to the third-party `toml` package via the `batconf[toml]` extra

### Option 2 — YAML via `YamlSource`
- [pro] batconf's historic default was `config.yaml`, so it is the path of least surprise for batconf users
- [con] Needs `pyyaml` as a new runtime dependency on *every* supported interpreter, not just the floor
- [con] Adds a third config dialect to a repo that already writes TOML

### Option 3 — INI via `IniSource`
- [pro] Stdlib `configparser` everywhere, no extra and no version condition
- [con] Weak nesting, and every value arrives as a string — the layered config would have to hand-parse its own types

### Option 4 — Stay env-var-only
- [pro] Simplest; no new source, no dependency question at all
- [con] Leaves ADR 0006's configuration ergonomics permanently on env vars, which is the friction that ADR deferred rather than accepted

## Rationale

The choice is between two costs: TOML's dependency is *conditional* —
one package, on one interpreter version, at the floor — while YAML's is
*unconditional*, paid by every install forever. A cost that shrinks as
the Python floor rises beats one that does not.

The tie-break is that the format is already in the repo. Contributors
read and write `pyproject.toml`; a TOML config file is the same syntax
in a different file, where YAML or INI would be a dialect to learn for
one small file. INI's stdlib parser is free, but its string-only values
would push type handling back into battodo — paying in code for what
the dependency buys.

Dogfooding cuts the same way as [ADR 0002](0001-project-bootstrap/0002-batconf-for-configuration.md):
`TomlSource` is the 0.4.0 source most worth exercising, and friction
found there is upstream signal.

## Consequences

- **The 3.10 floor now has a dependency implication** — battodo must
  either depend on `batconf[toml]` or drop 3.10. The floor is tested
  (the CPython matrix added this cycle), so this is a live constraint,
  not a hypothetical.
- **ADR 0006's rejected option becomes viable** — a config-file
  exclusion list is no longer blocked. ADR 0006 stands on its other
  reasoning; this ADR does not reopen it.
- **Config file location and schema are still open** — this decision
  fixes the format only.
