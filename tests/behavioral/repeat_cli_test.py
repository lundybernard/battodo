"""Round-trip tests for the repeat of a task and of a subtask.

The narratives are the ones ADR 0028 and ADR 0029 ask of an agent. Set,
change and clear the repeat of a task through `update`, and read each
state back through `show`. Then give a chore a repeating step, and close
the chore once the repeat of the step is cleared.
"""

from datetime import datetime
from json import loads
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import TestCase
from unittest.mock import patch

from tests.environment import TZ

from .cli_runner import run_cli

FROZEN = datetime(2026, 8, 5, 10, 30, tzinfo=TZ)
SOURCE_VAR = 'BATTODO_VIEW_SOURCE_DIR'
# A list that holds one chore.
CHORES = '# Chores\n\n## Open\n\n- [ ] Clear the yard [P:3] [ID:cy01ab]\n'


class RepeatCommandTests(TestCase):
    """Round-trip tests for the repeat of a task."""

    maxDiff = None

    def setUp(t) -> None:
        tmp = TemporaryDirectory()
        t.addCleanup(tmp.cleanup)
        t.source = Path(tmp.name)
        (t.source / 'chores.md').write_text(CHORES, encoding='utf-8')
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

    def test_update_repeat(t) -> None:
        t.run_ok('update', 'cy01ab', '--repeat', '7d')
        set_to = t.show('cy01ab')['repeat']
        t.run_ok('update', 'cy01ab', '--repeat', '14d')
        changed_to = t.show('cy01ab')['repeat']
        t.run_ok('update', 'cy01ab', '--repeat', 'None')
        cleared = t.show('cy01ab')['repeat']
        _, refusal, code = run_cli(
            ['update', 'cy01ab', '--repeat', 'None'], t.env
        )

        with t.subTest('a repeat is set on a task with none'):
            t.assertEqual(set_to, '7d')

        with t.subTest('and changed'):
            t.assertEqual(changed_to, '14d')

        with t.subTest('and cleared with None'):
            t.assertIsNone(cleared)

        with t.subTest('a clear of a task with no repeat changes nothing'):
            t.assertEqual(code, 1)
            t.assertIn('nothing to update', refusal)

    def test_repeating_subtask(t) -> None:
        t.run_ok(
            'add',
            'chores',
            'Mow the lawn',
            '--parent',
            'cy01ab',
            '--due',
            '2026-08-01',
            '--repeat',
            '7d',
        )
        (step,) = t.show('cy01ab')['subtasks']
        _, held, held_code = run_cli(['done', 'cy01ab'], t.env)
        logged = t.run_ok('done', step['id'])
        (rescheduled,) = t.show('cy01ab')['subtasks']
        t.run_ok('update', step['id'], '--repeat', 'None')
        closed = t.run_ok('done', 'cy01ab')
        listed = (t.source / 'chores.md').read_text(encoding='utf-8')

        with t.subTest('a repeating step holds its chore open'):
            t.assertEqual(held_code, 1)
            t.assertIn(f'update {step["id"]} --repeat None', held)

        with t.subTest('its done logs it, and moves its due date on'):
            t.assertEqual(
                logged,
                '2026-08-05 | chores | DONE | Clear the yard > Mow the lawn '
                '[DUE:2026-08-01] [REPEAT:7d]\n',
            )
            t.assertEqual(rescheduled['due'], '2026-08-12')

        with t.subTest('with its repeat cleared, the chore closes'):
            t.assertEqual(
                closed, '2026-08-05 | chores | DONE | Clear the yard [P:3]\n'
            )
            t.assertEqual(listed, '# Chores\n\n## Open\n')
