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
  `shutil.copy`/`copy2`, whose chmod/copystat raises
  `PermissionError: [Errno 1]` when the existing destination file
  belongs to another user — even with group write on the directory.
  So a checkout shared between users works for the mutated set and
  fails on the copied set. Workaround: pre-delete the copied set
  before every run (see the `_mutate` task); a tool-side fix would be
  writing copied files the same way mutated ones are written, or
  tolerating a failed chmod.
- **Incremental cache is mtime-based on the copies:** `mutants/` is
  reused when source mtimes look unchanged, and test-only changes do
  not reliably invalidate it — stale survivor lists read as real
  results. `rm -rf mutants/` is the reliable reset before any run
  whose numbers will be quoted.
- **pytest is the only runner:** mutmut 3 drives pytest in-process;
  there is no unittest-runner hook. Harmless for a stdlib-unittest
  suite (pytest collects it unchanged) but it decides the shape of
  the tool env: pytest must exist there and nowhere else.
