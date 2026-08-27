"""Round-trip test for `done`, with and without a completion date.

The fixture lists are copied to a temporary directory first: `done`
writes, and the committed fixtures are read-only inputs to the `view`
and `show` goldens.

The clock is pinned, so the day an undated completion falls on is a
fact the test can state. The targets are top-level tasks that do not
repeat: rescheduling reads the completion date too, and that is a
behaviour of its own.
"""

from datetime import datetime
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from battodo.cli import TZ

from .cli_runner import run_cli

FIXTURES = Path(__file__).parent / 'data' / 'todo'
FROZEN = datetime(2026, 8, 5, 10, 30, tzinfo=TZ)
SOURCE_VAR = 'BATTODO_VIEW_SOURCE_DIR'
# The day the work finished, earlier than the day it is logged.
BACKDATE = '2026-07-20'


class DoneCommandTests(TestCase):
    maxDiff = None

    def setUp(t) -> None:
        tmp = TemporaryDirectory()
        t.addCleanup(tmp.cleanup)
        t.source = Path(tmp.name) / 'todo'
        copytree(FIXTURES, t.source)
        t.env = {SOURCE_VAR: str(t.source)}

        patcher = patch('battodo.cli.datetime', autospec=True)
        t.datetime = patcher.start()
        t.addCleanup(patcher.stop)
        t.datetime.now.return_value = FROZEN

    def run_ok(t, *args: str) -> str:
        """Run `args`, require it to succeed, and return its stdout."""
        out, err, code = run_cli(list(args), t.env)
        t.assertEqual(err, '')
        t.assertEqual(code, 0)
        return out

    def read(t, name: str) -> str:
        return (t.source / name).read_text(encoding='utf-8')

    def test_done_on_a_given_date(t) -> None:
        logged = t.run_ok('done', 'Overdue task', '--date', BACKDATE)
        entry = f'{BACKDATE} | work | DONE | Overdue task'

        with t.subTest('the entry carries the date the user gave'):
            t.assertIn(entry, logged)

        with t.subTest('and the log records it under that date'):
            t.assertIn(entry, t.read('completed.md'))

    def test_done_defaults_to_the_clock(t) -> None:
        logged = t.run_ok('done', 'Due today task')

        t.assertIn(
            f'{FROZEN.date().isoformat()} | work | DONE | Due today task',
            logged,
        )

    def test_done_on_an_unreadable_date(t) -> None:
        """A rejected date reports on stderr and writes nothing."""
        before = (t.read('work.md'), t.read('completed.md'))

        out, err, code = run_cli(
            ['done', 'Overdue task', '--date', 'yesterday'],
            t.env,
        )

        with t.subTest('the message names the value it could not read'):
            t.assertIn('yesterday', err)

        with t.subTest('stdout stays parseable'):
            t.assertEqual(out, '')

        with t.subTest('the exit code is non-zero'):
            t.assertEqual(code, 1)

        with t.subTest('and the run wrote nothing'):
            t.assertEqual((t.read('work.md'), t.read('completed.md')), before)
