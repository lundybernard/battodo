# BatTodo — Storage prototype plan

> Author: lundybernard
> Date: 2026-08-08
> Branch: `storage-prototype`

Implements the hybrid storage design in
[ADR 0004](0004-storage-architecture.md). Scope is a prototype: parser,
journal, view, and two mutations. Multi-source composability (R6) is
schema-ready but wired to a single source.

## Phases

Each phase is one commit, tests included — the coverage gate is
package-wide at 100%, so a module and its tests cannot land separately.
`pixi run tests` is green at every commit.

### Phase 1 — Parser (R2, ADR 0004)

`battodo/parser.py`. Full SCHEMA.md item grammar: `P`, `LOE`, `DUE`,
`BUMPED`, `REPEAT` (interval `Nd`/`Nw` and schedule `weekly:DAY` /
`monthly:N`), `TAGS`, plus the `ID` extension. Subtask vs checklist
discrimination (a child is a subtask when it carries at least one
field), `## Open` sectioning, notes/continuation lines.

The parser keeps every line verbatim. Acceptance: parse → serialize is
byte-identical for every valid file, verified in memory against the live
`~/todo/` lists as read-only evidence.

### Phase 2 — Journal (ADR 0004)

`battodo/journal.py`. Append an event to
`<source_dir>/.journal/log.jsonl` under advisory `flock`, `O_APPEND`,
`fsync`. OFK envelope with `seq` equal to line number, `stream_id` of
`task/<id>`, per-stream `stream_seq`, and a payload carrying field
deltas plus a full task snapshot.

Includes lazy `[ID:]` injection: allocate and write an ID into the task
line on first mediated mutation.

### Phase 3 — View (R3)

`battodo/view.py` + `btodo view` / `btodo view --all`. Category time
windows evaluated in `America/Los_Angeles` (the host clock is UTC).
Sort P desc, then DUE asc, no-DUE last. Hide completed items and
future-dated recurring items.

Acceptance: same items in the same order as `view_todos.py` on the live
data. Formatting may differ.

### Phase 4 — `done` (R5)

`btodo done <id-or-title-match>`. Mark `[x]`, log to `completed.md` with
`Parent > Child` ancestry, remove the block when fully done, recompute
`DUE` for `REPEAT` items (interval from completion date; schedule from
the calendar anchor). Appends `TaskCompleted`.

### Phase 5 — `bump` (R4) — landed, then superseded

`btodo bump`. The once-daily `P += 1` pass over every open top-level
item with `DUE <= today` or no `DUE`, setting `BUMPED:today`. Runs over
**all discovered lists** — any `.md` containing a `## Open` heading —
which is the fix for the hard-coded five-category bug that silently
skips `backlog.md`. Appends `TaskBumped`.

Retired by [ADR 0005](0005-computed-rank.md) on the branch below: rank
is computed at view time instead of accumulated in the file, so the
command, the `BUMPED` field, and the `TaskBumped` event all go away.
Running over all discovered lists turned out to be too broad — it bumped
`backlog.md`, which declares itself parked.

## Follow-on — computed rank

> Branch: `computed-rank`, stacked on `storage-prototype`

Implements [ADR 0005](0005-computed-rank.md).

1. **Loud source errors** — a missing or list-free source directory
   raises with the resolved path instead of printing a bare header.
2. **`[ADDED:]`** — parse the new field.
3. **`battodo/rank.py`** — the multiplier fold and the bounded
   age/due urgency terms.
4. **Rank-ordered views** — sort by computed rank, show a Rank column,
   skip lists carrying `<!-- battodo:parked -->`.
5. **`btodo backfill`** — `bump` repurposed to stamp `[ADDED:today]`
   once, emitting `TaskAdded`.

## Out of scope

Deferred with the reasons recorded in ADR 0004: multi-source resolution
(R6 beyond schema readiness), `add` and `scratch` mutations, the event
hash chain, commit-boundary metadata, SessionStart hook replacement
(R8), and any authority flip.

## Guardrail

`~/todo/` is read-only for the duration. Round-trip and view parity are
verified by reading live files into memory; mutations are exercised only
against fixtures. The live system stays in daily use and nothing here
may disturb it.
