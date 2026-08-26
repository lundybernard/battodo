"""Contract test for the task a command works on, against real files.

The source is a real directory holding a real list, and both the list
and `completed.md` are read back from disk. This layer asserts state;
interaction checks stay in the isolation tests beside the code.
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
    maxDiff = None

    def setUp(t) -> None:
        tmp = TemporaryDirectory()
        t.addCleanup(tmp.cleanup)
        t.source = Path(tmp.name)
        t.path = t.source / 'work.md'
        t.path.write_text(WORK, encoding='utf-8')
        t.tk = Task(t.source, '9o71lx', TODAY)

    def test_match(t) -> None:
        with t.subTest('the selector reaches one task in one list'):
            t.assertEqual(t.tk.match.task.title, 'Deck rebuild')
            t.assertEqual(t.tk.match.path, t.path)

    def test_complete(t) -> None:
        t.tk.complete()

        with t.subTest('the entry is logged under the day it was given'):
            t.assertEqual(
                t.tk.completed,
                ['2026-08-08 | work | DONE | Deck rebuild [P:4] [LOE:8]'],
            )

        with t.subTest('the log on disk holds it'):
            log = (t.source / 'completed.md').read_text(encoding='utf-8')
            t.assertIn(t.tk.completed[0], log)

        with t.subTest('the block is gone from the list'):
            text = t.path.read_text(encoding='utf-8')
            t.assertNotIn('Deck rebuild', text)

        with t.subTest('and every other task stays where it was'):
            t.assertIn('- [ ] Unidentified task [P:2]', text)
