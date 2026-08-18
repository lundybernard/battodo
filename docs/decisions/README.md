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
