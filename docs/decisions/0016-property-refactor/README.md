# 0016 — Property refactor

**The decision this group names: every module that loads, parses, or
transforms state becomes a property-based object, and the personal
schedule the view hard-codes becomes configuration.** Half the package
already has that shape. The other half threads state through loose
functions, and this group converts it one slice at a time, each slice
refereed by an oracle that pins current behavior and is deleted with
the code it replaced.

ADRs 0017 and 0018 are the component decisions: the module design the
refactor targets, and the one configuration change it carries.

Branch: `property-refactor-plan` — Issue: #32

## Planning docs

| File | Purpose |
| ---- | ------- |
| [REQUIREMENTS.md](REQUIREMENTS.md) | Invariants every slice holds |
| [PLAN.md](PLAN.md) | Slice sequence, per-slice scope, risks |

Object names and module layouts are chosen per slice, in the
implementing PRs, not here.

## Component ADRs

| # | Title | Status |
| - | ----- | ------ |
| [0017](0017-property-objects-module-design.md) | Property objects as the module design | Proposed |
| [0018](0018-schedule-and-timezone-config.md) | Schedule and time zone become configuration | Proposed |

## AI assistance disclosure

The planning documents and ADRs in this directory were drafted with the
assistance of Claude Code (Anthropic). The author reviewed and takes
responsibility for all content.
