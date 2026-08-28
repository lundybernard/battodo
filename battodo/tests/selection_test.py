from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

from ..selection import (
    SelectionError,
    TaskNode,
    TaskRecord,
    TaskSelection,
    TodoFile,
)

SRC = 'battodo.selection'


class TaskSelectionTests(TestCase):
    """Unit tests for battodo.selection.TaskSelection."""

    discover_lists: MagicMock
    parse: MagicMock

    def setUp(t) -> None:
        for target in ('discover_lists', 'parse'):
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)

        t.path = MagicMock(spec=Path)
        t.path.name = 'work.md'
        t.dir = MagicMock(spec=Path)

        # One list holding every case the lookup distinguishes: an id, a
        # child no id is stamped on, a checked task, three titles
        # sharing a letter, and a title that quotes another task's id.
        t.brush = TaskNode(2, 2, False, 'Chip the brush', {'LOE': '2'})
        t.sand = TaskNode(3, 2, True, 'Sand it', {'LOE': '1'})
        t.deck = TaskNode(
            1, 0, False, 'Deck rebuild', {'ID': '9o71lx'},
            children=[t.brush, t.sand],
        )  # fmt: skip
        t.bare = TaskNode(4, 0, False, 'Bare', {'P': '2'})
        t.quote = TaskNode(5, 0, False, 'Chase invoice 9o71lx', {'P': '1'})
        t.doc = TodoFile([], [t.deck, t.bare, t.quote])

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
        records = t.searching('b').records

        with t.subTest('every open task the selector reaches, any depth'):
            t.assertEqual(
                [record.task for record in records],
                [t.deck, t.brush, t.bare],
            )

        with t.subTest('each one beside its list and the ancestry above it'):
            t.assertEqual([record.path for record in records], [t.path] * 3)
            t.assertEqual([record.doc for record in records], [t.doc] * 3)
            t.assertEqual(records[1].ancestry, [t.deck, t.brush])

        with t.subTest('a checked task is not open'):
            t.assertEqual(t.searching('Sand it').records, [])

        with t.subTest('a title matches whatever its case'):
            t.assertEqual(
                [record.task for record in t.searching('DECK re').records],
                [t.deck],
            )

        with t.subTest('an id narrows out the titles that quote it'):
            t.assertEqual(
                [record.task for record in t.searching('9o71lx').records],
                [t.deck],
            )

    def test_record(t) -> None:
        with t.subTest('the one open task the selector names'):
            only = TaskRecord(t.path, t.doc, [t.deck])
            t.ts.records = [only]
            t.assertIs(t.ts.record, only)

        with t.subTest('nothing open matches'):
            selection = TaskSelection(t.dir, 'Sand it')
            selection.records = []
            t.assertEqual(t.error(selection), "no open task matches 'Sand it'")

        with t.subTest('more than one does'):
            selection = TaskSelection(t.dir, 'b')
            selection.records = [
                TaskRecord(t.path, t.doc, [t.deck]),
                TaskRecord(t.path, t.doc, [t.deck, t.brush]),
            ]
            t.assertEqual(
                t.error(selection),
                "'b' matches 2 open tasks: 'Deck rebuild', 'Chip the brush'",
            )
