"""Contract test for the task a command works on, against real files.

The source is a real directory holding a real list. This layer asserts
state; interaction checks stay in the isolation tests beside the code.
"""

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from battodo.task import Task

TODAY = date(2026, 8, 8)
WORK = """# Work

## Open

- [ ] Deck rebuild [P:4] [LOE:8] [ADDED:2026-07-06] [ID:9o71lx]
- [ ] Unidentified task [P:2]

## Done
"""


class TaskTests(TestCase):
    """Contract tests for battodo.task.Task."""

    maxDiff = None

    def setUp(t) -> None:
        tmp = TemporaryDirectory()
        t.addCleanup(tmp.cleanup)
        t.source = Path(tmp.name)
        t.path = t.source / 'work.md'
        t.path.write_text(WORK, encoding='utf-8')
        t.tk = Task(t.source, '9o71lx', TODAY)

    def test_record(t) -> None:
        with t.subTest('the selector reaches one task in one list'):
            record = t.tk.record
            t.assertEqual(record.task.title, 'Deck rebuild')
            t.assertEqual(record.path, t.path)

    def test_path(t) -> None:
        ret = t.tk.path
        t.assertEqual(ret, t.path)

    def test_doc(t) -> None:
        ret = t.tk.doc
        t.assertEqual(ret.text, WORK)

    def test_ancestry(t) -> None:
        ret = t.tk.ancestry
        t.assertEqual([task.title for task in ret], ['Deck rebuild'])

    def test_node(t) -> None:
        ret = t.tk.node
        t.assertEqual(ret.title, 'Deck rebuild')

    def test_selection(t) -> None:
        ret = t.tk.selection
        t.assertEqual((ret.directory, ret.selector), (t.source, '9o71lx'))
