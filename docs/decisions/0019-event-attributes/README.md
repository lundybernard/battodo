# 0019 — Event attributes

**The decision this group names: facts a user records about a task live
in the journal, and a command that reads the journal shows them.** Facts
about one completion ride on that completion's event as an open
attribute map, so a new kind of fact does not need a schema change. The
static description of a task is a field on the task's own stream.

ADRs 0020–0022 are the component decisions: the attribute map on
completion events, the journaled task description, and the history
command.

Branch: `adr-event-attributes` — Issue: #79

**Status: active.** The work lands after the journal-authority flip
([ADR group 0008](../0008-journal-authority/README.md)). The property
refactor ([ADR group 0016](../0016-property-refactor/README.md)) is
complete.

## Terms

The group uses one word for each meaning:

- **description:** the static text of a task. In the markdown it is the
  indented lines under the task line that carry no checkbox
  ([ADR 0021](0021-task-description-field.md)).
- **note:** a dated annotation in the journal, and the attribute key
  `note` that carries it.

## Planning docs

| File | Purpose |
| ---- | ------- |
| [REQUIREMENTS.md](REQUIREMENTS.md) | Testable acceptance criteria |
| [DESIGN.md](DESIGN.md) | Command surface, payload keys, open questions |

## Component ADRs

| # | Title | Status |
| - | ----- | ------ |
| [0020](0020-event-attribute-map.md) | Completion events carry an open attribute map | Proposed |
| [0021](0021-task-description-field.md) | A task description is a journaled item field | Proposed |
| [0022](0022-history-command.md) | A history command reads the journal | Proposed |

## AI assistance disclosure

The planning documents and ADRs in this directory were drafted with the
assistance of Claude Code (Anthropic). The author reviewed and takes
responsibility for all content.
