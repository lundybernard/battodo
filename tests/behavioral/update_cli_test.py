"""Round-trip test for the `update` command.

The fixture lists are copied to a temporary directory first: `update`
writes, and the committed fixtures are read-only inputs to the `view`
and `show` goldens.

The narrative is the round trip R3 asks of an agent. Read an item that
carries no `[ID:]`, change its fields and its title, then read it back
-- by title, and by the id the update injected.
"""

from datetime import datetime
from json import loads
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
from typing import Any
from unittest import TestCase
from unittest.mock import patch

from battodo.cli import TZ
from battodo.journal import Journal

from .cli_runner import run_cli

FIXTURES = Path(__file__).parent / 'data' / 'todo'
FROZEN = datetime(2026, 8, 5, 10, 30, tzinfo=TZ)
SOURCE_VAR = 'BATTODO_VIEW_SOURCE_DIR'
SELECTOR = 'Legacy priority'


class UpdateCommandTests(TestCase):
    """Round-trip tests for the `update` command."""

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

    def show(t, selector: str) -> dict[str, Any]:
        return loads(t.run_ok('show', selector, '--format', 'json'))

    def test_update(t) -> None:
        before = t.show(SELECTOR)

        with t.subTest('the item starts with no id of its own'):
            t.assertIsNone(before['id'])

        echoed = t.run_ok(
            'update',
            SELECTOR,
            '-p',
            '3',
            '--due',
            '2026-09-01',
            '--tags',
            'yard,summer',
            '--title',
            'Renamed task',
        )

        with t.subTest('the written line and its file are echoed'):
            t.assertIn('- [ ] Renamed task', echoed)
            t.assertIn('work.md', echoed)

        after = t.show('Renamed task')

        with t.subTest('every supplied field is changed'):
            t.assertEqual(after['title'], 'Renamed task')
            t.assertEqual(after['priority'], 3.0)
            t.assertEqual(after['due'], '2026-09-01')
            t.assertEqual(after['tags'], ['yard', 'summer'])

        with t.subTest('what the update did not name is left alone'):
            t.assertEqual(after['loe'], before['loe'])
            t.assertEqual(after['subtasks'], before['subtasks'])

        with t.subTest('the update injects an id, so a read by id works'):
            by_id = t.show(after['id'])
            t.assertIsNotNone(after['id'])
            t.assertEqual(by_id, after)

    def test_update_clear(t) -> None:
        t.run_ok(
            'update', SELECTOR, '--due', '2026-09-01', '--tags', 'yard,summer'
        )
        _, due_err, _ = run_cli(['update', SELECTOR, '--due', 'None'], t.env)
        _, tags_err, _ = run_cli(['update', SELECTOR, '--tags', 'None'], t.env)
        after = t.show(SELECTOR)
        work = (t.source / 'work.md').read_text(encoding='utf-8')
        cleared = Journal(t.source).events[1:]
        _, refusal, code = run_cli(
            ['update', SELECTOR, '--due', 'None', '--tags', 'None'], t.env
        )

        with t.subTest('None removes the due date'):
            t.assertEqual(due_err, '')
            t.assertIsNone(after['due'])

        with t.subTest('None removes the tags, field and all'):
            t.assertEqual(tags_err, '')
            t.assertEqual(after['tags'], [])
            t.assertNotIn('[TAGS:', work)

        with t.subTest('each event records its clear against the old value'):
            t.assertEqual(
                [event['payload']['delta'] for event in cleared],
                [
                    {'DUE': ['2026-09-01', None]},
                    {'TAGS': ['yard,summer', None]},
                ],
            )

        with t.subTest(
            'a clear of fields the task does not carry is no change'
        ):
            t.assertEqual(code, 1)
            t.assertIn('nothing to update', refusal)

    def test_update_with_attributes(t) -> None:
        t.run_ok(
            'update',
            SELECTOR,
            '-p',
            '3',
            '--attrs',
            'estimate=2h, reason=moved up, after review',
            '--note',
            'Asked by the team',
        )

        event = Journal(t.source).events[-1]
        t.assertEqual(
            event['payload']['attrs'],
            {
                'estimate': '2h',
                'reason': 'moved up, after review',
                'note': 'Asked by the team',
            },
        )

    def test_move(t) -> None:
        before = t.show(SELECTOR)

        echoed = t.run_ok('update', SELECTOR, '--list', 'chores', '-p', '3')

        after = t.show(SELECTOR)
        work = (t.source / 'work.md').read_text(encoding='utf-8')
        chores = (t.source / 'chores.md').read_text(encoding='utf-8')
        (moved,) = Journal(t.source).events

        with t.subTest('the line and the list it joins are echoed'):
            t.assertIn('- [ ] Legacy priority task [P:3]', echoed)
            t.assertIn('chores.md', echoed)

        with t.subTest('the task, its subtasks with it, is in the new list'):
            t.assertEqual(after['list'], 'chores')
            t.assertEqual(after['subtasks'], before['subtasks'])
            t.assertNotIn('Legacy priority task', work)
            t.assertNotIn('Open subtask', work)
            t.assertIn('  - [ ] Open subtask [LOE:1]', chores)

        with t.subTest('the event records the list it left and joined'):
            t.assertEqual(
                moved['payload']['delta']['list'], ['work', 'chores']
            )
            t.assertEqual(moved['payload']['snapshot']['list'], 'work')

    def test_update_rejected(t) -> None:
        """A rejected update reports on stderr and writes nothing."""
        cases = {
            'an empty update names no change': ('update', SELECTOR),
            'a list that is not there': (
                'update',
                SELECTOR,
                '--list',
                'wrk',
            ),
            'a subtask moves with its top-level task alone': (
                'update',
                'Open subtask',
                '--list',
                'chores',
            ),
            'a subtask is out of reach': (
                'update',
                'Open subtask',
                '-p',
                '3',
            ),
            'an unreadable value never reaches the file': (
                'update',
                SELECTOR,
                '--due',
                'someday',
            ),
            'a title with a line break never reaches the file': (
                'update',
                SELECTOR,
                '--title',
                'Renamed\ntask',
            ),
            'an attribute given twice never reaches the file': (
                'update',
                SELECTOR,
                '-p',
                '3',
                '--attrs',
                'note=Asked',
                '--note',
                'Asked by the team',
            ),
            'the list the task is in names no change': (
                'update',
                SELECTOR,
                '--list',
                'work',
            ),
        }
        original = (t.source / 'work.md').read_text(encoding='utf-8')

        for name, args in cases.items():
            with t.subTest(name):
                out, err, code = run_cli(list(args), t.env)

                t.assertEqual(code, 1)
                t.assertEqual(out, '')
                t.assertNotEqual(err, '')
                t.assertEqual(
                    (t.source / 'work.md').read_text(encoding='utf-8'),
                    original,
                )

        # A refusal journals no event.
        t.assertEqual(Journal(t.source).events, [])
