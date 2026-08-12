# BatTodo — Implementation design

> Author: lundybernard
> Date: 2026-08-10
> Branch: `docs-adr-status`

The specification behind the bootstrap ADRs. Division of labour in this
directory:

| File | Answers |
| ---- | ------- |
| [REQUIREMENTS.md](REQUIREMENTS.md) | What the tool must do |
| ADRs [0001](0001-bootstrap-from-project-template.md)–[0006](0006-parked-lists.md) | What was decided, and why that option |
| **DESIGN.md** | How the decided design actually works |
| [PLAN.md](PLAN.md) | The order the work lands in |

Where a fact lives here, the ADRs link to it rather than restate it.

## Item grammar extensions

BatTodo's files are a superset of `~/todo/SCHEMA.md`'s item grammar.
Three additions, each optional — absent is always legal:

| Field | Introduced by | Written by |
| ----- | ------------- | ---------- |
| `[ID:xxxxxx]` | [ADR 0004](0004-storage-architecture.md) | by `add` at creation; otherwise lazily, on first mediated mutation |
| `[ADDED:YYYY-MM-DD]` | [ADR 0005](0005-computed-rank.md) | once, by `add` or `btodo backfill` |
| `<!-- battodo:parked -->` | [ADR 0006](0006-parked-lists.md) | never — hand-authored, file-level |

## Parser

### Verbatim line retention

The round-trip guarantee (parse → serialize is byte-identical for any
valid file) is met by keeping each source line verbatim on the parsed
node and using *that* string as the serialization source. Mutations
perform targeted substring replacement on the raw line; nothing is
rebuilt from parsed fields.

Rebuilding is not an option. Field order varies line to line in the live
data — `[P:95] [BUMPED:…] [LOE:8] [TAGS:…]` sits next to
`[P:33] [BUMPED:…] [DUE:…] [LOE:1]` — so any canonical-order serializer
would rewrite every line it touched, and every rewritten line is a
Syncthing conflict waiting to happen on a file a human also edits.

### Two distinct discriminators — do not conflate them

The parser makes two different three-way distinctions, on two different
signals. Reconciling them would be a bug:

| Distinction | Signal |
| ----------- | ------ |
| note / continuation line **vs** subtask | presence of a `- [ ]` / `- [x]` checkbox |
| subtask **vs** checklist item (R2) | presence of at least one `[FIELD:…]` |

Indent width is *not* the first discriminator, though it correlates:
notes and continuation lines are indented 6 spaces and subtasks 2. A
6-space-indented line carrying a checkbox is still a subtask.

### Lazy `[ID:…]` injection

Lines parse with or without an ID. On injection the field is appended at
the end of the existing field list, leaving every other field in its
original position — the minimum edit consistent with the round-trip
guarantee.

### List discovery

A markdown file is a todo list if it contains a `## Open` heading.
`discover_lists` returns every such file, including ones marked parked;
only `build_view` filters those out.

## Adding a task

`btodo add <list> <title>` files one new top-level task. Subtasks and
checklist items are out of scope for it — they stay hand-edited until a
command claims them.

**Which file.** `<list>` is a filename stem resolved against
`discover_lists`, so parked lists are valid targets: parking opts a file
out of *views*, not out of being written to. A stem matching nothing is
an error naming the resolved directory and the stems that do exist.
`add` never creates a list — a typo that spawned `wrk.md` would hide the
task rather than file it. Inferring the category from the title
(SCHEMA.md's heuristics) is deferred; the list is always explicit.

**Where in the file.** As the last entry of the `## Open` section, after
the previous item's own notes and children, with every other line kept
verbatim. `parser.append_open` is the primitive that does it: `set_field`
only edits lines that already exist.

**Which fields.** Only the ones the user supplied, in SCHEMA.md's own
order — `P`, `LOE`, `DUE`, `REPEAT`, `TAGS`. Nothing is defaulted: an
absent `P` already reads as 0 in the parser, so writing `[P:0]` would be
the same statement with a false provenance. Two fields are always
stamped — `[ADDED:today]` in the user's local day, since ADR 0005
computes rank from it, and `[ID:]`, because a task btodo itself created
has no reason to wait for the lazy injection hand-written ones get.

**What is checked.** `DUE` must be an ISO date, and is written back
normalised: `date.fromisoformat` accepts more spellings on newer
interpreters, and a line's meaning must not depend on which one wrote
it. `REPEAT` must be a spec `repeat.py` can schedule. `LOE` must be one
of 1, 2, 3, 5, 8. `P` must be a whole number — the parser calls `int()`
on it, so an unreadable one breaks every view of that file. `TAGS` is
free-form and cannot be wrong. Validation runs before anything is
written, so a rejected add leaves both the file and the journal
untouched.

## Journal

One log per source directory: `<source_dir>/.journal/log.jsonl`, JSONL,
one event per line.

### Envelope

Adopted from OpenFrameKeeper's envelope (OFK ADR 0002) so the two
projects share one event vocabulary:

| Field | Value |
| ----- | ----- |
| `seq` | 1-based; equals the line number |
| `event_id` | uuid4 |
| `stream_id` | `task/<id>` |
| `stream_seq` | per-stream counter |
| `type` | see below |
| `schema_version` | `1` |
| `occurred_at` / `recorded_at` | timestamps |
| `prev_hash` / `hash` | both `null`, reserved |
| `metadata` | actor (`user` \| `agent`), source file |
| `payload` | field deltas **plus a full task snapshot** |

Event types: `TaskAdded`, `TaskCompleted`, `TaskScratched`. (`TaskBumped`
was emitted by the retired `bump` command; readers must still tolerate
the type — see ADR 0005.)

The delta contract: `delta` lists every field the mutation wrote to the
markdown, each as `[before, after]` — bookkeeping stamps (`ID`, `ADDED`)
included, so a reverse-applier can undo any event by restoring the
`before` values with no per-command knowledge. `backfill`'s events
predate this ruling and omit `ID` from their deltas; readers must
tolerate them.

### `TaskAdded` payloads

Two writers emit `TaskAdded`, with deliberately different payloads. Both
are `schema_version` 1 and both are permanent; a reader tells them apart
by the `backfilled` key.

`backfill` stamps a field on a task that already existed, so its delta
carries `ADDED` alone, its snapshot is the *pre*-state, and
`"backfilled": true` marks the date as the migration's rather than an
observed fact.

`add` creates the task, so there is no pre-state to describe. Its delta
carries every field written to the line — the supplied ones plus `ADDED`
and `ID` — each as `[null, value]`, and its snapshot is the *post*-state,
read back from the line as written. `backfilled` is absent. Titles never
appear in a delta; the snapshot is where they live.

```json
{
  "type": "TaskAdded",
  "stream_id": "task/3usdig",
  "metadata": {"actor": "agent", "source_file": "chores.md"},
  "payload": {
    "delta": {
      "P": [null, "4"],
      "LOE": [null, "2"],
      "DUE": [null, "2026-09-01"],
      "TAGS": [null, "yard,summer"],
      "ADDED": [null, "2026-08-11"],
      "ID": [null, "3usdig"]
    },
    "snapshot": {
      "title": "Water the tomatoes",
      "done": false,
      "fields": {
        "P": "4",
        "LOE": "2",
        "DUE": "2026-09-01",
        "TAGS": "yard,summer",
        "ADDED": "2026-08-11",
        "ID": "3usdig"
      }
    }
  }
}
```

Envelope fields not shown are as tabled above.

Deferred from OFK's envelope: the hash chain (null, as OFK also does in
v1) and the `correlation_id` / `commit_len` / `commit_index`
commit-boundary machinery. BatTodo emits single-event commits only, so
there is no partial-commit hazard to detect yet. Both are additive when
added, needing no `schema_version` bump.

### Durability and concurrency

- Appended with `O_APPEND` under an advisory `flock`, `fsync` on write
  (OFK's durability rules 1–2).
- Syncthing conflict files are accepted as manual cleanup. No merge
  logic.
- **If per-device splitting becomes necessary** (trigger and reasoning
  in ADR 0004): one log file per device, `log.<device>.jsonl`, merged on
  read. The envelope already supports it — ordering is reconstructable
  from `occurred_at` plus `stream_seq`.

## Rank

The formula and the legacy-`P` fold table are in
[ADR 0005](0005-computed-rank.md); they are the decision. What follows
is the behaviour around them.

### The formula in words

An item starts at its multiplier, gains a full multiplier's worth for
every month it waits (up to two months), ramps up over the fortnight
before it comes due, and gains another multiplier's worth for every week
it is late (up to two weeks late).

### Unparseable dates

A missing or unparseable `ADDED` / `DUE` contributes 0 to its term. This
is a hard robustness rule, not a convenience: `van-trip-prep-template.md`
carries literal `[DUE:YYYY-MM-DD]` placeholder text, and placeholder text
must never change an outcome, let alone raise.

### Backfilling `ADDED`

`btodo backfill` walks every discovered list — parked ones included —
and stamps `[ADDED:today]` on every open top-level task that lacks one,
appending a `TaskAdded` event carrying `"backfilled": true`.

It is the repurposed `bump` command: the same walk and the same journal
discipline, run once instead of daily. Run against `sandbox/todo` in
development; the live `~/todo/` is the owner's call.

## Parked lists

The marker `<!-- battodo:parked -->` may appear anywhere in the file.

`backlog.md` is the case that motivated it. `van-trip-prep-template.md`
is the obvious second candidate — a template that has been appearing in
views as though it were a category. Neither live file is edited by this
project; adding the marker is the owner's call.
