from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

from ..selector import (
    SelectionError,
    TaskNode,
    TaskRecord,
    TaskSelection,
    TodoFile,
)

SRC = 'battodo.selector'


class TaskSelectionTests(TestCase):
    """Unit tests for battodo.selector.TaskSelection."""

    discover_lists: MagicMock
    parse: MagicMock

    def setUp(t) -> None:
        for target in ('discover_lists', 'parse'):
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)

        t.path = MagicMock(spec=Path)
        t.path.name = 'a-list.md'
        t.dir = Path('/source-dir')

        # One list holding every case the lookup distinguishes: an id, a
        # child no id is stamped on, a checked task, three titles
        # sharing a letter, and a title that quotes another task's id.
        t.child = TaskNode(
            raw_index=1,
            indent=2,
            done=False,
            title='Subtask below it',
            fields={},
        )
        t.checked = TaskNode(
            raw_index=2,
            indent=2,
            done=True,
            title='Checked subtask',
            fields={},
        )
        t.parent = TaskNode(
            raw_index=0,
            indent=0,
            done=False,
            title='Branch task',
            fields={'ID': '9o71lx'},
            children=[t.child, t.checked],
        )
        t.sibling = TaskNode(
            raw_index=3,
            indent=0,
            done=False,
            title='Bare top-level task',
            fields={},
        )
        t.quoting = TaskNode(
            raw_index=4,
            indent=0,
            done=False,
            title='Title quoting 9o71lx',
            fields={},
        )
        t.doc = TodoFile([], [t.parent, t.sibling, t.quoting])

        t.ts = TaskSelection(t.dir, 'b')

    def searching(t, selector: str) -> TaskSelection:
        """A selection over the fixture list, the read already done."""
        selection = TaskSelection(t.dir, selector)
        selection.lists = [(t.path, t.doc)]
        return selection

    def error(t, selection: TaskSelection) -> str:
        """The message a failed resolution carries."""
        with t.assertRaises(SelectionError) as caught:
            _ = selection.record
        return str(caught.exception)

    def test_lists(t) -> None:
        t.discover_lists.return_value = [t.path]

        lists = t.ts.lists

        with t.subTest('every discovered list is read'):
            t.discover_lists.assert_called_once_with(t.dir)
            t.path.read_text.assert_called_once_with()

        with t.subTest('and parsed, beside the path it came from'):
            t.parse.assert_called_once_with(t.path.read_text.return_value)
            t.assertEqual(lists, [(t.path, t.parse.return_value)])

    def test_records(t) -> None:
        with t.subTest('every open task the selector reaches, any depth'):
            t.assertEqual(
                t.searching('b').records,
                [
                    TaskRecord(t.path, t.doc, [t.parent]),
                    TaskRecord(t.path, t.doc, [t.parent, t.child]),
                    TaskRecord(t.path, t.doc, [t.sibling]),
                ],
            )

        with t.subTest('a checked task is not open'):
            t.assertEqual(t.searching('Checked subtask').records, [])

        with t.subTest('a title matches whatever its case'):
            t.assertEqual(
                [record.task for record in t.searching('BRANCH ta').records],
                [t.parent],
            )

        with t.subTest('an id narrows out the titles that quote it'):
            t.assertEqual(
                [record.task for record in t.searching('9o71lx').records],
                [t.parent],
            )

    def test_record(t) -> None:
        with t.subTest('the one open task the selector names'):
            only = TaskRecord(t.path, t.doc, [t.parent])
            t.ts.records = [only]
            t.assertIs(t.ts.record, only)

        with t.subTest('nothing open matches'):
            selection = TaskSelection(t.dir, 'Checked subtask')
            selection.records = []
            t.assertEqual(
                t.error(selection),
                "no open task matches 'Checked subtask'",
            )

        with t.subTest('more than one does'):
            selection = TaskSelection(t.dir, 'b')
            selection.records = [
                TaskRecord(t.path, t.doc, [t.parent]),
                TaskRecord(t.path, t.doc, [t.parent, t.child]),
            ]
            t.assertEqual(
                t.error(selection),
                "'b' matches 2 open tasks: 'Branch task', 'Subtask below it'",
            )
