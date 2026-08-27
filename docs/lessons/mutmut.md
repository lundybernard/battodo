# mutmut findings

Findings from adopting mutmut 3 (2026-08 mutation-testing cycle) —
upstream issue candidates against boxed/mutmut.

- **`do_not_mutate` is file-level only:** the setting is fnmatch
  against the file path, so there is no way to exempt a region or a
  single string inside an otherwise-mutated file. The docs' obvious
  companion, `# pragma: no mutate`, appears in the source as an
  unimplemented TODO. Consequence here: excluding display strings
  required moving them into their own module (which turned out to be
  a better design anyway, but the tool forced the timing).
- **Copy step breaks on foreign-owned files:** mutated sources are
  written with a plain `open(..., 'w')`, but files that are copied
  unmodified (excluded files, `pyproject.toml`) go through
  `shutil.copy`/`copy2`, whose `copystat` raises
  `PermissionError: [Errno 1]` when the existing destination file
  belongs to another user — even with group write on the directory.
  The tool-side fix is to write copied files the same way mutated ones
  are written, or to tolerate a failed chmod. Resolved: worked around
  in battodo's pyproject.toml, with a comment naming the cause.
- **Incremental cache is mtime-based on the copies:** test-only changes
  do not reliably invalidate `mutants/`, so stale survivor lists read
  as real results. Clear the tree before any run whose numbers will be
  quoted.
- **`@property` bodies are never mutated:** converting a module of
  functions into classes whose computed data lives behind properties
  dropped the project's mutant count from 1614 to 1482 and removed the
  converted logic from the oracle entirely — the survivors in that
  module went to zero partly because the code they lived in stopped
  being a mutation target. A style the house prefers (classes with
  properties over free functions) therefore silently shrinks mutation
  coverage. Compensated locally with 100% line coverage plus a manual
  defect-injection sweep (43 injected defects, 42 caught, 1 provably
  equivalent); upstream issue candidate, since property-heavy code is
  hardly rare. Re-verify before filing: upstream #387 (open) and #480
  (closed) may already cover it — check against installed mutmut 3.6 or
  newer.
