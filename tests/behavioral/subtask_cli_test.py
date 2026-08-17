"""Round-trip test for subtasks.

The fixture lists are copied to a temporary directory first: these
commands write, and the committed fixtures are read-only inputs to the
`view` and `show` goldens.

The narrative is one subtask's life. Add it under a parent that carries
no `[ID:]`, read it back by the id the add stamped, and complete it.
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
PARENT = 'Legacy priority'


class SubtaskCommandTests(TestCase):
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

    def test_add_subtask(t) -> None:
        before = t.show(PARENT)
        with t.subTest('the parent starts with no id of its own'):
            t.assertIsNone(before['id'])

        echoed = t.run_ok(
            'add', 'work', 'Sand the rails', '--parent', PARENT, '--loe', '2'
        )

        with t.subTest('the child line is indented under its parent'):
            t.assertIn('  - [ ] Sand the rails [LOE:2] [ID:', echoed)
            t.assertIn('work.md', echoed)

        after = t.show(PARENT)

        with t.subTest('the parent is stamped, so an event can name it'):
            t.assertIsNotNone(after['id'])

        with t.subTest('the child lands last under its parent'):
            t.assertEqual(
                [child['title'] for child in after['subtasks']],
                [
                    *(child['title'] for child in before['subtasks']),
                    'Sand the rails',
                ],
            )

        child = after['subtasks'][-1]
        with t.subTest('and reads back by the id the add stamped'):
            t.assertEqual(t.show(child['id'])['title'], 'Sand the rails')

    def test_add_subtask_rejected(t) -> None:
        """A rejected add reports on stderr and writes nothing."""
        cases = {
            'no task carries that id': ('zz01ab', 'Sand the rails'),
            'a checklist item cannot be a parent': (
                'Open checklist item',
                'Sand the rails',
            ),
        }
        original = (t.source / 'work.md').read_text(encoding='utf-8')

        for name, (parent, title) in cases.items():
            with t.subTest(name):
                out, err, code = run_cli(
                    ['add', 'work', title, '--parent', parent], t.env
                )

                t.assertEqual(code, 1)
                t.assertEqual(out, '')
                t.assertNotEqual(err, '')
                t.assertEqual(
                    (t.source / 'work.md').read_text(encoding='utf-8'),
                    original,
                )

    def add_subtask(t) -> str:
        """Add one subtask under PARENT and return its id."""
        t.run_ok(
            'add', 'work', 'Sand the rails', '--parent', PARENT, '--loe', '2'
        )
        return t.show(PARENT)['subtasks'][-1]['id']

    def test_update_and_done_reach_a_subtask(t) -> None:
        child = t.add_subtask()

        echoed = t.run_ok(
            'update', child, '--due', '2026-09-01', '--title', 'Sand and seal'
        )
        with t.subTest('the child line is rewritten where it stands'):
            t.assertIn('  - [ ] Sand and seal', echoed)

        after = t.show(child)
        with t.subTest('the change reads back by the same id'):
            t.assertEqual(after['title'], 'Sand and seal')
            t.assertEqual(after['due'], '2026-09-01')

        with t.subTest('what the update did not name is left alone'):
            t.assertEqual(after['loe'], 2)

        logged = t.run_ok('done', child)
        with t.subTest('done logs the child under its ancestry'):
            t.assertIn('Legacy priority task > Sand and seal', logged)

    def test_scratch_reaches_a_subtask(t) -> None:
        child = t.add_subtask()

        logged = t.run_ok('scratch', child)

        with t.subTest('the log entry names the child under its parent'):
            t.assertIn('Legacy priority task > Sand the rails', logged)

        with t.subTest('and the line is gone'):
            t.assertNotIn(
                'Sand the rails',
                [child['title'] for child in t.show(PARENT)['subtasks']],
            )
