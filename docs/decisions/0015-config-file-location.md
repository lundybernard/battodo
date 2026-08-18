# 0015 — Config file location

Status: Accepted
Date: 2026-08-17

## Context

btodo is a daily-driver CLI: it runs from whatever directory the user
happens to be in. Its config file is resolved as `config.toml` in the
working directory, so every run outside a checkout of this repo finds
no file at all. Configuration is therefore env-var-only in practice,
which is the friction [ADR 0006](0000-project-bootstrap/0006-parked-lists.md)
deferred and [ADR 0007](0007-toml-config-file.md) was supposed to end.

[ADR 0007](0007-toml-config-file.md) chose TOML and left the location
open. batconf ships no search order of its own — its quickstart shows
a single app-level constant — so the order is battodo's to define.

Two uses pull in different directions. A user wants one config file
that follows them everywhere. A checkout wants its own lists, so a
sandbox run picks up the sandbox config without touching the user's.

## Decision

battodo searches four locations for its config file, in order:

1. the path given on the command line,
2. the path named by the config-file environment variable, under
   batconf's existing environment naming convention,
3. `battodo.toml` in the working directory,
4. `config.toml` under the XDG user config directory, honouring
   `XDG_CONFIG_HOME`.

The first hit wins. A file the user named must exist; a file the
search finds is optional, and finding none is normal — defaults and
environment variables answer on their own.

Only the working-directory file carries the application name. That
directory holds the files of every tool. The user config file sits in
a `battodo/` directory, which names it already.

## Options

### Option 1 — CLI, environment, working directory, XDG (chosen)
- [pro] The CLI works from any directory, which is what a daily driver has to do
- [pro] A checkout keeps its own config beside its own lists, so a sandbox run cannot reach the user's file
- [pro] XDG is where users already look for the config of a Unix CLI
- [con] Four locations to reason about when a value resolves unexpectedly

### Option 2 — working directory only (status quo)
- [pro] One location, no ambiguity, nothing to explain
- [con] Leaves the CLI unconfigurable everywhere except a checkout — the defect being fixed

### Option 3 — XDG only
- [pro] Two locations fewer, and the user file behaves the same wherever it runs
- [con] A checkout cannot carry its own config, so sandbox runs need the environment variable every time
- [con] A per-project config file would have to be re-invented later

### Option 4 — an explicit path, always
- [pro] Fully unambiguous: the config in use is on the command line
- [con] Puts a path in every invocation of a command meant to be typed dozens of times a day

## Rationale

The order runs from the most explicit statement to the most ambient
one. It matches the source order batconf already applies to values:
what the user states now beats what the user stated once.

Options 2 and 3 each serve one of the two uses and drop the other. The
chain serves both. Its cost is length, and only a surprising lookup
pays that cost.

## Consequences

- **The working directory outranks the user config.** A `battodo.toml`
  beside the lists wins over `~/.config/battodo/config.toml`. The
  application name keeps the shadowing deliberate: no other tool writes
  that file.
- **Test suites must pin the environment.** Discovery reads real
  locations, so any suite that runs the CLI pins `XDG_CONFIG_HOME` to
  keep the developer's own config out of the run.
- **`--env` is inert without a file.** When the search finds nothing,
  no file source exists for the environment name to select.
- **battodo carries the search itself.** batconf has no equivalent, so
  this is upstream signal, logged in `docs/lessons/batconf.md`.
