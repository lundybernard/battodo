# 0000 — Project bootstrap

BatTodo rebuilds the plain-text todo system in `~/todo/` (markdown lists +
helper scripts + a Claude Code skill) as an installable Python CLI
(`btodo` / `btd`) — a personal tool, built fast and loose as a test-bed
project.

Branch: `main`

## Planning docs

| File | Purpose |
| ---- | ------- |
| [DESIGN.md](DESIGN.md) | How the decided design works — grammar, parser, journal, rank |

## ADRs

| # | Title | Status |
| - | ----- | ------ |
| [0001](0001-bootstrap-from-project-template.md) | Bootstrap from lundybernard/project_template | Accepted |
| [0002](0002-batconf-for-configuration.md) | batconf for configuration | Accepted |
| [0003](0003-argparse-bat-cli-pattern.md) | argparse with the BAT CLI pattern | Accepted |
| [0004](0004-storage-architecture.md) | Storage architecture | Accepted |
| [0005](0005-computed-rank.md) | Computed rank | Accepted |
| [0006](0006-parked-lists.md) | Parked lists | Accepted |

## Requirement labels

The ADRs of this group cite three bootstrap requirements by label:

- **R3 — Views.** btodo renders the open items as sorted tables, and
  category time windows filter the default view.
  [ADR 0005](0005-computed-rank.md) amends the sort to computed rank,
  and [ADR 0026](../0026-due-date-factor.md) shows every open task.
- **R4 — Daily bump.** Once a day, every open item that is due or has
  no due date gains one `P`, on every discovered list.
  [ADR 0005](0005-computed-rank.md) supersedes it: rank climbs by
  computation at view time.
- **R6 — Composable list sources.** Views and operations merge several
  list sources: the home list, configured shared lists, and the lists
  in the working directory. It is pending:
  [ADR 0004](0004-storage-architecture.md) leaves it schema-ready but
  not wired, and
  [ADR 0012](../0008-journal-authority/0012-optional-per-project-tool.md)
  merges a foreign list into views without a journal.

## AI assistance disclosure

The planning documents and ADRs in this directory were drafted with the
assistance of Claude Code (Anthropic). The author reviewed and takes
responsibility for all content.
