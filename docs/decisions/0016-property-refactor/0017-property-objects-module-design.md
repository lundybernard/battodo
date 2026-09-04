# 0017 — Property objects as the module design

Status: Proposed
Date: 2026-09-04

## Context

The package carries two module styles. `task.py`, `selection.py`,
`completed.py`, `conf.py` and `view/render.py` are objects: the
constructor stores the inputs, `cached_property` steps derive state,
and methods write. `mutate.py`, `item.py`, `parser.py`, `journal.py`
and half of `view/selection.py` thread state through loose functions
instead.

The split is chronological, not designed. The procedural modules were
written first, and the object modules that followed were not
retrofitted onto them. The cost is visible in each:

- `mutate.py` is 853 lines. Its completion path threads nine locals
  through one function, and two of its helpers take mutable state as an
  argument.
- `item.py` passes one dict through six functions.
- `parser.py` parses in a 47-line loop with a hand-kept stack and a
  flag.
- `journal.py` is a class with no property chain, and its append path
  re-implements the read path's parse inline.
- `view/selection.py` keeps eight module functions beside three
  objects, and one function duplicates a class in `view/render.py`.

Issue #32 records the cost to the tests: a bare function gets a test
class holding a single method, so the suite carries one container per
function and mocks every call across the seam.

## Decision

**Every module that loads, parses, or transforms state in steps is a
property-based object.** The constructor stores its inputs and does no
work. Each `cached_property` derives one step from the step before it.
Writes are methods.

**Pure computation stays as functions.** A function that computes a
value from its arguments and holds nothing keeps its shape.

`lib.py` keeps the boundary functions the user interfaces call. The
layering the CLI depends on
([ADR 0003](../0000-project-bootstrap/0003-argparse-bat-cli-pattern.md))
does not change.

## Options

### Option 1 — Convert the stateful modules, keep pure computation as functions (chosen)

- [pro] The pattern applies where it pays: input/output and multi-step
  derivation
- [pro] Each converted module gains one test class with one method per
  member, which is the class pattern the suite already uses
- [pro] Leaves the smallest surface to convert, so the parity brackets
  stay reviewable
- [con] Two shapes still coexist, so the rule has to be stated rather
  than read off the tree

### Option 2 — Convert every module, pure computation included

- [pro] One shape everywhere, nothing to explain
- [con] A rank computation over a task and a date gains no state to
  cache; the object is a wrapper with one property
- [con] Its callers re-derive the value cheaply and independently, so
  caching would tie them together for no gain

### Option 3 — Leave the mixed style, convert opportunistically

- [pro] No dedicated work; each module converts when it is next touched
- [pro] No parity risk taken on modules nobody is changing
- [con] Has been the standing position, and the procedural modules grew
  during it
- [con] Opportunistic conversion has no parity bracket, so it trades a
  contained risk for a diffuse one

## Rationale

The property pattern earns its place on work that has steps: something
is read, something is derived from it, something is derived from that.
Naming each step as a property makes the sequence inspectable, lets a
test assert one step, and stops the intermediate values from becoming
locals that only the whole function can see. Every module in Option 1's
scope has that shape today, written as locals instead.

Pure computation has no steps to name. Wrapping it buys a container and
costs a construction at every call site. Option 2 would apply the
pattern to satisfy consistency rather than to fix anything, and
consistency is not the reason the pattern was adopted.

Option 3 is the position that produced the current state. The
procedural modules are not stable legacy; they are where the work
happens, and their shape is what makes each change expensive.

## Consequences

- `mutate.py` becomes one command object per write operation. `item.py`
  becomes an object shaped like the completed digest and the view.
  `parser.py` gains a document object that owns the byte-identity
  contract. `journal.py` gains a property chain and one parse path. The
  functions in `view/selection.py` fold into the objects beside them,
  and the duplicated row builder merges into the render class.
- `rank.py` and `repeat.py` do not change.
- Object names are domain nouns chosen per slice, not fixed here.
- Every converted module carries a parity oracle for the length of its
  slice, so the refactor costs a test suite that is written to be
  deleted.
- The unit suites restructure as each module converts: one class per
  subject, one method per member. That is a large test diff riding
  beside each conversion.
- A future module has a rule to apply rather than a precedent to pick:
  steps mean an object, a computed value means a function.
