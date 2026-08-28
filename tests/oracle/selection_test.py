"""Characterization tests for the task-lookup cluster in `mutate`.

Temporary scaffolding for the conversion to `battodo.selection`. The
suite pins what the old functions do, then asserts the new property
object answers the same. It is deleted with the old functions.
"""

from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

from battodo.mutate import (
    SelectionError,
    _descend,
    _lists,
    _selects,
    find_task,
    parse,
)
from battodo.selection import TaskSelection
from battodo.selection import _descend as new_descend
from battodo.selection import _selects as new_selects

SRC = 'battodo.mutate'
NEW = 'battodo.selection'

# One list, holding every case the lookup distinguishes: an id, a child
# no id is stamped on, a checked task, three titles sharing a letter,
# and a title that quotes another task's id.
WORK = """# Work

## Open

- [ ] Deck rebuild [P:4] [ID:9o71lx]
  - [ ] Chip the brush [LOE:2]
  - [x] Sand it [LOE:1]
- [ ] Bare [P:2]
- [ ] Chase invoice 9o71lx [P:1]

## Done
"""


class TaskLookupTests(TestCase):
    """Characterization tests for the task lookup, old and new."""

    discover_lists: MagicMock

    def setUp(t) -> None:
        t.path = MagicMock(spec=Path)
        t.path.name = 'work.md'
        t.path.read_text.return_value = WORK
        t.dir = MagicMock(spec=Path)
        t.doc = parse(WORK)
        t.deck = t.doc.tasks[0]

        t.discover_lists = t.discovery(SRC)
        t.discovery(NEW)

    def discovery(t, module: str) -> MagicMock:
        """`discover_lists` in `module`, answering with the fixture."""
        patcher = patch(f'{module}.discover_lists', autospec=True)
        mock = patcher.start()
        t.addCleanup(patcher.stop)
        mock.return_value = [t.path]
        return mock

    def messages(t, selector: str) -> tuple[str, str]:
        """What each implementation says when nothing resolves."""
        with t.assertRaises(SelectionError) as old:
            find_task(t.dir, selector)
        with t.assertRaises(SelectionError) as new:
            _ = TaskSelection(t.dir, selector).record
        return str(old.exception), str(new.exception)

    def test_lists(t) -> None:
        pairs = list(_lists(t.dir))

        with t.subTest('every discovered list is read'):
            t.discover_lists.assert_called_once_with(t.dir)
            t.assertEqual([path for path, _ in pairs], [t.path])

        with t.subTest('and parsed, beside the path it came from'):
            t.assertEqual(
                [task.title for _, doc in pairs for task in doc.tasks],
                ['Deck rebuild', 'Bare', 'Chase invoice 9o71lx'],
            )

        with t.subTest('TaskSelection.lists answers the same'):
            t.assertEqual(TaskSelection(t.dir, 'b').lists, pairs)

    def test_descend(t) -> None:
        ancestries = list(_descend(t.doc.tasks, []))

        with t.subTest('every task at any depth, ancestry first'):
            t.assertEqual(
                [[task.title for task in ancestry] for ancestry in ancestries],
                [
                    ['Deck rebuild'],
                    ['Deck rebuild', 'Chip the brush'],
                    ['Deck rebuild', 'Sand it'],
                    ['Bare'],
                    ['Chase invoice 9o71lx'],
                ],
            )

        with t.subTest('selection._descend walks the same'):
            t.assertEqual(list(new_descend(t.doc.tasks, [])), ancestries)

    def test_selects(t) -> None:
        cases = {
            'the id the task carries': ('9o71lx', True),
            'part of its title, whatever the case': ('DECK re', True),
            'a title it does not carry': ('Bare', False),
            'an id it does not carry': ('zz01ab', False),
        }
        for name, (selector, expected) in cases.items():
            with t.subTest(f'{name}, both implementations'):
                t.assertIs(_selects(t.deck, selector), expected)
                t.assertIs(new_selects(t.deck, selector), expected)

    def test_find_task(t) -> None:
        with t.subTest('an id wins over a title that quotes it'):
            record = find_task(t.dir, '9o71lx')
            t.assertEqual(record.task.title, 'Deck rebuild')
            t.assertEqual(record.path, t.path)
            t.assertEqual(TaskSelection(t.dir, '9o71lx').record, record)

        with t.subTest('a title reaches a child no id is stamped on'):
            record = find_task(t.dir, 'chip the brush')
            t.assertEqual(
                [task.title for task in record.ancestry],
                ['Deck rebuild', 'Chip the brush'],
            )
            t.assertEqual(
                TaskSelection(t.dir, 'chip the brush').record, record
            )

        with t.subTest('a checked task is not a candidate'):
            old, new = t.messages('Sand it')
            t.assertEqual(old, "no open task matches 'Sand it'")
            t.assertEqual(new, old)

        with t.subTest('an ambiguous selector names what it matched'):
            old, new = t.messages('b')
            t.assertEqual(
                old,
                "'b' matches 3 open tasks: 'Deck rebuild', "
                "'Chip the brush', 'Bare'",
            )
            t.assertEqual(new, old)
