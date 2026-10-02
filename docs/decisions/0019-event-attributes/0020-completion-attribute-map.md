# 0020 — Completion events carry an open attribute map

Status: Proposed
Date: 2026-10-01

## Context

btodo journals every write as an event, under the delta contract of
[DESIGN.md ## Journal](../0000-project-bootstrap/DESIGN.md#journal).
After the flip
([ADR 0009](../0008-journal-authority/0009-journal-becomes-authoritative.md))
the journal is the record, and a fact the events do not hold is lost.

No command writes free text on a task today. The completion event
carries the delta, a snapshot of the task, and its ancestry, and
nothing the user supplies.

Users need to record a fact about one completion, such as the
confirmation number of an order. A repeating task must keep one such
fact per cycle, and a later cycle must not overwrite an earlier one
([R1](REQUIREMENTS.md)). Other facts of the same shape appear across
lists: a technician's name on a support call, an appointment date, a
cost or an estimate on a purchase, time spent on a chore. A fixed
schema for these grows with every new kind of fact
([R5](REQUIREMENTS.md)).

## Decision

**A completion event carries an open map of attributes.** `done`
attaches any number of `key=value` attributes to the completion event
it writes. Keys are free-form lowercase identifiers, and values are
text. `note` is the conventional key for free text.

The schema states that the map exists and fixes no vocabulary.
[DESIGN.md](DESIGN.md#completion-attributes) specifies the grammar and
the payload.

## Options considered

### Open attribute map on the completion event (chosen)

- each completion already writes its own event, so per-cycle history
  follows and nothing overwrites an earlier cycle [pro]
- a new kind of fact is a new key, with no schema or code change [pro]
- a reader finds a fact by its key, across tasks and lists [pro]
- values carry no type, and a misspelt key starts a new kind of fact
  without warning [con]

### A single free-text note on the event

- the smallest change: one optional string [pro]
- not queryable; a confirmation number sits inside prose [con]
- each new kind of fact becomes a prose convention that no reader
  enforces [con]

### A fixed set of typed fields per kind of fact

- the write validates each value against its type [pro]
- each new kind needs a schema change and a code change, which R5
  rules out [con]
- the set grows with every list that tracks a new fact [con]

### A static item-level field, overwritten or appended per cycle

- reuses the field grammar the lists already carry [pro]
- an overwrite loses the earlier cycles, which fails R1 [con]
- an append turns a fact about the item into a log of completions,
  which fails R3 [con]

## Rationale

The completion event is already the one record per completion that R1
asks for: one event per finished task, on that task's own stream
([ADR 0014](../0014-subtask-journal-events.md)). Facts about the
completion belong on it, not on the item, because the item outlives
every cycle.

An open map keeps the vocabulary with the user. The facts that motivate
the feature differ by list, and each list adds kinds that no one can
list in advance. A fixed schema turns each new kind into a code change;
a single note turns each new kind into prose that no reader can query.
A map of named keys avoids both costs.

Text values follow the journal's existing practice: the snapshot
already stores every field value as text. Typing would need a
vocabulary, and the vocabulary is what this decision declines to fix.

## Consequences

- `done` gains attribute options, and the completion event gains an
  optional map. An event without one stays valid.
- The completion day becomes a payload key too, because a history must
  show it and `occurred_at` is the ordering key
  ([ADR 0010](../0008-journal-authority/0010-event-ordering-key.md)).
  DESIGN.md specifies it.
- An ancestor that a cascade completes carries no attributes. The rule
  for a checklist item, whose completion event goes on an ancestor's
  stream, is open ([DESIGN.md](DESIGN.md#open-questions)).
- Attributes also appear in the completed log, which is a render of
  the journal ([DESIGN.md](DESIGN.md#completion-attributes)).
- Nothing catches a misspelt key. A reader that lists the keys in use
  is where a check would start.
