# Property refactor — Requirements

> Author: lundybernard
> Date: 2026-09-04
> Branch: property-refactor-plan
> Issue: #32

## Purpose

Convert the remaining function-based modules to property-based objects
without changing what the tool does. These are the invariants that hold
across every slice; the decisions behind them are
[ADR 0017](0017-property-objects-module-design.md) and
[ADR 0018](0018-schedule-and-timezone-config.md), and the slice
sequence is [PLAN.md](PLAN.md).

The refactor is a rewrite of working code. Its risk is silent
behavior drift, so most of what follows pins behavior rather than
describing new behavior.

## Requirements

### R1 — Parse-to-serialize byte identity

Parse followed by serialize returns the input bytes for every valid
list file
([ADR 0004](../0000-project-bootstrap/0004-storage-architecture.md)).
An oracle pins this before the parser changes.

### R2 — Published JSON output shapes

The machine-readable output shapes are a published contract (the
cutover requirements, R2, at
[0013](../0013-cutover/REQUIREMENTS.md)). Each shape is pinned
byte-for-byte before the module that renders it changes.

### R3 — Green at every commit

Every commit keeps all five gates green: unit tests, integration
tests, behavioral tests, the linter, and the type checker. The unit
coverage floor never goes red, at any commit, including the
intermediate commits inside a slice.

### R4 — One bracket per slice

Each slice runs one bracket: pin current behavior in an oracle,
declare the new interface, land the red, land the green, prove parity
against the oracle, cut callers over, retire the old code. Oracles live
in `tests/oracle/`. The retire commit of a slice deletes that slice's
oracle. No oracle outlives its slice.

The R1 and R2 pins are not slice oracles. They pin contracts that
outlive the refactor, so they are permanent tests in the integration
and behavioral suites, and this retire rule does not reach them.

### R5 — The boundary holds

`lib.py` stays the single boundary the user interfaces execute
through, and the guard that keeps the CLI module importing only the
boundary, config, messages, and logging modules stays green.

### R6 — One event per task stream

A mutation writes one journal event per task stream, never one event
covering several tasks
([ADR 0014](../0014-subtask-journal-events.md)).

### R7 — Refactor changes no behavior

A slice records the bugs it finds and fixes none of them. Three
behavior changes are permitted across the whole refactor. Each lands
as a marked non-parity commit, after its slice proves parity, and
updates the oracle in the same commit:

1. The explicit table-width argument is removed from the view.
2. The reserved `prev_hash` and `hash` event fields are removed, as
   [ADR 0011](../0008-journal-authority/0011-union-merge-and-no-hash-chain.md)
   already decided.
3. The schedule and time zone move to configuration, per
   [ADR 0018](0018-schedule-and-timezone-config.md).

### R8 — Durable-artifact scope

Code, docstrings, comments, fixtures, and docs name nothing outside
this project: no unrelated project names, no personal content, no
host or account specifics. Each slice includes a prose pass over the
module it touches.

### R9 — Test standard

Unit tests import the module under test plus the standard library and
nothing else. They assert the outputs of the unit itself, never a
collaborator's rendering. Every patch is auto-specced and every mock
is constrained to what the code under test reads. Unit tests touch no
disk. Each subject gets one test class, with one test method per
member and subtests per code path.

## Success criteria

- [ ] The modules named in ADR 0017 hold their state in
      `cached_property` chains, and pure computation is still
      functions
- [ ] `tests/oracle/` is empty at the end of the last slice
- [ ] The behavior of the tool differs from today only in the three
      changes R7 permits
- [ ] Every commit on every slice branch is green on all five gates
