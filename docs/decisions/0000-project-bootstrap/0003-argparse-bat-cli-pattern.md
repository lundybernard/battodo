# 0003 — argparse with the BAT CLI pattern

Status: Accepted
Date: 2026-08-07

## Context

The CLI needs subcommands (view/top/all/add/done/scratch/bump).
project_template ships an argparse-based `bat.cli:BATCLI` entry-point
pattern; alternatives are typer or click.

## Decision

Build the CLI on stdlib argparse following the BAT CLI pattern from
project_template, exposed as `btodo` and `btd`.

## Options

### Option 1 — argparse + BAT CLI pattern
- [pro] Zero dependencies; YAGNI for a personal tool
- [pro] Exercises and improves the template's own CLI pattern
- [con] More boilerplate than typer for nested subcommands

### Option 2 — typer
- [pro] Concise, modern, good help output
- [con] Extra dependency chain (click); bypasses the template pattern we want to evaluate

### Option 3 — click
- [pro] Mature, composable
- [con] Same external-dependency and template-bypass drawbacks

## Rationale

The template's CLI pattern is part of what this project exists to
exercise; argparse keeps the dependency surface at zero.

## Consequences

- CLI boilerplate stays hand-rolled; if it grows painful, that is
  template feedback, not a reason to silently switch frameworks.
