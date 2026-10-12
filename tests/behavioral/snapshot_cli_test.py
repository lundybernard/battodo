"""Round-trip test for the list that each journal event records.

The fixture lists are copied to a temporary directory first: the
narrative writes, and the committed fixtures are read-only inputs to
the `view` and `show` goldens.

The narrative adds a task to one list, then updates it, notes it and
completes it. The snapshot of every event it journals names that list.
A second task closes with a subtask under it, and the snapshot of its
completion records the subtask.
"""

from datetime import datetime
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from battodo.cli import TZ
from battodo.journal import Journal

from .cli_runner import run_cli

FIXTURES = Path(__file__).parent / 'data' / 'todo'
FROZEN = datetime(2026, 8, 5, 10, 30, tzinfo=TZ)
SOURCE_VAR = 'BATTODO_VIEW_SOURCE_DIR'


class SnapshotListTests(TestCase):
    """Round-trip tests for the list in each event snapshot."""

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

    def test_list(t) -> None:
        t.run_ok('add', 'chores', 'Sweep the deck')
        t.run_ok('update', 'Sweep the deck', '-p', '2')
        t.run_ok('note', 'Sweep the deck', 'Bring the broom')
        t.run_ok('done', 'Sweep the deck')

        events = Journal(t.source).events

        t.assertEqual(
            [
                (event['type'], event['payload']['snapshot'].get('list'))
                for event in events
            ],
            [
                ('TaskAdded', 'chores'),
                ('TaskUpdated', 'chores'),
                ('TaskAnnotated', 'chores'),
                ('TaskCompleted', 'chores'),
            ],
        )

    def test_children(t) -> None:
        t.run_ok('add', 'chores', 'Paint the fence')
        t.run_ok(
            'add',
            'chores',
            'Buy paint',
            '--parent',
            'Paint the fence',
            '--loe',
            '1',
        )
        t.run_ok('done', 'Paint the fence')
        *_, added, completed = Journal(t.source).events
        child_id = added['stream_id'].removeprefix('task/')

        ret = completed['payload']['snapshot'].get('children')

        t.assertEqual(
            ret,
            [
                {
                    'title': 'Buy paint',
                    'done': False,
                    'fields': {'LOE': '1', 'ID': child_id},
                },
            ],
        )
