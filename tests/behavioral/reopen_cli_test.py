"""Round-trip test for the reopen of a closed task through `update`.

The fixture lists are copied to a temporary directory first: the
narratives write, and the committed fixtures are read-only inputs to
the `view` and `show` goldens.

Each narrative closes a task with `done`, then names it by its `[ID:]`
to `update`, and reads it back. A top-level task comes back
to its list with its subtasks closed (rule 2). A closed subtask opens,
and so does each closed task above it (rule 1). `--with-subtasks` opens
the task and each subtask below it (rule 3).
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


class ReopenCommandTests(TestCase):
    """Round-trip tests for `update` on a closed task."""

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

    def added(t, *args: str) -> str:
        """Add the task `args` describe, and return its id."""
        echoed = t.run_ok('add', *args)
        return echoed.split('[ID:')[1].split(']')[0]

    def chores(t) -> str:
        """The chores list as it stands."""
        return (t.source / 'chores.md').read_text(encoding='utf-8')

    def show(t, selector: str) -> dict[str, Any]:
        return loads(t.run_ok('show', selector, '--format', 'json'))

    def test_reopen(t) -> None:
        task_id = t.added(
            'chores',
            'Rx refill',
            '--due',
            '2026-08-10',
            '--description',
            'Call the pharmacy',
        )
        t.run_ok('done', 'Rx refill', '--date', '2026-08-04')

        echoed = t.run_ok('update', task_id, '--due', '2026-09-10')

        line = f'- [ ] Rx refill [DUE:2026-09-10] [ADDED:2026-08-05] [ID:{task_id}]'
        reopened = Journal(t.source).events[-1]

        with t.subTest('the line comes back to its list, open, its id kept'):
            t.assertEqual(echoed, f'{line}\n{t.source / "chores.md"}\n')
            t.assertIn(f'{line}\n      Call the pharmacy\n', t.chores())

        with t.subTest('show reads it, with its list and description'):
            shown = t.show(task_id)
            t.assertEqual(
                (shown['list'], shown['due'], shown['description']),
                ('chores', '2026-09-10', 'Call the pharmacy'),
            )

        with t.subTest('one TaskUpdated on its stream opens it'):
            t.assertEqual(
                (reopened['type'], reopened['stream_id']),
                ('TaskUpdated', f'task/{task_id}'),
            )
            t.assertEqual(
                reopened['payload']['delta'],
                {'DUE': ['2026-08-10', '2026-09-10'], 'done': [True, False]},
            )

        with t.subTest('the completed log keeps its record'):
            log = (t.source / 'completed.md').read_text(encoding='utf-8')
            t.assertIn('2026-08-04 | chores | DONE | Rx refill', log)

        with t.subTest('a later done adds a completion on the same id'):
            t.run_ok('done', task_id)

            completions = [
                event['stream_id']
                for event in Journal(t.source).events
                    if event['type'] == 'TaskCompleted'
            ]  # fmt: skip

            t.assertEqual(completions, [f'task/{task_id}'] * 2)

    def test_reopen_unchanged(t) -> None:
        task_id = t.added('chores', 'Rx refill')
        t.run_ok('done', 'Rx refill')

        echoed = t.run_ok('update', task_id)

        line = f'- [ ] Rx refill [ADDED:2026-08-05] [ID:{task_id}]'
        t.assertEqual(echoed, f'{line}\n{t.source / "chores.md"}\n')

    def test_reopen_scratched_to_another_list(t) -> None:
        task_id = t.added('chores', 'Fix the gate', '-p', '2')
        t.run_ok('done', 'Fix the gate', '--scratch')

        echoed = t.run_ok('update', task_id, '--list', 'work')

        work = (t.source / 'work.md').read_text(encoding='utf-8')
        reopened = Journal(t.source).events[-1]
        line = f'- [ ] Fix the gate [P:2] [ADDED:2026-08-05] [ID:{task_id}]'
        t.assertEqual(echoed, f'{line}\n{t.source / "work.md"}\n')
        t.assertIn(line, work)
        t.assertEqual(
            reopened['payload']['delta'],
            {'done': [True, False], 'list': ['chores', 'work']},
        )

    def test_reopen_parent(t) -> None:
        """Rule 2: a parent comes back with its subtasks closed."""
        parent_id = t.added('chores', 'Paint the fence')
        child_id = t.added(
            'chores', 'Buy paint', '--parent', 'Paint the fence'
        )
        t.run_ok('done', 'Paint the fence')

        t.run_ok('update', parent_id)

        t.assertIn(
            f'- [ ] Paint the fence [ADDED:2026-08-05] [ID:{parent_id}]\n'
            f'  - [x] Buy paint [ID:{child_id}]\n',
            t.chores(),
        )

    def test_reopen_subtask_in_its_list(t) -> None:
        """Rule 1: a closed subtask under an open parent opens in place."""
        parent_id = t.added('chores', 'Paint the fence')
        paint_id = t.added('chores', 'Buy paint', '--parent', parent_id)
        brush_id = t.added('chores', 'Buy brushes', '--parent', parent_id)
        t.run_ok('done', paint_id)

        t.run_ok('update', paint_id)

        events = Journal(t.source).events
        t.assertIn(
            f'- [ ] Paint the fence [ADDED:2026-08-05] [ID:{parent_id}]\n'
            f'  - [ ] Buy paint [ID:{paint_id}]\n'
            f'  - [ ] Buy brushes [ID:{brush_id}]\n',
            t.chores(),
        )
        t.assertEqual(
            (events[-1]['stream_id'], events[-1]['payload']['delta']),
            (f'task/{paint_id}', {'done': [True, False]}),
        )

    def test_reopen_subtask_of_a_closed_parent(t) -> None:
        """Rule 1: a closed parent opens with it; its sibling stays closed."""
        parent_id = t.added('chores', 'Paint the fence')
        paint_id = t.added('chores', 'Buy paint', '--parent', parent_id)
        brush_id = t.added('chores', 'Buy brushes', '--parent', parent_id)
        t.run_ok('done', paint_id)
        t.run_ok('done', brush_id)

        t.run_ok('update', paint_id)

        *_, parent, paint = Journal(t.source).events
        t.assertIn(
            f'- [ ] Paint the fence [ADDED:2026-08-05] [ID:{parent_id}]\n'
            f'  - [ ] Buy paint [ID:{paint_id}]\n'
            f'  - [x] Buy brushes [ID:{brush_id}]\n',
            t.chores(),
        )
        t.assertEqual(
            [parent['stream_id'], paint['stream_id']],
            [f'task/{parent_id}', f'task/{paint_id}'],
        )

    def test_reopen_with_subtasks(t) -> None:
        """Rule 3: the parent opens, and each subtask below it."""
        parent_id = t.added('chores', 'Paint the fence')
        paint_id = t.added('chores', 'Buy paint', '--parent', parent_id)
        brush_id = t.added('chores', 'Buy brushes', '--parent', parent_id)
        t.run_ok('done', paint_id)
        t.run_ok('done', parent_id)

        t.run_ok('update', parent_id, '--with-subtasks')

        events = Journal(t.source).events[-3:]
        t.assertIn(
            f'- [ ] Paint the fence [ADDED:2026-08-05] [ID:{parent_id}]\n'
            f'  - [ ] Buy paint [ID:{paint_id}]\n'
            f'  - [ ] Buy brushes [ID:{brush_id}]\n',
            t.chores(),
        )
        t.assertEqual(
            [event['stream_id'] for event in events],
            [f'task/{parent_id}', f'task/{paint_id}', f'task/{brush_id}'],
        )

    def test_reopen_rejected(t) -> None:
        """A rejected reopen reports on stderr and writes nothing."""
        t.run_ok('done', 'Open checklist item')
        owner_id = Journal(t.source).events[0]['stream_id'][len('task/') :]
        for _ in range(2):
            t.added('chores', 'Rx refill')
            t.run_ok('done', 'Rx refill')
        with t.subTest('a checklist item opens with its task'):
            before = t.chores()

            out, err, code = run_cli(['update', 'Open checklist item'], t.env)

            t.assertEqual(code, 1)
            t.assertEqual(out, '')
            t.assertEqual(
                err,
                "'Open checklist item' names a checklist item of "
                f'[ID:{owner_id}]: a checklist item opens with its '
                'task, not on its own\n',
            )
            t.assertEqual(t.chores(), before)

        with t.subTest('an open task takes no --with-subtasks'):
            out, err, code = run_cli(
                ['update', 'Overdue task', '--with-subtasks'], t.env
            )

            t.assertEqual(code, 1)
            t.assertEqual(
                err,
                "'Overdue task' names an open task: --with-subtasks "
                'reopens a closed task and its subtasks\n',
            )

        with t.subTest('several closed tasks: each named by id'):
            out, err, code = run_cli(['update', 'rx refill'], t.env)

            t.assertEqual(code, 1)
            t.assertTrue(
                err.startswith("'rx refill' matches 2 tasks in the journal:\n")
            )
