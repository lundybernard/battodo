# Dev-process lessons

Agent and workflow findings, grouped by status.

## Pending skill promotion

Each entry waits on the owner's ruling on the skill edit that would hold
it. The text stays as recorded until that ruling lands.

- 2026-08-08: a 48-test suite at 100% coverage still shipped a crash.
  `btodo view` raised `ValueError: Invalid isoformat string:
  'YYYY-MM-DD'` the first time it was pointed at the real source
  directory, because a template file carries literal `[DUE:YYYY-MM-DD]`
  placeholders that no fixture contained. Coverage measures which lines
  ran, not which *inputs* were tried. For a tool that reads
  human-authored files, run it against the real corpus (read-only)
  before claiming it works — that single run found what the whole suite
  missed.
- 2026-08-08: a silent empty view. Run by a second user with no
  configured source directory, `btodo view` printed its header and
  exited 0 — `discover_lists` returned `[]` for the missing path, and
  the view rendered a header over nothing. It reads as
  "you have no tasks". A read that finds no source is a configuration
  error, not an empty result: name the resolved path and fail. The suite
  had the wrong behavior *encoded* ("empty directory still renders a
  header"), so 100% coverage actively defended the bug. Second real-user
  run in two days to find something the tests could not.
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
- 2026-08-27: a docs-gap finding names the upstream ref it was read at,
  and gets re-checked against upstream main before it is routed.
  Findings written 2026-08-11 against a dependency's documentation were
  refuted by an upstream commit dated three days earlier — the report
  described a docs state that had already stopped existing, and routing
  it would have spent credibility on a fixed problem.
- 2026-09-04: a retire commit deleted durable tests along with the
  oracle. The oracle had pinned a type that survived the conversion
  unchanged, so it had no old code to die with, and the durable
  assertions it displaced went out in the same commit; six properties
  and a recorded bug were unpinned at the tip while the coverage
  floor stayed at 100 percent (statement coverage, executed through
  other modules). Independent review caught it. Rule candidates for
  the test-driven-refactor skill: the oracle pins only superseded
  surface; the retire diff is read for durable-suite deletions; a
  recorded bug's pin lives in a durable suite, never only in the
  oracle.

## Open

- 2026-08-25: pixi-build has two sharp edges. The python backend cannot
  read a PEP 621 dynamic version, so the pixi manifest repeats the
  version as a literal (`pyproject.toml:44-46`). A manifest error names
  no file, so with a source dependency in the graph, check the
  dependency's manifest first. Why: the root package's missing section
  produces the same words. Next: move to `/pixi-dev-env` or to memory.

## Filed

- 2026-08-08: when a discovery predicate widens, audit what else it
  caught. Why: intent that lives in prose needs a machine-readable form,
  such as the `<!-- battodo:parked -->` marker of ADR 0006. Residual:
  #37.
- 2026-08-28: a review comment names one instance; the follow-up
  extracts the rule and sweeps the codebase. Why: a fix to one instance
  leaves its siblings in place. Home: memories `no-passive-mocks` and
  `breadcrumb-test-values`. Residual sweep: #48.
- 2026-10-03: a value object builds no output form. Each output form is
  a view class that reads the object through its attributes. Why: a new
  form then adds a class, not a member on the value object. Home: ADR
  0017. Residual: #81, #87.

## Resolved

Each rule lives in the home that it names.

- 2026-08-08: reconcile a written spec against observed behaviour before
  you encode either. Why: the spec is a third opinion, not the
  tiebreaker. Home: memory `schema-md-format-only`.
- 2026-08-10: an ADR writer gets a decision summary, never the spec, and
  the decisions are counted before group or flat is chosen. Why: an ADR
  mirrors the altitude of its order. Home: `/adr-write`,
  `/adr-directory`.
- 2026-08-11: when a written finding and a live run disagree, resolve
  the delta before the finding ships. Why: the delta is a third bug.
  Home: `battodo/logconf.py:8`; the template side is in
  [project-template.md](project-template.md).
- 2026-08-11: an experiment order keeps the coordinator's verified facts
  out, and counts every workaround as a finding. Why: an agent graded on
  success hides its workarounds, and the workarounds are the data. Home:
  `/work-orders` "Experiment integrity".
- 2026-08-14: a work order carries the test-style rules. Why: the
  implementing agent never sees the style skill. Home: `/work-orders`.
- 2026-08-14: the orchestrator reruns the full gate, whatever the report
  says. Why: a reported green gate had left out the format check. Home:
  `/work-orders`, universal skill.
- 2026-08-15: durable prose follows ASD-STE100, and commit messages
  follow Conventional Commits and Chris Beams. Why: a named standard is
  checkable, and an adjective is not. Home: universal skill,
  `/commit-message`.
- 2026-08-15: examples in instruction files are schematic, with a
  placeholder for every per-use value. Why: the model draws real output
  from demonstration content. Home: `/work-orders`.
- 2026-08-15 to 2026-10-10: a history rewrite runs against a written
  plan of record. Review changes go up fast-forward and squash only
  after approval. A rewrite that edits every commit, including the fold
  of a reviewed branch, runs as a scripted tree rebuild. An empty
  `git diff <old-tip> HEAD` proves it, or a stat diff plus a range-diff
  when approved edits fold in. Why: improvised rebase sequences slip,
  and the reviewer reads a small delta, never a rewritten branch. Home:
  `/pr-crafting`, `/work-orders`, Engineer memory
  `scripted-tree-rebuild-rewrite`.
- 2026-08-17: two systems that read one stored value differently cut
  over in one step, with no coexistence window. Why: the legacy bump
  pushes `P` past 5, and btodo folds `P > 5` on the legacy scale (ADR
  0005), so one legacy run drops a `P:5` task from 5 to 1.24. Home: this
  entry; the cutover completed, and its ADR group 0013 retired on
  2026-10-19.
- 2026-08-28: oracle tests bracket a conversion: pin the old behaviour
  first, then assert that the new code answers the same. Why: the
  equivalence proof lands in history. Home: `/test-driven-refactor`.
- 2026-09-04: a work-order scope bullet names the target shape per case
  and never paraphrases a rider. Why: the agent follows the concrete
  bullet when the two disagree. Home: memory
  `function-test-class-convention`.
- 2026-09-08: mutation testing runs once at each PR tip as an
  informational gate, and a survivor is a finding, not a block. Why: a
  100% coverage floor still admits weak assertions. Home: memory
  `mutation-gate-informational`.
- 2026-09-09: test suites compose and never inherit: module-level
  fixture functions, and helpers that take the fixture. Why: shared base
  TestCases and reset helpers carry state between tests. Home: the
  work-order test riders, `/python-style`.
- 2026-10-10: the owner reviews by key question. A report and the PR
  reviewer notes lead with the decisions that need a ruling, and the
  rulings fold before the next look. Why: one review round then ends in
  a merge. Home: memory `speed-run-review-posture`.
- 2026-10-11: an agent-facing change lands in `SKILL.md` in the same PR.
  Why: `SKILL.md` is the whole manual of the operating agent. Home:
  CLAUDE.md (#103).
- 2026-10-12: red evidence goes in the report and the PR reviewer notes.
  A `test(RED)` body is empty or a short list of the behaviours covered.
  Why: the commit records the change, and the report carries its
  verification. Home: `/tdd`, `/work-orders`, `/commit-message`.
- 2026-10-12: `[REVIEW FIX]` commits never merge to main. A stacked
  dependent rebases from its old fork point, and a dependent whose new
  base changes the CI workflow pushes to start a run. Why: a rebase from
  the base tip replays merged commits, and a retarget starts no CI run.
  Home: `/pr-crafting` step 5.
