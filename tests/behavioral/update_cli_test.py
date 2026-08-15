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

from .cli_runner import run_cli

FIXTURES = Path(__file__).parent / 'data' / 'todo'
FROZEN = datetime(2026, 8, 5, 10, 30, tzinfo=TZ)
SOURCE_VAR = 'BATTODO_VIEW_SOURCE_DIR'
SELECTOR = 'Legacy priority'


class UpdateCommandTests(TestCase):
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
            t.assertIsNotNone(after['id'])
            t.assertEqual(t.show(after['id']), after)

    def test_update_rejected(t) -> None:
        """A rejected update reports on stderr and writes nothing."""
        cases = {
            'an empty update names no change': ('update', SELECTOR),
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
