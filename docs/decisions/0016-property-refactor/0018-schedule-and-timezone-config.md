# 0018 — Schedule and time zone become configuration

Status: Proposed
Date: 2026-09-04

## Context

The view hard-codes one user's working day. The view package names a
single time zone as a module constant. The selection module names the
hours that make each category active on a weekday and at the weekend,
and a fixed set of list names that stay active at every hour.

These values are correct for the person they were written for, wrong
for anyone else, and exactly the kind of value a user expects to change
without editing code. The time zone also cannot be resolved at import
time in the general case: a deployment clock and the user's day
boundary can differ, and only the running system knows the difference.

The project already reads a TOML file with a view section
([ADR 0007](../0007-toml-config-file.md),
[ADR 0015](../0015-config-file-location.md)), so there is a home for
them. The refactor's slice over the selection module is the point at
which those values are being moved anyway
([ADR 0017](0017-property-objects-module-design.md)).

## Decision

**The time zone, the per-category hour windows, and the always-active
list names become fields of the view configuration section, with
neutral defaults.**

The defaults are: the system local time zone; no hour windows, so every
discovered category is active; and no always-active set. A user who
wants a schedule writes one in their own config file.

## Options

### Option 1 — Configuration fields, neutral defaults (chosen)

- [pro] Nothing in the shipped code encodes a person's working day
- [pro] A user with no config file sees everything, which is the
  behavior a new user can reason about without reading the source
- [pro] The system local time zone is what a personal tool means by
  "today" on the machine it runs on
- [con] The current user must write a config file to keep the view they
  have now
- [con] Changes what the tool does out of the box, so it is a non-parity
  commit inside a refactor

### Option 2 — Configuration fields, current values as defaults

- [pro] Configurable, and no user has to change anything
- [pro] Smallest diff, and the behavioral goldens stay valid untouched
- [con] Moves a personal schedule from one durable artifact to another
  rather than removing it
- [con] A second user inherits hours and list names that mean nothing to
  them, and has to discover them before overriding them

### Option 3 — Keep them hard-coded

- [pro] No work, and no new configuration surface to document or test
- [con] Shipped code carries one person's schedule
- [con] The time zone constant is evaluated at import, so it cannot
  follow a machine whose clock differs from the user's day

## Rationale

Defaults in production code are durable artifacts, and a durable
artifact must not carry one person's schedule. That is the whole
argument against Option 2, which is otherwise the cheapest path: it
preserves behavior, but it preserves the thing that is wrong.

The neutral defaults are chosen to be inert rather than sensible. No
hour window is a filter that excludes nothing, which fails visibly and
harmlessly when the user has not configured one. A guessed default
schedule would fail by hiding tasks, which the user only discovers by
missing them.

Empty is also the honest default for the always-active names, which are
a workaround for the hour windows: with no windows there is nothing to
be exempt from.

## Consequences

- A user with no configuration sees every discovered category at every
  hour. This is the behavior change the refactor accepts.
- The behavioral fixtures set these fields in their own TOML file, so
  the goldens stay stable and stop depending on the clock's time zone.
- The view's category filter reads its schedule from configuration
  rather than from a module constant, so it becomes testable without
  patching a clock.
- **Open before implementation:** how the config layer types a numeric
  TOML value. Every configuration value reaches the view as a string
  today, and the item count is decoded at the call site. The hour-window
  fields cannot be typed until that is answered. Recorded as a recon
  item in [PLAN.md](PLAN.md).
- The configuration surface grows by three fields, all of which must be
  documented where the existing view settings are documented.
