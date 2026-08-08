# 0004 — Storage architecture

Status: Draft — open
Date: 2026-08-07

## Context

Storage carries the project's hardest requirements and is deliberately
undecided. Constraints gathered so far:

- Multiple todo lists in different directories must compose into one
  view: a personal home-directory list, explicitly-added lists in
  shared/synced directories, and lists auto-discovered from the working
  directory in project repos (R6).
- The current system is human-edited markdown, synced by Syncthing;
  hand-editability and sync-friendliness have real value today.
- The author is inclined toward an immutable, time-series-style record —
  similar to what OpenFrameKeeper is building — and sees BatTodo as a
  possible test-bed for that design.
- completed.md is already an append-only log; the mutable state lives in
  the category files.

## Decision

Deferred. To be worked through in a dedicated design session before any
storage code is written.

## Options

### Option 1 — Markdown files in place (status quo, parsed)
- [pro] Zero migration; hand-editing and Syncthing keep working
- [pro] The /todo skill and hooks stay functional during transition
- [con] Concurrent edits + sync conflicts land on mutable files; no history

### Option 2 — Immutable event log with projections
- [pro] Time-series record the author wants to explore; natural audit trail
- [pro] Append-only files are the sync-friendliest shape (OpenFrameKeeper test-bed)
- [con] Hand-editing story and markdown compatibility need explicit design
- [con] Biggest build; projections/compaction are real machinery

### Option 3 — SQLite
- [pro] Real query/transaction semantics
- [con] Breaks hand-editing and clean file sync; binary blobs conflict badly

## Rationale

Pending the design session. The composability requirement (R6) and the
event-log inclination interact — source discovery, merge semantics, and
per-list vs global logs all need to be decided together.

## Consequences

- PLAN.md for implementation is deferred until this ADR resolves.
- Parser work (R2) is safe to start: every option consumes the existing
  markdown format either as source of truth or as import/projection.
