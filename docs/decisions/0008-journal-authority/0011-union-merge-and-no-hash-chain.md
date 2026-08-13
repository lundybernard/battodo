# 0011 — Union merge, no hash chain

Status: Accepted
Date: 2026-08-13

## Context

ADR 0004 left concurrent writes unmerged: two devices syncing the same
`log.jsonl` produce a Syncthing conflict file, and the user cleans it up
by hand. That was tolerable while the journal was a derived audit trail.
Once it is authoritative
([ADR 0009](0009-journal-becomes-authoritative.md)), losing a conflict
file loses state, so merging has to be defined.

ADR 0004 also reserved `prev_hash` and `hash` envelope fields for
OpenFrameKeeper's hash chain, both written as `null` and never
implemented.

An ordering key that travels with the event
([ADR 0010](0010-event-ordering-key.md)) makes a merge possible; this
decision says what the merge is.

## Decision

**Merge is set union of events, deduplicated by `event_id`, sorted by
the composite key, written back over the file.** Reconciling two copies
of a journal means concatenating them, dropping duplicate ids, sorting,
and rewriting.

The journal becomes **append-mostly**: writers append at the end even
when an event sorts earlier, and order is restored at read or at the
next reconcile.

**The reserved `prev_hash` and `hash` fields are dropped.** A chain
asserts an immutable order; rewrite-on-reconcile changes order by
design, so the two cannot coexist.

## Options

### Option 1 — Union merge, dedup by `event_id`, rewrite (chosen)
- [pro] Convergent: any two copies merged in any order produce the same file and the same state
- [pro] The whole implementation is concat, dedup, sort — no per-device bookkeeping
- [pro] Idempotent, so merging an already-merged log is a no-op and repeated syncs are safe
- [con] The file is rewritten, so it is not strictly append-only any more
- [con] Deletes the reserved hash-chain fields, closing that door without having tried it

### Option 2 — One log file per device, merged at read
- [pro] Every file stays strictly append-only, and sync never produces a conflict
- [con] Machinery — device identity, file discovery, N-way read merge — for a problem union merge already solves at this volume
- [con] Was ADR 0004's stated fix for a trigger (recurring conflict files) that has not fired

### Option 3 — Keep the hash chain
- [pro] Tamper-evidence, and shared event vocabulary with OpenFrameKeeper
- [con] A chain assumes an immutable sequence, which rewrite-on-reconcile violates on every merge
- [con] Never implemented, so nothing depends on it and there is no tamper-evidence to lose

### Option 4 — CRDTs
- [pro] Principled convergence with per-field conflict semantics
- [con] Overkill for a single-user tool with a handful of events a day

## Rationale

Union merge is the smallest thing that converges, and convergence is the
whole requirement — a personal todo list needs the same state on every
device, not a proof of what happened first. Dedup by `event_id` is what
makes it idempotent, and the total order from ADR 0010 is what makes it
deterministic; the two together mean merge order cannot be observed in
the result.

Dropping the hash chain is not a rejection of tamper-evidence, it is
recognizing an incompatibility: the chain and rewrite-on-reconcile
cannot both be true. Nothing was built on the reserved fields, so
removing them costs a schema line. If tamper-evidence is wanted later,
it belongs over the sorted, merged view, not over file order.

## Consequences

- The projection fold must be idempotent per stream — replaying the same
  event twice must not change state.
- Competing completions of the same task resolve earliest-wins.
- Competing edits to the same field resolve last-writer-wins.
- Syncthing conflict files on `log.jsonl` become recoverable input to a
  merge rather than manual cleanup.
- ADR 0004's per-device log splitting is retired as the concurrency fix;
  union merge replaces it.
- The envelope diverges from OpenFrameKeeper's on the hash fields. The
  event vocabulary is still shared.
