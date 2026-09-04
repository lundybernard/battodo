# Property refactor — Plan

> Author: lundybernard
> Date: 2026-09-04
> Branch: property-refactor-plan
> Issue: #32

Implements [ADR 0017](0017-property-objects-module-design.md) and
[ADR 0018](0018-schedule-and-timezone-config.md) against the invariants
in [REQUIREMENTS.md](REQUIREMENTS.md).

## How the sequence is chosen

Slices run leaf-first by the import graph, so no slice writes an
adapter it later deletes. `mutate.py` is last because it imports the
most and because its interface is set by the slice before it.

One slice is one PR. Inside a slice, mechanical renames and moves ride
at the front of the branch, before the pin, so the oracle and every
commit after it read in the final vocabulary. Each slice then runs the
R4 bracket: pin, declare, red, green, prove parity, cut over, retire.

## Slice 0 — Test cleanup (R9)

Test-only. It runs before any bracket, because the suites that pin
behavior must first assert the right things.

- Rewrite `battodo/tests/mutate_test.py` to assert the calls and
  payloads of the unit itself, with the parser seams patched. Land the
  interaction tests before removing the document-equality tests, so the
  coverage floor never goes red (R3).
- Patch `rank` in the item test and in the view selection sort-key and
  list test classes, so the tests stop asserting a collaborator's
  arithmetic.
- Split the argparser test class (#41).
- Remove the `**fields`, `task()`, `item()` and `record()` helpers from
  the four test modules that define them (#42).
- Apply breadcrumb values to fixtures (#48), including the behavioral
  completed-log fixture and its four goldens.
- Add a target docstring to the sixteen unit test classes that have
  none.
- Rename the `*IsolationTests` classes to `<Subject>Tests`.
- Convert `test_<fn>_<behavior>` methods to subtests, in the unit and
  integration suites.
- Constrain the child mocks in the boundary-module test.

## Slice 1 — Mechanical moves

No behavior change, no oracle. It clears the moves that would otherwise
land inside a bracket.

- Apply the wrapped-signature trailing-comma style repo-wide (#43).
- Move list discovery, category order, item count, and the time zone
  constant out of the view package and into the storage layer, where
  [ADR 0004](../0000-project-bootstrap/0004-storage-architecture.md)
  places list discovery.
- Disambiguate the two `selection` modules by name.
- Prose pass over the module docstrings (R8).
- Remove the dead `TaskNode.priority`.

## Slice 2 — parser (R1, R2)

Pin byte identity and the published JSON shapes first. Both pin
contracts that outlive the refactor, so they land as permanent tests in
the integration and behavioral suites, not as a slice oracle (R4). The
parser then gains a document object that owns the parse and holds the
byte-identity contract.

## Slice 3 — journal (R6)

Give the journal a property chain and one parse path, so `append` stops
re-implementing the read.

Non-parity commit, after parity: drop the `prev_hash` and `hash` fields
(R7.2). Recon before it: confirm the read path accepts entries written
with and without the fields, and that union merge is unaffected.

## Slice 4 — view selection (ADR 0018)

Fold the module functions into the objects beside them, and merge the
task-entry builder with the row class it duplicates.

Two non-parity commits, after parity, in this order:

1. Remove the explicit table-width argument (R7.1). The integration
   call sites that pass a width move to the `COLUMNS` environment
   patch the probe path already uses.
2. Extract the schedule, time zone, and always-active list names to
   configuration (R7.3, ADR 0018).

**Recon before the extraction:** probe how the config layer types a
numeric TOML value. Today every value reaches the view as a string and
the item count is decoded at the call site. The hour-window fields
cannot be typed until that answer is known.

## Slice 5 — selection and task (#47)

Mutation consumes the task object, and the selection record becomes
internal. This slice sets the interface slices 6 and 7 write against.
It runs before the item slice because the item module reads the
selection record today, and the item object must consume the task
object instead.

## Slice 6 — item

Convert the dict threaded through six functions into an object with the
same shape as the completed digest and the view, built on the task
object from slice 5.

## Slice 7 — mutate

Last. Its interface comes from slice 5, and its oracle builds on the
parser and journal objects from slices 2 and 3. `mutate.py` splits into
one command object per write operation.

## Deferred

Filed as follow-ups rather than absorbed:

- The table machinery duplicated between the completed digest and the
  view renderer.
- The configuration inputs that reach the config object through
  fallback lookup without being declared.
- Type annotations on the CLI module, which belong upstream as
  template feedback.

## Issue-tracker writes held for approval

None of these go out before the owner approves this plan:

- File the tolerant-read bug: a non-integer level-of-effort value
  raises in the parser and the whole view exits.
- File the undeclared-configuration-inputs gap.
- Re-scope #28 to the assertion-layer remainder.
- Make #32 the tracking issue, carrying this slice list.
- Note #43 and #47 as absorbed into slices 1 and 5.

## Risks

- **Config typing (slice 4).** The hour-window fields are the first
  numeric configuration the view reads as a number. If the config layer
  hands back strings, the decode point has to be decided before the
  fields are named.
- **The coverage floor during slice 0.** Removing a document-equality
  test drops coverage that the replacement must already carry. Ordering
  is the whole mitigation: the new tests land first.
- **Slice 7 size.** `mutate.py` is the largest module and splits into
  several objects. Split its PR if the oracle bracket cannot stay
  readable in one.
