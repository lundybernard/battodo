"""Round-trip test for the `history` command.

The fixture lists are copied to a temporary directory first: the
narrative writes, and the committed fixtures are read-only inputs to
the `view` and `show` goldens.

The narrative completes a one-shot task, which leaves its list, and
reads its history back from the journal by title and by id. A second
task takes a note and a checklist completion, and its history lists
both, newest first.
"""

from datetime import datetime
from json import loads
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from battodo.journal import Journal
from tests.environment import TZ

from .cli_runner import run_cli

FIXTURES = Path(__file__).parent / 'data' / 'todo'
FROZEN = datetime(2026, 8, 5, 10, 30, tzinfo=TZ)
# The instant the journal records a write at: still 2026-08-04 in TZ.
RECORDED = '2026-08-05T03:30:00+00:00'
SOURCE_VAR = 'BATTODO_VIEW_SOURCE_DIR'


class HistoryCommandTests(TestCase):
    """Round-trip tests for the `history` command."""

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

        patcher = patch('battodo.journal._utc_now', autospec=True)
        patcher.start().return_value = RECORDED
        t.addCleanup(patcher.stop)

    def run_ok(t, *args: str) -> str:
        """Run `args`, require it to succeed, and return its stdout."""
        out, err, code = run_cli(list(args), t.env)
        t.assertEqual(err, '')
        t.assertEqual(code, 0)
        return out

    def test_finished_task(t) -> None:
        t.run_ok(
            'done',
            'Overdue task',
            '--date',
            '2026-08-03',
            '--attrs',
            'cost=45.00, place=Main St, Suite 4',
            '--note',
            'Paid at the desk',
        )
        (completed,) = Journal(t.source).events
        task_id = completed['stream_id'].removeprefix('task/')
        expected = (
            f'Overdue task [ID:{task_id}]\n'
            '  2026-08-03  TaskCompleted\n'
            '    cost=45.00\n'
            '    place=Main St, Suite 4\n'
            '    note=Paid at the desk\n'
        )

        with t.subTest('show no longer reaches the finished task'):
            _, err, code = run_cli(['show', 'Overdue task'], t.env)
            t.assertEqual(code, 1)
            t.assertIn('no open task matches', err)

        with t.subTest('part of its title reaches it in the journal'):
            out = t.run_ok('history', 'overdue')
            t.assertEqual(out, expected)

        with t.subTest('and so does its id'):
            out = t.run_ok('history', task_id)
            t.assertEqual(out, expected)

        with t.subTest('the JSON form carries the same document'):
            out = t.run_ok('history', task_id, '--format', 'json')
            t.assertEqual(
                loads(out),
                {
                    'id': task_id,
                    'title': 'Overdue task',
                    'entries': [
                        {
                            'kind': 'TaskCompleted',
                            'checklist_item': False,
                            'day': '2026-08-03',
                            'attrs': {
                                'cost': '45.00',
                                'place': 'Main St, Suite 4',
                                'note': 'Paid at the desk',
                            },
                        },
                    ],
                },
            )

    def test_open_task(t) -> None:
        t.run_ok('note', 'Legacy priority', 'Waiting on the vendor')
        t.run_ok('done', 'Open checklist item')
        stamp, *_ = Journal(t.source).events
        task_id = stamp['stream_id'].removeprefix('task/')

        out = t.run_ok('history', 'legacy')

        t.assertEqual(
            out,
            f'Legacy priority task [ID:{task_id}]\n'
            '  2026-08-05  TaskCompleted (checklist item)\n'
            '  2026-08-04  TaskAnnotated\n'
            '    note=Waiting on the vendor\n',
        )

    def test_reopened_task(t) -> None:
        t.run_ok('done', 'Overdue task', '--date', '2026-08-03')
        (completed,) = Journal(t.source).events
        task_id = completed['stream_id'].removeprefix('task/')
        t.run_ok('update', task_id)

        out = t.run_ok('history', task_id)

        # The reopen is listed, though it carries no attribute.
        t.assertEqual(
            out,
            f'Overdue task [ID:{task_id}]\n'
            '  2026-08-04  TaskUpdated\n'
            '  2026-08-03  TaskCompleted\n',
        )

    def test_several_tasks(t) -> None:
        """Each task a title part matches is named by id, newest first."""
        t.run_ok('add', 'chores', 'Rx refill')
        t.run_ok('done', 'Rx refill', '--date', '2026-08-01')
        t.run_ok('add', 'chores', 'Rx refill')
        t.run_ok('done', 'Rx refill', '--date', '2026-08-03')
        events = Journal(t.source).events
        first, second = (
            event['stream_id'].removeprefix('task/')
            for event in events
                if event['type'] == 'TaskCompleted'
        )  # fmt: skip

        out, err, code = run_cli(['history', 'rx refill'], t.env)

        t.assertEqual(code, 1)
        t.assertEqual(out, '')
        t.assertEqual(
            err,
            "'rx refill' matches 2 tasks in the journal:\n"
            f'{second}  2026-08-03  Rx refill\n'
            f'{first}  2026-08-01  Rx refill\n',
        )

    def test_history_rejected(t) -> None:
        """A selector that names no stream reports on stderr."""
        out, err, code = run_cli(['history', 'Legacy priority'], t.env)

        t.assertEqual(code, 1)
        t.assertEqual(out, '')
        t.assertEqual(
            err, "no task in the journal matches 'Legacy priority'\n"
        )
