# BatTodo — Claude Code project instructions

Personal toy project, fast-paced, not for release. The app doubles as a
test-bed for the project template, batconf, and the development process
itself; the operating procedure below is Claude Code configuration, not
project scope — keep it out of REQUIREMENTS and ADRs.

Personal per-checkout configuration (commit mechanics, private notes)
lives in CLAUDE.local.md (gitignored).

- Work happens on feature branches, never directly on main; branches get
  manual review before merge.

## Configuration values are strings

Every battodo configuration value is a string: in the TOML file, in the
environment, and on the command line. The consumer decodes what it
needs. This is a project design rule rather than operating procedure, so
it belongs in the code and in ADRs — recorded in the 2026-09-19
amendment to docs/decisions/0007-toml-config-file.md.

**Why:** an environment variable holds a string only. One type from
every source keeps each decoder to a single case, where a typed file
value would force every decoder to handle `0` as well as `"0"`.

**How to apply:** a new config field is a `str` dataclass field with a
`str` default, decoded by the consumer that reads it. Keep each
decoder's input a `str`; widening one to accept a non-string is the
change this rule forbids. A typed TOML value is input outside the
contract, so the exit-1 error it produces is a config error to fix in
the file, not a decoder bug.

## Feature-cycle-end evaluation (modified engineering cycle)

When a feature cycle completes, before moving on, evaluate the finished
work for:

1. **project_template improvements** — generalizable fixes to upstream as
   PRs to lundybernard/project_template.
2. **batconf findings** — friction, gaps, and wins to file as upstream
   issues against batconf.
3. **Dev-process lessons** — agent and workflow findings.
4. **Publicizable wins** — post candidates; log privately in
   CLAUDE.local.md.

Record findings 1–3 in docs/lessons/ (informal log, parallel to
docs/decisions/) as they occur; route upstream at cycle boundaries.
