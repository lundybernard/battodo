"""Contract tests for the task lookup, against real list files.

Inputs are a real directory holding real todo lists. This layer asserts
state; interaction checks stay in the isolation tests beside the code.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from battodo.selection import SelectionError, TaskSelection

WORK = """# Work

## Open

- [ ] Deck rebuild [P:4] [ID:9o71lx]
  - [ ] Chip the brush [LOE:2]
    - [ ] Sand the rails
  - [x] Pack tools [LOE:1]
- [ ] Bare [P:2]

## Done
"""

CHORES = """# Chores

## Open

- [ ] Chase invoice 9o71lx [P:1]
- [ ] Water the plants [P:3] [ID:wtr001]

## Done
"""

COMPLETED = """# Completed Tasks

2026-07-27 | work | DONE | Deck rebuild > Pack tools [LOE:1]
"""


class TaskSelectionTests(TestCase):
    """Contract tests for battodo.selection.TaskSelection."""

    def setUp(t) -> None:
        t.tmp = TemporaryDirectory()
        t.addCleanup(t.tmp.cleanup)
        t.dir = Path(t.tmp.name)
        (t.dir / 'work.md').write_text(WORK)
        (t.dir / 'chores.md').write_text(CHORES)
        (t.dir / 'completed.md').write_text(COMPLETED)

    def error(t, selector: str) -> str:
        """The message a failed resolution carries."""
        with t.assertRaises(SelectionError) as caught:
            _ = TaskSelection(t.dir, selector).record
        return str(caught.exception)

    def test_lists(t) -> None:
        lists = TaskSelection(t.dir, 'Bare').lists

        with t.subTest('every todo list, in name order, completed.md aside'):
            t.assertEqual(
                [path.name for path, _ in lists],
                ['chores.md', 'work.md'],
            )

        with t.subTest('each one parsed'):
            t.assertEqual(
                [task.title for _, doc in lists for task in doc.tasks],
                [
                    'Chase invoice 9o71lx',
                    'Water the plants',
                    'Deck rebuild',
                    'Bare',
                ],
            )

    def test_records(t) -> None:
        with t.subTest('every open task the selector reaches, at any depth'):
            t.assertEqual(
                [
                    record.task.title
                    for record in TaskSelection(t.dir, 'the').records
                ],
                ['Water the plants', 'Chip the brush', 'Sand the rails'],
            )

        with t.subTest('a checked task is not open'):
            t.assertEqual(TaskSelection(t.dir, 'Pack tools').records, [])

        with t.subTest('an id narrows out the titles that quote it'):
            t.assertEqual(
                [
                    record.task.title
                    for record in TaskSelection(t.dir, '9o71lx').records
                ],
                ['Deck rebuild'],
            )

    def test_record(t) -> None:
        with t.subTest('by id, with the list that holds it'):
            record = TaskSelection(t.dir, '9o71lx').record
            t.assertEqual(record.task.title, 'Deck rebuild')
            t.assertEqual(record.path.name, 'work.md')

        with t.subTest('by part of a title, case-insensitively'):
            t.assertEqual(
                TaskSelection(t.dir, 'DECK re').record.task.title,
                'Deck rebuild',
            )

        with t.subTest('a subtask, which has no id to be found by'):
            t.assertEqual(
                [
                    task.title
                    for task in TaskSelection(
                        t.dir,
                        'sand the',
                    ).record.ancestry
                ],
                ['Deck rebuild', 'Chip the brush', 'Sand the rails'],
            )

        with t.subTest('nothing open matches'):
            t.assertEqual(
                t.error('Pack tools'),
                "no open task matches 'Pack tools'",
            )

        with t.subTest('more than one does'):
            t.assertEqual(
                t.error('the'),
                "'the' matches 3 open tasks: 'Water the plants', "
                "'Chip the brush', 'Sand the rails'",
            )
