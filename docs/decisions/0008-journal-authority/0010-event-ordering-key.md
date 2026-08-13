# 0010 — Event ordering key

Status: Accepted
Date: 2026-08-13

## Context

Once the journal is authoritative
([ADR 0009](0009-journal-becomes-authoritative.md)), the order events
fold in determines state, so the order has to be a property of the
events themselves rather than of the file that happens to hold them.
Today it is the latter: `seq` is the 1-based line number, and
`stream_seq` is a per-stream counter assigned at append time.

That works for one writer appending to one file. It breaks the moment
two devices append offline and the logs are merged — both assign the
same numbers to different events, and there is no way to tell which came
first. The same weakness blocks the union merge
([ADR 0011](0011-union-merge-and-no-hash-chain.md)), which needs to sort
events that were never written in one sequence.

## Decision

**The authoritative order of a journal is `(occurred_at, event_id)`.**
`occurred_at` is an epoch number; `event_id` is the existing uuid, used
only to break ties deterministically.

`seq` and `stream_seq` demote to derived values, computed at read over
the sorted events. Nothing is read from a stored position.

Epoch numbers, not ISO date-time strings: a sort key should compare as a
number, without a parser, a timezone, or an offset format standing
between two events and their order.

**Epoch unit: integer milliseconds.** JSON integers compare exactly and
port across writers; floats risk representation drift, which is a real
hazard for a value whose whole job is to sort identically on every
device. Millisecond resolution is far beyond what a todo CLI generates,
and collisions are harmless because `event_id` breaks them. The owner
reviews this sub-choice in the PR.

## Options

### Option 1 — `(occurred_at, event_id)` composite key (chosen)
- [pro] Order travels with the event, so merged logs sort without knowing which file they came from
- [pro] Total and deterministic — the uuid tiebreak means no two events ever compare equal
- [pro] Both fields already exist in the envelope; nothing new is written
- [con] Order now depends on device clocks, so a badly skewed clock misplaces events

### Option 2 — Keep line-number `seq` as the order
- [pro] Status quo; costs nothing and is trivially total within one file
- [con] Two devices appending offline assign identical numbers to different events, with no way to resolve the collision
- [con] Ties the order to file position, which rewrite-on-reconcile invalidates

### Option 3 — Hybrid logical clocks
- [pro] Preserves causal order even under clock skew — the correct answer for a real distributed system
- [con] Overkill at human todo volume: a handful of events a day, from devices whose clocks are NTP-synced anyway
- [con] Adds a clock to maintain and reason about, for a failure mode a uuid tiebreak already handles well enough

## Rationale

The requirement is a total order that survives merging, not causal
correctness. At this volume, wall-clock time plus a random tiebreak
delivers it — and delivers it with fields that are already being
written. Hybrid logical clocks are the right tool one or two orders of
magnitude up in concurrency; here they buy accuracy nobody can perceive
in exchange for machinery someone has to maintain.

Demoting `seq` to a derived value is the same move as demoting markdown
to a projection: a stored position is a fact about a file, and files are
no longer the authority.

## Consequences

- Clock skew becomes the ordering failure mode. A device with a wrong
  clock writes events that sort into the wrong place, and the fix is to
  fix the clock — there is no correction mechanism in the format.
- `seq` and `stream_seq` may no longer be read as stable identifiers.
  Anything that persisted one persisted a computed value.
- The journal no longer has to be stored in order, which is what makes
  the append-mostly union merge possible
  ([ADR 0011](0011-union-merge-and-no-hash-chain.md)).
- Timestamps stop being human-readable in the raw file. Reading a
  journal by eye now needs a formatter.
