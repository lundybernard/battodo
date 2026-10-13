# Architecture Decision Records

Groups (directories) organize large changes with multiple component
decisions; single decisions are flat ADR files.

**Numbering.** One global sequence covers flat ADRs, group directories,
and the ADRs inside a group — no number is used twice. A group directory
takes its own number, which names the umbrella decision the group
stands for; its component ADRs take the following numbers.

| Entry | Topic | Status |
| ----- | ----- | ------ |
| [0000](0000-project-bootstrap/) | Project bootstrap (ADRs 0001–0006) | Accepted |
| [0007](0007-toml-config-file.md) | TOML config file | Accepted |
| [0008](0008-journal-authority/) | Journal authority (components 0009–0012) | Accepted |
| [0013](0013-cutover/) | Cutover to daily driver (requirements only) | Active |
| [0014](0014-subtask-journal-events.md) | Subtask journal events | Proposed |
| [0015](0015-config-file-location.md) | Config file location | Accepted |
| [0016](0016-property-refactor/) | Property refactor (components 0017–0018) | Accepted |
| [0019](0019-event-attributes/) | Event attributes (components 0020–0023) | Active |
| [0024](0024-cli-inputs-config-and-command.md) | Command inputs beside the configuration | Proposed |
| [0025](0025-reopen-by-update.md) | A closed task reopens through update | Proposed |
| [0026](0026-due-date-factor.md) | A due-date factor on the priority | Proposed |
| [0027](0027-scratch-through-done.md) | A scratch closes a task through done | Proposed |
| [0028](0028-update-repeat.md) | update sets, changes and clears a repeat | Proposed |
