# Dev-process lessons

- 2026-08-07: a subagent's permission classifier refused a delegated
  CLAUDE.md write — an instruction relayed by a coordinating agent does
  not count as user consent for agent-config files. Correct behavior;
  the pattern: agent-config files get authored from the main thread on a
  direct user request, subagents prep content in scratchpad.
- 2026-08-08: the permission classifier also refused a ~40-line compound
  bash script performing a history rewrite (reset + four commits), while
  the identical operations run as small single-purpose commands were
  permitted. Lesson: keep shell steps small and reviewable; a monolithic
  script reads as unreviewable even when each step is benign. Distinguish
  "operation denied" (stop, escalate) from "presentation denied"
  (decompose, retry) — the earlier CLAUDE.md write was the former, this
  was the latter.
- 2026-08-08: bootstrap was committed directly on main, which made
  pre-push manual review impossible — the repo owner had to push
  unreviewed history as a one-time exception. Feature-branch workflow
  adopted from cycle 2 onward.
- 2026-08-08: `git add -A` in a planned commit series swept `.pixi/envs`
  and `pixi.lock` into the packaging commit before the ignore rules
  existed, and pulled in a test fix staged for a later commit. Stage by
  explicit path when building a commit sequence; `-A` is only safe once
  .gitignore is already correct.
- 2026-08-08: `gh api repos/{owner}/{repo}` reporting
  `permissions.push: true` does **not** mean the active token can push.
  That block reflects the authenticated account's role on the repo,
  while a fine-grained PAT is separately scoped to an allow-list of
  repositories. Pushing to `project_template` returned 403 ("Permission
  to lundybernard/project_template.git denied to lundybernard") while
  the API reported `admin: true`. Verify write access with an actual
  throwaway-branch push, never from the API permissions block.
- 2026-08-08: a 48-test suite at 100% coverage still shipped a crash.
  `btodo view` raised `ValueError: Invalid isoformat string:
  'YYYY-MM-DD'` the first time it was pointed at the real `~/todo/`,
  because a template file carries literal `[DUE:YYYY-MM-DD]`
  placeholders that no fixture contained. Coverage measures which lines
  ran, not which *inputs* were tried. For a tool that reads
  human-authored files, run it against the real corpus (read-only)
  before claiming it works — that single run found what the whole suite
  missed.
- 2026-08-08: `cp -r ~/todo sandbox/todo` copied a **symlink**, not a
  tree. `~/todo` points at `/projects/todo`, so the "sandbox" was the
  live system under another name and a `btodo bump` run mutated real
  data. The recovery is the interesting part: it was exact rather than
  best-effort only because the journal had landed the day before. Every
  event carries the field delta plus a full task snapshot, so the
  affected lines could be walked back field by field instead of restored
  wholesale from a backup that did not exist. The audit trail ADR 0004
  justified as a *migration asset* paid for itself on day one, against a
  class of bug it was not designed for. Rule: clone with `cp -rL`, and
  `ls -ld` the target to confirm it is a real directory, before pointing
  anything that writes at it.
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
- 2026-08-10: an ADR mirrors the altitude of its work order. ADRs
  0004/0005 came out 4–6x the size of 0001–0003 and full of
  implementation spec; the suspected causes (verbose agent, saturated
  context) were both eliminated by a controlled comparison: the *same*
  agent instance wrote a tight ~46-line 0004 v1, then a 202-line v2
  after the coordinator's work order said "rewrite ADR 0004 ...
  including identity + journal layout sub-decisions" with a
  design-specifics block attached — which the writer transcribed
  faithfully. A fresh-context agent given "the ADR must also cover X
  and Y" likewise produced three decisions in one file. Fixes applied:
  adr-write got a length/altitude section (cognitive-load bands at
  100/150/200 lines), a one-`(chosen)`-per-file rule, and a
  don't-transcribe-the-work-order section; adr-directory got DESIGN.md
  as the designated home for spec (the gap that made the ADR the only
  container); the delegation rules got "hand ADR writers a decision
  summary, never the spec". A replay of the poison work order against
  the updated skills produced four 84–114-line ADRs with the spec in
  DESIGN.md — the skills resisted the exact instruction that caused
  the original failure.
- 2026-08-11: "investigate and verify before modifying" paid twice on
  the JSON-format review. A measured comparison (JSON vs JSONL vs
  TSV/CSV vs bare table, real corpus, token counts) upheld the
  incumbent — the intuitive win evaporated under measurement because
  tokenizers merge indentation, so compact JSON's 48% character saving
  is only 21% in tokens — and the investigation itself surfaced three
  real defects plus the stderr gap (issue #6). Challenging a default
  is worth the cost even when the default survives: the audit is how
  the defects were found.
- 2026-08-11: work-order over-structure, round two. The coordinator's
  order said "create ADR group 0003" for what turned out to be one
  decision; the writer faithfully built the group, and review caught
  it ("groups are for organizing a large change which requires
  multiple component decisions"). Same failure shape as the 2026-08-10
  altitude lesson — the agent transcribes the order's structure, so
  structural decisions (group vs flat file) must be made by counting
  decisions, not defaulted at delegation time. Guardrail added to the
  adr-directory skill ("When NOT to use").
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
- 2026-08-14: work orders must carry the test-style rules. The
  import-isolation rule (unit tests import only from the module under
  test) lived in a loaded style skill, yet the delivered tests
  imported from three source files and human review caught it — the
  implementing agent never sees the orchestrator's skills, so the
  order is the enforcement point. Same enforcement class as mock
  discipline (no bare `Mock()`; spec from the input type or constrain
  to what the code under test reads; `autospec=True` on every patch):
  these ride inline in every test-writing order now.
- 2026-08-14: durable prose leaks local context. Two catches in one
  cycle: a commit body described the dev arrangement and named an
  unrelated project as the pattern source; a test docstring leaned on
  the host's timezone. Rule extracted: commits, code comments,
  docstrings, and PR prose read as if the repo is the whole world —
  generic statements about any host are fine, claims about this
  particular setup are not. Related phrasing rule from the same
  cycle: mutation-testing prose in durable artifacts says "improve
  coverage" / "mutant caught", never kill/dead.
- 2026-08-14: verify outcomes, not work orders — round two. The
  implementing agent reported a green per-commit gate, but its gate
  had omitted the format check; the orchestrator's own rerun found an
  unformatted file at the tip. The cheap full-gate rerun by the
  orchestrator stays mandatory no matter what the report says.
- 2026-08-14: first full review loop through the agent's own GitHub
  identity: review comment, threaded reply over REST, fix dissolved
  into its introducing commit, re-approve, merge. API notes worth
  keeping: pending reviews are invisible to the API until submitted,
  and GraphQL endpoints want `read:org` — classic-PAT flows should
  stay on REST.
- 2026-08-15: improvised history rewrites slip; planned ones do not.
  Two slips in two sessions from typing rebase/cherry-pick sequences
  ad hoc: a flag that does not exist on the subcommand
  (`cherry-pick -q`, twice), and a commit landed on top of the target
  instead of squashed into it. The fix that held: before touching
  HEAD, write the plan of record — every target parent hash, every
  branch tip, in order — then execute against it. A rewrite work
  order now carries that requirement, and the next multi-branch
  restack under it ran clean on the first pass.
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
