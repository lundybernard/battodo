# 0008 — Journal authority

**The decision this group names: BatTodo stores its state as an
authoritative event time series, and every other representation is
derived from it.** The markdown lists stop being the source of truth and
become a generated projection; the journal stops being an audit trail
and becomes the store. This supersedes the storage-authority decision of
[ADR 0004](../0000-project-bootstrap/0004-storage-architecture.md),
which made markdown authoritative because the system was hand-edited in
daily use — a constraint that no longer holds.

ADRs 0009–0012 are the component decisions that build up to it: the flip
itself, how events order, how journals merge, and how a project adopts
or drops the tool.

Branch: `journal-authority-adrs`

## Planning docs

| File | Purpose |
| ---- | ------- |
| [REQUIREMENTS.md](REQUIREMENTS.md) | Testable acceptance criteria for the flip |

Design and implementation sequencing land with the refactor itself, not
in this directory.

## Component ADRs

| # | Title | Status |
| - | ----- | ------ |
| [0009](0009-journal-becomes-authoritative.md) | Journal becomes authoritative | Accepted |
| [0010](0010-event-ordering-key.md) | Event ordering key | Accepted |
| [0011](0011-union-merge-and-no-hash-chain.md) | Union merge, no hash chain | Accepted |
| [0012](0012-optional-per-project-tool.md) | btd is an optional per-project tool | Accepted |

## AI assistance disclosure

The planning documents and ADRs in this directory were drafted with the
assistance of Claude Code (Anthropic). The author reviewed and takes
responsibility for all content.
