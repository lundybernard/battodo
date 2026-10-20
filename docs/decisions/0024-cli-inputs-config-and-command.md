# 0024 — Command inputs pass beside the configuration

Status: Accepted (merged 2026-10-11, PR #91)
Date: 2026-10-11

## Context

The CLI parsed every argument to a dest named for a dotted config path,
so each command input reached the command through the resolved
configuration. batconf answers such a lookup from the command line,
then the environment, then the config file. A command input therefore
had three sources where it needs one: `BATTODO_TITLE` renamed the task
an `update` named, `BATTODO_PARENT` turned an `add` into a subtask, and
`BATTODO_DATE` or a `date` in the config file backdated every `done`.

The same lookup takes the first truthy value, not the first non-None
one. An argparse default fills the namespace on every run, so a config
option with a default ignores the environment and the file. `--format`
had one, so `BATTODO_FORMAT` had no effect. A flag read as a string
also misreads the environment: `BATTODO_SHOW_ALL=false` read as true.

Issue #52 recorded the inputs as undeclared on the configuration.

## Decision

btodo splits its arguments into config options and command inputs.

- A config option is a field declared on the config dataclass. Its
  argparse option takes the dotted config path as its dest and takes
  no default, so the schema default answers below the environment and
  the file.
- A command input pertains to one execution. Its argparse option takes
  a bare dest, and the command passes it to `lib` as a keyword argument
  beside the configuration. No environment variable and no config file
  reaches it.
- A `lib` entry point takes the configuration, then the command inputs
  as keyword-only arguments. A keyword of None means that the input was
  not given. A value default, such as the completed period, stays on
  the argparse option.

## Options

### Option 1 — Split config options from command inputs (chosen)

- [pro] Each value has the sources its meaning calls for, and no
  environment variable reaches a selector or a title
- [pro] The configuration declares its whole surface, and the schema
  holds every config default
- [pro] A script calls `lib` with plain keywords and no configuration
  stand-in for its inputs
- [con] Each command forwards its inputs by name, so a new input
  touches the parser, the command and the `lib` signature

### Option 2 — Declare every input as a config field

- [pro] One mechanism, and the dataclass names every value
- [con] The environment and the file still reach every input, which is
  the defect
- [con] A required input such as a selector has no sensible default

### Option 3 — A property object over the configuration per input

- [pro] Names each input with its default and its decode, as #52
  proposed
- [con] Reads the same sources, so it names the leak but keeps it

## Rationale

A configuration holds what stays true across runs. A selector, a title
or a completion date is true of one run only, and a value inherited
from the shell or a file silently changes what that run writes.
Option 1 removes that path. The two other options keep the
configuration as the carrier, so they keep the leak whatever they
declare.

## Consequences

- `format` becomes a declared config field, so `BATTODO_FORMAT` and a
  `format` in the config file now take effect. Its reader refuses a
  value other than text or json, because only the command line passes
  the argparse choices check.
- `view --all` becomes a command input, so `BATTODO_SHOW_ALL` no longer
  reaches the view.
- A value that should follow a shell session but never a file has no
  home in batconf: a declared field is settable from the environment
  and the file alike. Such a value becomes a declared field, or btodo
  reads it from a bootstrap configuration with no file source.
- Each `from_config` method decodes config fields and takes the command
  inputs it forwards as keywords.
