# 0005 — Computed rank

Status: Proposed
Date: 2026-08-08

## Context

Ordering is currently driven by a stored `P` that a once-daily pass
mutates: every open item with `DUE <= today` or no `DUE` gets `P += 1`
and `BUMPED:today` (SCHEMA.md's daily-bump rule, R4, implemented as
`btodo bump`). Four problems with that machinery have surfaced now that
it runs over real data:

- **`P` conflates two different things and loses both.** A live value of
  `P:95` is "whatever priority I first assigned, plus the number of days
  this has sat". Neither number is recoverable. Values in the live
  directory range from `1` to `125`, and the top of every list is a
  cluster of high-90s items whose relative order records add-order, not
  importance.
- **It writes to compute.** Ranking is a pure function of the clock, but
  the current design persists it — rewriting hand-edited,
  Syncthing-synced markdown every day, churning mtimes and widening the
  conflict-file surface. `BUMPED` exists purely as an
  only-once-per-day guard for a mutation that should not happen at all.
- **The answer depends on how often the tool is run.** The bump only
  advances when something invokes it (the SessionStart hook). A laptop
  left closed for a week comes back with stale numbers, and a double
  invocation is only prevented by the `BUMPED` guard.
- **Parked lists get swept up.** `backlog.md` declares itself parked in
  its header comment ("Not surfaced in daily views, not bumped"), but
  the discover-every-list fix for R4 — correct in itself — bumped it
  along with everything else. The discovery predicate has no notion of a
  list opting out.

The author's direction:

> change the bumped/Priority machinery to just be a time-stamp when it
> was added. the priority should be like a multiplier, and we calculate
> each item's rank by how out-dated it is, how close its due-date is, or
> how long it's been waiting.

## Decision

**Rank is computed at view time from a stored add-date, and `P` becomes
a multiplier.** No daily mutation, no `BUMPED` field, no `bump` command.

### The stored fields

- **`[ADDED:YYYY-MM-DD]`** — when the item entered the list. Written
  once, never updated. A second extension to SCHEMA.md's grammar,
  alongside `[ID:…]` from ADR 0004, and tolerated the same way: absent
  is legal.
- **`[P:N]`** — a multiplier on a **0–5 scale**, not a running total.
  `3` is twice as important as `1.5`; `0` parks a single item at rank 0.
  Absent `P` reads as `1` (neutral), *not* `0` — an unprioritized item
  still ranks by its dates.
- **`[BUMPED:…]`** — retired. Still parsed (so it is stripped from
  titles and round-trips untouched) but no longer read or written.

### The formula

`battodo/rank.py`, evaluated against today's date in
`America/Los_Angeles`:

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

In words: an item starts at its multiplier, gains a full multiplier's
worth for every month it waits (up to two months), ramps up over the
fortnight before it comes due, and gains another multiplier's worth for
every week it is late (up to two weeks late). Every term is **bounded**,
which is the property the old stored `P` lacked: urgency can never grow
without limit, so the multiplier keeps its influence forever.

A missing or unparseable `ADDED`/`DUE` contributes 0 — placeholder text
such as `[DUE:YYYY-MM-DD]` in the trip-prep template must never change
an outcome, let alone raise.

### Reading legacy `P`

Live files carry bump-inflated values. Rather than require a migration
before btodo is usable, values are folded onto the multiplier scale at
read time:

| stored `P` | multiplier |
| ---------- | ---------- |
| absent | `1` |
| `0` … `5` | as written (the new scale) |
| `> 5` | `min(5, 1 + P/25)` — legacy scale, folded |

The fold is **order-preserving**, so no ordering that exists in the live
files today is lost: `P:98 → 4.92` still outranks `P:95 → 4.80`. It
needs no file to be rewritten and it is idempotent on already-migrated
files, which is what lets the live system stay untouched indefinitely.
Its cost is that `P` values 6 and above can no longer be written
intentionally; the usable hand-authored scale is 0–5.

### Migration

`btodo backfill` stamps `[ADDED:today]` on every open top-level task
that lacks one, across every discovered list, appending a `TaskAdded`
event carrying `"backfilled": true`. It is the repurposed `bump`
command: the same walk, the same journal discipline, run once instead of
daily.

Legacy tasks therefore begin accruing age from the migration date, not
from when they were really added — that date is not recoverable from the
files. **`age_score` is 0 for the whole corpus on day one**, and the
waiting half of the design only becomes visible over the following
weeks; day-one ordering comes from the folded multiplier and the due
dates. Backfill is run against `sandbox/todo` here. Running it on the
live `~/todo/` is the owner's call.

### Parked lists

A list opts out of views by carrying the marker `<!-- battodo:parked -->`
anywhere in the file. `discover_lists` still returns it — so `backfill`
and any future mutation cover it — but `build_view` skips it.

A live `backlog.md` with no marker keeps appearing exactly as it does
today; the opt-out is opt-in, and adding the marker to the live file is
the owner's call. `van-trip-prep-template.md` is the obvious second
candidate: it is a template that has been showing up in views as if it
were a category.

## Options

### Option 1 — Computed rank: multiplier × bounded urgency (chosen)
- [pro] Directly implements the author's direction: `P` is a multiplier, rank is computed from age, due proximity, and lateness
- [pro] Ranking becomes a pure function of (files, clock) — no writes, no mtime churn, no once-per-day guard, no dependence on how often the tool runs
- [pro] Bounded urgency terms mean the multiplier never stops mattering, which is precisely the failure of the stored-`P` scheme
- [pro] Multiplication makes the multiplier a real lever: doubling `P` doubles the rank at every age
- [con] Rank is no longer visible in the file — you cannot read a list in an editor and know its order without running btodo
- [con] Introduces two tuning constants (the caps) that only real use can validate

### Option 2 — Keep the stored-`P` daily bump
- [pro] Order is legible directly in the markdown, with no tool
- [pro] Zero work; the SessionStart hook already does it
- [con] Unbounded inflation, and it destroys the base priority it accumulates onto
- [con] Rewrites every hand-edited synced file daily to record something derivable
- [con] Correctness depends on the bump having been run every single day

### Option 3 — Compute rank, but leave `P` on its unbounded legacy scale
- [pro] No fold table, no scale change, no migration question for `P`
- [con] A newly hand-written `P:3` would be permanently invisible beneath a legacy `P:95` — the two scales cannot coexist
- [con] Keeps the conflated "priority plus days waited" number as the dominant input, which is the thing being fixed

### Option 4 — Uncapped urgency terms
- [pro] Simpler: two straight lines, no cap constants
- [con] Measured on the live data, a 73-day-overdue item scored 57 against 4.8 for everything else — the multiplier stops mattering entirely
- [con] Reproduces the inflation bug in a new coordinate: an ignored item's rank grows forever

### Option 5 — Additive score (`rank = P + age + due`)
- [pro] Easiest to compute by hand and explain
- [con] Contradicts the author's direction — "priority should be like a multiplier"
- [con] With addition, priority and urgency are interchangeable; a low-priority item accumulates its way past a high-priority one, which is the status quo

### Option 6 — Parked lists: in-file marker (chosen)
- [pro] Self-describing and travels with the file — the same place `backlog.md` already states its intent in prose
- [pro] Hand-editable, and applies to any future parked list or template with no code or config change
- [pro] Keeps the list discoverable for mutations while hiding it from views
- [con] A third extension to the SCHEMA.md grammar
- [con] Needs the live file edited to take effect, so the live bug is only *fixable*, not fixed

### Option 7 — Parked lists: multiplier-zero (`P:0` on every item)
- [pro] No new grammar; falls out of the multiplier semantics for free
- [con] Requires rewriting every item in the file, and their real priorities are lost when the list is unparked
- [con] Conflates "this item is parked" with "this list is parked" — the header states the latter
- [con] A hand-added item in a parked list would surface until someone remembered to zero it

### Option 8 — Parked lists: exclusion list in batconf config
- [pro] No file edits at all, and no grammar extension
- [con] Out-of-band: the file says it is parked, but the reason it is hidden lives somewhere else entirely
- [con] Config-file configuration is currently blocked on batconf 0.4.0/`TomlSource`, so this would be env-var-only today

### Option 9 — Backfill `ADDED` with the migration date (chosen)
- [pro] Honest: the real add-date is not recoverable, and a task's file says nothing about when it appeared
- [pro] Age starts accruing immediately and correctly from a known anchor
- [con] Day one shows no age signal at all across the whole corpus

### Option 10 — Backfill `ADDED` from `DUE` where present
- [pro] Yields a real age signal immediately for the overdue items
- [con] Double-counts: the same lateness would drive both `age_score` and `due_score`, amplifying overdue items twice for one fact
- [con] It is a guess presented as data, in a field defined as a record of fact

## Rationale

The direction quoted above is not merely a formula change: it moves
ranking from *stored, mutated state* to a *pure function of recorded
facts*. That is the same move ADR 0004 makes with the event journal, and
the reason to prefer it here is the same — the stored value is a lossy
projection of facts that are cheaper to keep. `ADDED` is a fact.
`BUMPED` was a cache invalidation token for a computation that did not
need caching.

The bounded terms are the part worth defending. The first draft used
uncapped linear growth and was checked against the real lists before
being written down; it produced ranks from 1 to 57 and made `P`
irrelevant for anything overdue. Capping each term is what keeps the
author's word "multiplier" true — with urgency confined to 1–6, a
priority-5 item and a priority-1 item never trade places on urgency
alone unless the gap is genuinely large.

Reading legacy `P` at view time rather than migrating it is a deliberate
asymmetry with `ADDED`, which does get a backfill command. `P` can be
folded correctly without touching a file, so it is; `ADDED` cannot be
invented from a file, so a decision to write one has to be the owner's.

## Consequences

- **R4 (daily bump) is superseded.** The requirement's underlying goal —
  overdue items must keep climbing — is met by `due_score`, computed
  rather than accumulated. `btodo bump` is gone.
- **R3's sort criteria change** from "P desc, then nearest DUE" to "rank
  desc, then nearest DUE". The R3 acceptance criterion of output parity
  with `view_todos.py` no longer holds and is deliberately abandoned:
  the whole point is a different order.
- **ADR 0004's event vocabulary loses `TaskBumped`** and uses `TaskAdded`
  for the backfill. No journal already written by this project contains
  a `TaskBumped` event outside test fixtures and the sandbox, so nothing
  needs replaying; a reader of the log must still tolerate the type.
- **SCHEMA.md diverges further.** Its daily-bump rule and `BUMPED` field
  no longer describe what btodo does, and BatTodo's files now carry
  `ADDED`, `ID`, and a parked marker that the live scripts do not know.
  As with `ID`, the live SCHEMA.md is not edited here; reconciling the
  two is the owner's decision, and the live system's tolerance of
  unknown bracket fields is what makes the divergence safe meanwhile.
- **Ranking is invisible in the source files.** Anyone hand-reading a
  list sees multipliers and dates, not order. The view has to show the
  computed rank for the ordering to be intelligible, so it gains a Rank
  column.
- **The caps are tuning constants, not laws.** They live as named
  module-level constants in `battodo/rank.py` and are expected to move
  once the scheme has been lived with. A revisit is due after the first
  month of accrued `ADDED` ages, when the age term is finally carrying
  weight.
