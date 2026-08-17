# Cutover — Requirements

> Author: Lundy Bernard
> Date: 2026-08-17
> Branch: cutover-docs
> Status: ACTIVE

## Purpose

Everything that must be in place before btodo replaces the legacy
scripts (`view_todos.py`, `bump_priorities.py`) as the live todo
interface, for both the human operator and AI agents.

## Requirements

### R1 — Human-friendly output format — done

The default `btodo view` output is designed for a human reading a
terminal, not for markdown rendering: column widths are computed against
the content, stdlib only.

**Done** — `battodo/view/render.py` computes the widths and lays each
category out to one shared table width.

### R2 — Agent-friendly output flag — done

A flag selects machine-readable output with a documented schema, so AI
agents consume views without screen-scraping. Errors go to stderr and
failures exit non-zero, so agents branch on them.

**Done** — `--format json` on `view` and `show` (`battodo/cli.py`).

### R3 — Item CRUD operations — done

Agents (and the human) manage individual items end to end through the
CLI — no hand-editing markdown for routine operations:

- **Create** — `add` a task to a list.
- **Read** — `show` one item with its fields and subtasks.
- **Update** — `update` the fields of an existing item.
- **Delete** — `done` (complete) and `scratch` (drop without
  completing).

Every mutation records a journal event carrying the full field delta
(DESIGN.md ## Journal), and writes the markdown line in the same
operation. The journal is the record and the markdown is a view of it
([ADR group 0008](../0008-journal-authority/README.md)); no command
reads the markdown back to correct the journal. The flip that makes the
view fully generated does not block cutover.

**Done** — `add`, `show`, `update`, `done` and `scratch` in
`battodo/cli.py`.

## Operator rulings

Decisions taken for the cutover, recorded here so the checklist below
reads as work, not as open questions.

- **`backlog.md` is parked.** It gets the parked marker.
- **The template list is parked.** It gets the parked marker; reusable
  templates are a future feature (#27).
- **Backfill and the switchover are one atomic step.** The legacy bump
  script inverts btodo's computed rank for `P > 5`, so the two ranking
  systems get no coexistence window — not even one run.
- **The bump mechanic is removed, not ported.** btodo never gains a
  `bump` command; event timestamps drive the computed rank
  ([ADR 0005](../0000-project-bootstrap/0005-computed-rank.md)) in place
  of direct priority mutation.

## Cutover checklist (operational, not code)

- [ ] One sitting, atomic: `btodo backfill` against the live source
      directory, then every automated caller switched from the legacy
      scripts to btodo
- [ ] Parked marker added to live `backlog.md`
- [ ] Parked marker added to the live template list
- [ ] SCHEMA.md updated: `[ADDED:]`, `[ID:]`, parked marker, computed
      rank replacing P-bump; the daily-bump procedure and `[BUMPED:]`
      dropped; reconcile SCHEMA vs `view_todos.py` future-dated
      discrepancy (ADR 0005 flag)
- [ ] Agent operating guide ships with the repo as `SKILL.md`, written
      against the btodo CLI (uses R2 + R3)
- [ ] Legacy scripts retired, `bump_priorities.py` included

## Open research

- Existing `[BUMPED:]` fields in the live lists: strip them during
  backfill, or leave them in place — ADR 0005 retired the field but
  keeps it parsed and round-tripping. Decide at the cutover rehearsal,
  on the live data.

## Success criteria

- [ ] A day of normal use (view, add, complete, bump-free ranking)
      without touching the legacy scripts or hand-editing markdown
- [ ] AI agent completes a full CRUD round-trip via CLI only
- [ ] CI green
