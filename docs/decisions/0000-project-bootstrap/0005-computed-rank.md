# 0005 — Computed rank

Status: Accepted
Date: 2026-08-08

## Context

Ordering is driven by a stored `P` that a once-daily pass mutates: every
open item with `DUE <= today` or no `DUE` gets `P += 1` and
`BUMPED:today` (SCHEMA.md's daily-bump rule, R4, `btodo bump`). Four
problems have surfaced now that it runs over real data.

- **`P` conflates two things and loses both** — assigned priority plus
  days waited, neither recoverable. Live values run 1–125, and the top
  of every list is a cluster of high-90s items ordered by add-order, not
  importance.
- **It writes to compute.** Ranking is a pure function of the clock, yet
  the design persists it, rewriting hand-edited synced markdown daily
  and churning mtimes. `BUMPED` exists only as a once-per-day guard for
  a mutation that should not happen at all.
- **The answer depends on how often the tool runs.** A laptop left
  closed for a week comes back with stale numbers.
- **Parked lists get swept up.** `backlog.md` declares itself parked in
  its header ("Not surfaced in daily views, not bumped"), but the
  discover-every-list fix for R4 — correct in itself — bumped it too.
  The discovery predicate has no notion of a list opting out.

The author's direction:

> change the bumped/Priority machinery to just be a time-stamp when it
> was added. the priority should be like a multiplier, and we calculate
> each item's rank by how out-dated it is, how close its due-date is, or
> how long it's been waiting.

## Decision

**Rank is computed at view time from a stored add-date, and `P` becomes
a multiplier.** No daily mutation, no `BUMPED` field, no `bump` command.

### The stored fields

- **`[ADDED:YYYY-MM-DD]`** — when the item entered the list, written
  once and never updated. A second extension to SCHEMA.md's grammar
  alongside `[ID:…]` from ADR 0004, tolerated the same way: absent is
  legal.
- **`[P:N]`** — a multiplier on a **0–5 scale**, not a running total.
  `3` is twice as important as `1.5`; `0` parks a single item at rank 0.
  Absent `P` reads as `1` (neutral), *not* `0`.
- **`[BUMPED:…]`** — retired. Still parsed, so it round-trips untouched
  and is stripped from titles, but no longer read or written.

### The formula

`battodo/rank.py`:

```
rank = multiplier × urgency

urgency = 1 + age_score + due_score          # 1.0 … 6.0
```

| Term | Definition | Range |
| ---- | ---------- | ----- |
| `age_score` | `days_since_ADDED / 30`, capped at 2 | 0 … 2 |
| `due_score` (undated) | 0 | 0 |
| `due_score` (due in `d` days, `0 ≤ d < 14`) | `(14 - d) / 14` | 0 … 1 |
| `due_score` (overdue by `n` days) | `1 + n / 7`, capped at 3 | 1 … 3 |

Every term is **bounded**, which is the property the old stored `P`
lacked: urgency can never grow without limit, so the multiplier keeps
its influence forever. Missing or unparseable dates contribute 0 — see
[DESIGN.md](DESIGN.md) for that rule and the walkthrough of the terms.

### Reading legacy `P`

Live files carry bump-inflated values, folded onto the multiplier scale
at read time rather than migrated:

| stored `P` | multiplier |
| ---------- | ---------- |
| absent | `1` |
| `0` … `5` | as written (the new scale) |
| `> 5` | `min(5, 1 + P/25)` — legacy scale, folded |

The fold is **order-preserving**, so no ordering that exists in the live
files today is lost: `P:98 → 4.92` still outranks `P:95 → 4.80`. It
rewrites no file and is idempotent on already-migrated ones, which is
what lets the live system stay untouched indefinitely. Its cost: `P`
values of 6 and above can no longer be written intentionally, so the
usable hand-authored scale is 0–5.

### `ADDED` is backfilled with the migration date

`btodo backfill` stamps `[ADDED:today]` on every open top-level task
that lacks one (mechanics in [DESIGN.md](DESIGN.md)). Legacy tasks
therefore begin accruing age from the migration date, not from when they
were really added — that date is not recoverable from the files.
Running the backfill on the live `~/todo/` is the owner's call.

### Parked lists

Parked lists are a separate decision — see
[ADR 0006](0006-parked-lists.md).

## Options

### Option 1 — Computed rank: multiplier × bounded urgency (chosen)
- [pro] Directly implements the author's direction: `P` is a multiplier, rank is computed from age, due proximity, and lateness
- [pro] Bounded urgency terms mean the multiplier never stops mattering, which is precisely the failure of the stored-`P` scheme
- [con] Rank is no longer visible in the file — you cannot read a list in an editor and know its order without running btodo

### Option 2 — Keep the stored-`P` daily bump
- [pro] Order is legible directly in the markdown, with no tool
- [con] Unbounded inflation, and it destroys the base priority it accumulates onto

### Option 3 — Compute rank, but leave `P` on its unbounded legacy scale
- [pro] No fold table, no scale change, no migration question for `P`
- [con] A newly hand-written `P:3` would be permanently invisible beneath a legacy `P:95` — the two scales cannot coexist

### Option 4 — Uncapped urgency terms
- [pro] Simpler: two straight lines, no cap constants
- [con] Measured on the live data, a 73-day-overdue item scored 57 against 4.8 for everything else — the multiplier stops mattering entirely, reproducing the inflation bug in a new coordinate

### Option 5 — Additive score (`rank = P + age + due`)
- [pro] Easiest to compute by hand and explain
- [con] Contradicts the author's direction; with addition, a low-priority item accumulates its way past a high-priority one, which is the status quo

### Backfilling `ADDED` — part of Option 1

Computed rank cannot rank legacy tasks without an `ADDED`, so how to
backfill one is part of choosing it, not a decision of its own.

Backfilling with the migration date:

- [pro] Honest: the real add-date is not recoverable, and a task's file says nothing about when it appeared
- [pro] Age starts accruing immediately and correctly from a known anchor
- [con] Day one shows no age signal at all across the whole corpus

Backfilling from `DUE` where present, rejected:

- [pro] Yields a real age signal immediately for the overdue items
- [con] Double-counts — the same lateness would drive both `age_score` and `due_score` — and it is a guess presented as data, in a field defined as a record of fact

## Rationale

The direction quoted above is not merely a formula change: it moves
ranking from *stored, mutated state* to a *pure function of recorded
facts*. That is the same move ADR 0004 makes with the event journal, and
the reason to prefer it here is the same — the stored value is a lossy
projection of facts that are cheaper to keep. `ADDED` is a fact.
`BUMPED` was a cache-invalidation token for a computation that did not
need caching.

The bounded terms are the part worth defending: the uncapped first draft
made `P` irrelevant for anything overdue (Option 4). Capping each term
is what keeps the author's word "multiplier" true — with urgency
confined to 1–6, a priority-5 item and a priority-1 item never trade
places on urgency alone unless the gap is genuinely large.

Reading legacy `P` at view time rather than migrating it is a deliberate
asymmetry with `ADDED`, which does get a backfill command. `P` can be
folded correctly without touching a file, so it is; `ADDED` cannot be
invented from a file, so a decision to write one has to be the owner's.

## Consequences

- **R4 (daily bump) is superseded.** The requirement's underlying goal —
  overdue items must keep climbing — is met by `due_score`, computed
  rather than accumulated. `btodo bump` is gone.
- **R3's sort criteria change** from "P desc, then nearest DUE" to "rank
  desc, then nearest DUE". R3's acceptance criterion of output parity
  with `view_todos.py` no longer holds and is deliberately abandoned:
  the whole point is a different order.
- **`age_score` is 0 for the whole corpus on day one.** The waiting half
  of the design only becomes visible over the following weeks; day-one
  ordering comes from the folded multiplier and the due dates.
- **ADR 0004's event vocabulary loses `TaskBumped`** and uses `TaskAdded`
  for the backfill. No journal written by this project contains a
  `TaskBumped` event outside test fixtures and the sandbox, so nothing
  needs replaying; a reader of the log must still tolerate the type.
- **SCHEMA.md diverges further.** Its daily-bump rule and `BUMPED` field
  no longer describe what btodo does, and BatTodo's files now carry
  `ADDED`, `ID`, and a parked marker that the live scripts do not know.
  As with `ID`, the live SCHEMA.md is not edited here; reconciling the
  two is the owner's decision, and the live system's tolerance of
  unknown bracket fields is what makes the divergence safe meanwhile.
- **Ranking is invisible in the source files.** Anyone hand-reading a
  list sees multipliers and dates, not order, so the view gains a Rank
  column for the ordering to be intelligible.
- **The caps are tuning constants, not laws.** They live as named
  module-level constants in `battodo/rank.py` and are expected to move
  once the scheme has been lived with. A revisit is due after the first
  month of accrued `ADDED` ages, when the age term is finally carrying
  weight.
