# mutmut lessons

Findings from battodo's use of mutmut 3, grouped by status. Upstream state
read 2026-10-19 at mutmut 3.8.0 (`HISTORY.rst`). battodo locks 3.7.0
(`pixi.lock`).

## Open

- Decorated members have no mutant. mutmut skips every decorated
  function except one whose lone decorator is `@staticmethod` or
  `@classmethod`, so `@property`, `@cached_property` and
  `@contextmanager` bodies are not targets. Before you trust a
  zero-survivor line for a module, count its decorated members. When a
  refactor is itself the catch for a survivor, keep the caught line in a
  plain method. Why: a property-heavy style shrinks the mutation surface
  with no report. Home: upstream #387 (open); battodo's data point is
  not posted.
- The copy step fails on a destination file that another user owns.
  `shutil.copy` runs `copystat`, which raises `PermissionError` even
  with group write on the directory. battodo works around it in
  `pyproject.toml:162-171`. An upstream issue is optional.
- Only `rm -rf mutants/` gives a cold run. The cache is mtime-based on
  the copies, and a delete of `mutmut-stats.json` alone remaps only the
  new test ids. Why: a stale survivor list reads as a real result.
  Re-check on 3.8.0, which drops obsolete test ids (#564).

## Resolved upstream

- `do_not_mutate` was file-level only. mutmut `main` has
  `# pragma: no mutate` for a line, a block, and a start/end region;
  3.8.0 fixes its edge cases (#554, #559).
- Decorated classes were skipped whole (`TaskNode`, a `@dataclass`).
  Fixed in 3.8.0 (#480, #539). The fix takes effect when the lock moves
  to 3.8.0.
- A test under `patch.dict(os.environ, ..., clear=True)` removed
  `MUTANT_UNDER_TEST`, so it ran the original code against every
  mutant. Fixed in 3.8.0 (#511, #552). battodo's fixtures remove only
  the battodo variables (`tests/environment.py`, #123). Until the lock
  moves, `rg -n "clear=True"` over the test trees detects a regression.
