# 0001 — Project bootstrap

BatTodo rebuilds the plain-text todo system in `~/todo/` (markdown lists +
helper scripts + a Claude Code skill) as an installable Python CLI
(`btodo` / `btd`) — a personal tool, built fast and loose as a test-bed
project.

Branch: `main`

## Planning docs

| File | Purpose |
| ---- | ------- |
| [REQUIREMENTS.md](REQUIREMENTS.md) | Testable acceptance criteria |
| [DESIGN.md](DESIGN.md) | How the decided design works — grammar, parser, journal, rank |
| [PLAN.md](PLAN.md) | Phased implementation plan for the storage prototype |

## ADRs

| # | Title | Status |
| - | ----- | ------ |
| [0001](0001-bootstrap-from-project-template.md) | Bootstrap from lundybernard/project_template | Accepted |
| [0002](0002-batconf-for-configuration.md) | batconf for configuration | Accepted |
| [0003](0003-argparse-bat-cli-pattern.md) | argparse with the BAT CLI pattern | Accepted |
| [0004](0004-storage-architecture.md) | Storage architecture | Accepted |
| [0005](0005-computed-rank.md) | Computed rank | Accepted |
| [0006](0006-parked-lists.md) | Parked lists | Accepted |

## AI assistance disclosure

The planning documents and ADRs in this directory were drafted with the
assistance of Claude Code (Anthropic). The author reviewed and takes
responsibility for all content.
