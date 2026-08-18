"""Golden tests for the rendered output of the `completed` command.

The entry point runs against the fixture log in `data/todo/completed.md`
and its stdout is compared, byte for byte, with a committed file in
`data/golden/`. Nothing below the entry point is imported.

The clock is pinned: every period is measured back from it.

Each fixture record pins one behaviour: a record outside every period,
a record one day outside the week, a date out of file order, the pair
inside the week but outside the month, a SCRATCHED record, an ancestry
title, a title carrying fields, an ad-hoc category, and a line that is
no record at all.
"""

from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from battodo.cli import TZ

from .cli_runner import run_cli

DATA = Path(__file__).parent / 'data'
TODO_DIR = DATA / 'todo'
GOLDEN_DIR = DATA / 'golden'

# Wednesday. The week reaches back to 2026-07-30, the month to
# 2026-08-01.
FROZEN = datetime(2026, 8, 5, 10, 30, tzinfo=TZ)
# The environment outranks any config file in the checkout.
SOURCE_VAR = 'BATTODO_VIEW_SOURCE_DIR'


def golden(name: str) -> str:
    """Return the committed output named `name`."""
    return (GOLDEN_DIR / name).read_text(encoding='utf-8')


class CompletedCommandTests(TestCase):
    maxDiff = None

    def setUp(t) -> None:
        patcher = patch('battodo.cli.datetime', autospec=True)
        t.datetime = patcher.start()
        t.addCleanup(patcher.stop)
        t.datetime.now.return_value = FROZEN
        t.env = {SOURCE_VAR: str(TODO_DIR)}

    def render(t, *args: str) -> str:
        """Run `completed` with `args` and return what it wrote."""
        out, err, code = run_cli(['completed', *args], t.env)
        # A failed run reports on stderr and exits non-zero. Check that
        # before diffing stdout.
        t.assertEqual(err, '')
        t.assertEqual(code, 0)
        return out

    def test_completed(t) -> None:
        cases = {
            'the week is the default period': ((), 'completed.txt'),
            'one day of it': (('today',), 'completed_today.txt'),
            'or the month so far': (('month',), 'completed_month.txt'),
            'and a document for a machine to read': (
                ('--format', 'json'),
                'completed_json.json',
            ),
        }
        for name, (args, recorded) in cases.items():
            with t.subTest(name):
                t.assertEqual(t.render(*args), golden(recorded))

    def test_completed_without_a_log(t) -> None:
        """A source with no log is an error a consumer can branch on."""
        with TemporaryDirectory() as empty:
            out, err, code = run_cli(['completed'], {SOURCE_VAR: empty})

        with t.subTest('the message goes to stderr'):
            t.assertIn('completed log not found', err)

        with t.subTest('stdout stays parseable'):
            t.assertEqual(out, '')

        with t.subTest('the exit code is non-zero'):
            t.assertEqual(code, 1)
