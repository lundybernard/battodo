"""Golden tests for the rendered output of the `view` command.

Each test runs the console entry point in process against the fixture
lists in `data/todo/` and compares stdout, byte for byte, with a
committed file in `data/golden/`. Nothing below the entry point is
imported.

The output depends on the clock, the terminal width, and the source
directory, so all three are pinned. The entry point runs in process
because a subprocess's clock cannot be patched.

The fixture lists:

- `work.md`: open window, more items than the abridged view shows.
  Each item pins one rendered behaviour: overdue, due today, a
  clipped long title, open and completed children, a legacy-scale
  priority, a completed item, a future recurrence, a placeholder
  date, and a second heading that is not an open section.
- `chores.md`: shut window; absent from every golden.
- `backlog.md`: parked; the scan steps over it.
- `side-quests.md`: a name outside the category order, so always
  shown. The hyphen renders as a space, and its undated item makes a
  rank with more decimals than the JSON publishes.
"""

from datetime import datetime
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from battodo.cli import TZ

from .cli_runner import run_cli

DATA = Path(__file__).parent / 'data'
TODO_DIR = DATA / 'todo'
GOLDEN_DIR = DATA / 'golden'

# Wednesday mid-morning: the work window is open, the chores window
# is shut. All fixture dates are relative to this instant.
FROZEN = datetime(2026, 8, 5, 10, 30, tzinfo=TZ)
# The layout reads the terminal width from COLUMNS.
WIDTH = '80'
# The environment outranks any config file in the checkout.
SOURCE_VAR = 'BATTODO_VIEW_SOURCE_DIR'
TOP_VAR = 'BATTODO_VIEW_TOP'


def golden(name: str) -> str:
    """Return the committed output named `name`.

    The goldens hold box-drawing characters, so the encoding is
    explicit, not the host default.
    """
    return (GOLDEN_DIR / name).read_text(encoding='utf-8')


class ViewCommandTests(TestCase):
    maxDiff = None

    def setUp(t) -> None:
        # Pin the clock: the rendered output depends on it.
        patcher = patch('battodo.cli.datetime', autospec=True)
        t.datetime = patcher.start()
        t.addCleanup(patcher.stop)
        t.datetime.now.return_value = FROZEN

    def cli(
        t,
        *args: str,
        env: dict[str, str] | None = None,
    ) -> tuple[str, str, object]:
        """Run `view` with `args`, and `env` over the pinned variables."""
        pinned = {'COLUMNS': WIDTH, SOURCE_VAR: str(TODO_DIR)}
        return run_cli(['view', *args], pinned | (env or {}))

    def render(t, *args: str, env: dict[str, str] | None = None) -> str:
        """Run `view` with `args` and return what it wrote to stdout."""
        out, err, code = t.cli(*args, env=env)
        # A misconfigured run reports on stderr and exits non-zero.
        # Check that before diffing stdout.
        t.assertEqual(err, '')
        t.assertEqual(code, 0)
        return out

    def test_view(t) -> None:
        cases = {
            'the human view is the default': ((), 'view.txt'),
            'every open item, not just the top few': (
                ('--all',),
                'view_all.txt',
            ),
            'and a document for a machine to read': (
                ('--format', 'json'),
                'view_json.json',
            ),
            'a chosen count replaces the default five': (
                ('--top', '1'),
                'view_top.txt',
            ),
            'the document is abridged to the same count': (
                ('--top', '1', '--format', 'json'),
                'view_top_json.json',
            ),
            'asking for everything outranks a count': (
                ('--all', '--top', '1'),
                'view_all.txt',
            ),
        }
        for name, (args, recorded) in cases.items():
            with t.subTest(name):
                t.assertEqual(t.render(*args), golden(recorded))

        out, err, code = t.cli('--top', '0')

        with t.subTest('a count below one is a usage error'):
            t.assertIn('argument --top: ', err)
            t.assertIn('must be a whole number of 1 or more', err)

        with t.subTest('which exits non-zero and writes no view'):
            t.assertNotEqual(code, 0)
            t.assertEqual(out, '')

    def test_view_top_is_configured(t) -> None:
        with t.subTest('the environment sets the count'):
            t.assertEqual(t.render(env={TOP_VAR: '1'}), golden('view_top.txt'))

        with t.subTest('the command line outranks the environment'):
            t.assertEqual(
                t.render('--top', '5', env={TOP_VAR: '1'}),
                golden('view.txt'),
            )

        out, err, code = t.cli(env={TOP_VAR: '0'})

        with t.subTest('a configured count below one is reported'):
            t.assertIn('must be a whole number of 1 or more', err)

        with t.subTest('which exits non-zero and writes no view'):
            t.assertNotEqual(code, 0)
            t.assertEqual(out, '')
