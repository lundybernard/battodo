# Dev-process lessons

- 2026-08-07: a subagent's permission classifier refused a delegated
  agent-config write, then next day refused a compound bash script whose
  individual commands were all permitted. Rehomed: agent memory
  permission-classifier-denials (operation-denied vs
  presentation-denied).
- 2026-08-08: bootstrap was committed directly on main, which made
  pre-push manual review impossible. Resolved: feature-branch rule is
  project law in CLAUDE.md.
- 2026-08-08: `git add -A` in a planned commit series swept build
  artifacts into the packaging commit before the ignore rules existed,
  and pulled in a test fix staged for a later commit. Rehomed:
  pr-crafting skill (stage by explicit path).
- 2026-08-08: an API permissions block reporting `permissions.push:
  true` does not mean the active token can push, and the later
  review-loop cycle added its own REST-vs-GraphQL notes. Rehomed: agent
  memory github-api-write-verification.
- 2026-08-08: a 48-test suite at 100% coverage still shipped a crash.
  `btodo view` raised `ValueError: Invalid isoformat string:
  'YYYY-MM-DD'` the first time it was pointed at the real `~/todo/`,
  because a template file carries literal `[DUE:YYYY-MM-DD]`
  placeholders that no fixture contained. Coverage measures which lines
  ran, not which *inputs* were tried. For a tool that reads
  human-authored files, run it against the real corpus (read-only)
  before claiming it works — that single run found what the whole suite
  missed.
- 2026-08-08: a sandbox copy that was really a link to the live data let
  a write command mutate real records. The recovery is what is worth
  keeping: it was exact rather than best-effort only because ADR 0004's
  journal had landed the day before — every event carries the field
  delta plus a full task snapshot, so the affected records were walked
  back field by field instead of restored wholesale from a backup that
  did not exist. An audit trail justified as a *migration asset* paid
  for itself against a class of bug it was not designed for. Rehomed
  (the `cp -rL` rule): agent memory.
- 2026-08-08: a silent empty view. Run by the repo owner rather than the
  agent account, `btodo view` printed its header and exited 0 — that
  user has no `~/todo`, `discover_lists` returned `[]` for a missing
  directory, and the view rendered a header over nothing. It reads as
  "you have no tasks". A read that finds no source is a configuration
  error, not an empty result: name the resolved path and fail. The suite
  had the wrong behavior *encoded* ("empty directory still renders a
  header"), so 100% coverage actively defended the bug. Second real-user
  run in two days to find something the tests could not.
- 2026-08-08: widening a discovery predicate is only half a fix. Trading
  five hard-coded category filenames for "any `.md` with a `## Open`
  heading" fixed the silent-skip bug and immediately over-corrected: it
  bumped `backlog.md`, whose header has always read "Not surfaced in
  daily views, not bumped", and it lists `van-trip-prep-template.md` as
  though a template were a category. A structural predicate finds every
  list, including the ones a human knew to leave alone — intent that
  lives in prose needs a machine-readable form (hence the
  `<!-- battodo:parked -->` marker in ADR 0006). When a net gets wider,
  audit what else it caught.
- 2026-08-08: the spec and the implementation of the *same* system
  disagree, and nobody had noticed. `~/todo/SCHEMA.md` — the template of
  record — says to surface open items where `DUE` is absent or
  `DUE <= today`, which would hide every future-dated item. Both
  `view_todos.py` and R3 hide only *future-recurring* items. btodo
  follows the script and R3, because that is the behaviour people
  actually rely on. Lesson: when reimplementing a system, the written
  spec is a third opinion, not the tiebreaker — reconcile it against
  observed behaviour before encoding either. The inconsistency is in the
  live system and is its owner's to reconcile; it is recorded here
  rather than silently resolved in BatTodo's ADRs.
- 2026-08-10: an ADR mirrors the altitude of its work order. The same
  agent produced a 46-line ADR from one order and a 202-line one from
  an order carrying a design-specifics block, which it transcribed
  faithfully; a later order that said "create ADR group 0003" for what
  turned out to be a single decision duly produced a group. So hand ADR
  writers a decision summary, never the spec, and count the decisions
  before choosing group-vs-flat. Resolved: length band and "when not to
  use" landed in the adr-write and adr-directory skills.
- 2026-08-11: a measured comparison upheld the incumbent. Compact JSON's
  48% character saving over the pretty-printed form is only 21% in
  tokens, because tokenizers merge indentation, so the intuitive win
  evaporated and the format stayed as it was. The audit still paid for
  itself: it surfaced three real defects plus the stderr gap (issue #6,
  closed). Challenging a default is worth the cost even when the default
  survives.
- 2026-08-11: when an agent's written finding and a live run disagree,
  the delta is a third bug, not noise. The migration report claimed a
  missing config file warns on stderr; the real CLI run was silent.
  Neither was wrong: the warning exists, and battodo's own
  schema-version-1 `dictConfig` (`disable_existing_loggers=True` by
  default, run after batconf's import) was eating it — a latent bug
  that had silently disabled every third-party logger since bootstrap.
  Resolving the contradiction before shipping the findings document
  was the whole game: publishing the unverified claim upstream would
  have cost the credibility the dogfooding cycle exists to build.
- 2026-08-11: experiment design for docs dogfooding. The brief was
  "find where batconf's docs fail agents", so the coordinator's job
  was to not contaminate the sample: facts the coordinator verified
  itself (TomlSource exists; the extra's version marker) informed the
  decisions, but the implementing agent got a goal-altitude order with
  no API names and an explicit reframe — "every fallback to reading
  batconf source is itself a finding, not a failure; take it freely
  but log it." That reframe matters: an agent graded on success hides
  its workarounds, and the workarounds were the data. Yield: 13
  documented findings in one cycle, including one (the `[toml]` lazy
  trap) the project then reproduced in its own suite the same day.
- 2026-08-14: an observed default is not a requirement. A live probe
  of a dependency's config resolution saw the lookup namespace derive
  from the schema class's `__module__` and recorded that as a hard
  placement constraint — in a docstring and a commit body — when the
  constructor accepts an explicit `path=` two lines above the fallback
  the probe had exercised. The experiment verified what the code
  *does* by default, not what the API *allows*; the false constraint
  shipped and cost a history rewrite to retract. Rule: a constraint
  claim about a dependency is read from its API surface (signature,
  docs, source), never inferred from a default-configuration
  experiment — the probe can only ever confirm behavior, not
  necessity.
- 2026-08-14: work orders must carry the test-style rules — import
  isolation and mock discipline lived in a style skill the implementing
  agent never sees, so the order is the only enforcement point.
  Resolved: integrated into the work-orders skill and two memories.
- 2026-08-14: durable prose leaks local context — a commit body
  described the dev arrangement and named an unrelated project as its
  pattern source, and a test docstring depended on the host's local
  timezone. Resolved: carried in full by agent memory.
- 2026-08-14: verify outcomes, not work orders — round two. The
  implementing agent reported a green per-commit gate, but its gate
  had omitted the format check; the orchestrator's own rerun found an
  unformatted file at the tip. The cheap full-gate rerun by the
  orchestrator stays mandatory no matter what the report says.
- 2026-08-15: improvised history rewrites slip; planned ones do not.
  Two slips in two sessions came from typing rebase/cherry-pick
  sequences ad hoc. Before touching HEAD, write the plan of record —
  every target parent hash, every branch tip, in order — then execute
  against it; the next multi-branch restack under that rule ran clean
  on the first pass. Resolved: required by the work-orders skill.
- 2026-08-15: code prose drifts into dev-process narration unless a
  register is named. A review rejected a whole PR's prose — module
  docstrings narrating fixture design, commit bodies walking through
  reasoning — as "the agent thinking through the problem and writing
  notes to itself." Adopted ASD-STE100 as the named register for all
  code prose (short declarative sentences, active voice, present
  tense), plus a commit-specific rule set: Conventional Commits 1.0.0
  for the header, Chris Beams' seven rules for mechanics, and a house
  rule — the body says only what the commit adds, and never repeats
  what a comment or docstring in the diff already says. Naming an
  external standard beats adjectives ("be concise") in a work order:
  it is checkable, and the rewrite under it was accepted first pass.
- 2026-08-15: worked examples in instruction files leak their
  payload. Concrete example content (invented issue numbers, scopes,
  rationale sentences) reappears in real output — the model treats
  demonstration content as the value space to draw from. Fix pattern:
  keep examples for what prose states badly (whitespace assembly,
  layout), but make them schematic — angle-bracket placeholders for
  every per-use value, one leak-guard line declaring them layout-only
  — and keep at most one concrete phrase where a rule (imperative
  mood) needs demonstrating. Rules stay in prose; examples carry
  layout only.
- 2026-08-27: pushing `fixup!` commits fast-forward for human review,
  and autosquashing only after approval, kept the human gate on
  history without blocking agent progress. The reviewer reads a small
  diff against a named target commit instead of a rewritten branch,
  and the squash that follows has to move no content: an empty
  `git diff <fixup-tip> HEAD` is the proof. Keep it as the default
  shape for review-then-rewrite.
- 2026-08-27: a docs-gap finding names the upstream ref it was read at,
  and gets re-checked against upstream main before it is routed.
  Findings written 2026-08-11 against a dependency's documentation were
  refuted by an upstream commit dated three days earlier — the report
  described a docs state that had already stopped existing, and routing
  it would have spent credibility on a fixed problem.
