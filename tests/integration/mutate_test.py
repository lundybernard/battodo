"""Contract tests for the field update, against real files.

Inputs are real directories holding real todo lists, and the journal is
read back from disk. This layer asserts state; interaction checks stay
in the isolation tests beside the code.
"""

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from battodo.journal import Journal
from battodo.mutate import update_task

TODAY = date(2026, 8, 8)

WORK = """# Work

## Open

- [ ] Deck rebuild [P:4] [LOE:8] [ADDED:2026-07-06] [ID:9o71lx]
      A note that stays put.
  - [ ] Chip the brush [LOE:2]
- [ ] Unidentified task [P:2]

## Done
"""


class UpdateTaskTests(TestCase):
    maxDiff = None

    def setUp(t) -> None:
        tmp = TemporaryDirectory()
        t.addCleanup(tmp.cleanup)
        t.source = Path(tmp.name)
        t.path = t.source / 'work.md'
        t.path.write_text(WORK, encoding='utf-8')

    def test_update_task(t) -> None:
        path, entry = update_task(
            t.source,
            '9o71lx',
            {'P': '5', 'DUE': '2026-09-01'},
            TODAY,
            title='Deck rebuild, phase two',
        )
        text = t.path.read_text(encoding='utf-8')

        with t.subTest('the list written to, and the line as written'):
            t.assertEqual(path, t.path)
            t.assertEqual(
                entry,
                '- [ ] Deck rebuild, phase two [P:5] [LOE:8] '
                '[ADDED:2026-07-06] [ID:9o71lx] [DUE:2026-09-01]',
            )

        with t.subTest('the file holds the line that came back'):
            t.assertIn(entry, text)

        with t.subTest('every other line keeps its text and its place'):
            t.assertIn('      A note that stays put.', text)
            t.assertIn('  - [ ] Chip the brush [LOE:2]', text)
            t.assertTrue(text.endswith('## Done\n'))

    def test_update_task_journal(t) -> None:
        update_task(t.source, '9o71lx', {'P': '5'}, TODAY, title='Renamed')
        events = Journal(t.source).read()

        with t.subTest('one event, on the task stream'):
            t.assertEqual(len(events), 1)
            t.assertEqual(events[0]['type'], 'TaskUpdated')
            t.assertEqual(events[0]['stream_id'], 'task/9o71lx')

        with t.subTest('the delta is what was written, before and after'):
            t.assertEqual(
                events[0]['payload']['delta'],
                {'P': ['4', '5'], 'title': ['Deck rebuild', 'Renamed']},
            )

        with t.subTest('the snapshot is the state the delta changed from'):
            t.assertEqual(
                events[0]['payload']['snapshot'],
                {
                    'title': 'Deck rebuild',
                    'done': False,
                    'fields': {
                        'P': '4',
                        'LOE': '8',
                        'ADDED': '2026-07-06',
                        'ID': '9o71lx',
                    },
                },
            )

        with t.subTest('metadata names the source file'):
            t.assertEqual(events[0]['metadata']['source_file'], 'work.md')

    def test_update_task_injects_an_id(t) -> None:
        _, entry = update_task(t.source, 'Unidentified', {'P': '5'}, TODAY)
        event = Journal(t.source).read()[0]
        task_id = event['stream_id'].removeprefix('task/')

        with t.subTest('a task with no id of its own is given one'):
            t.assertEqual(
                entry, f'- [ ] Unidentified task [P:5] [ID:{task_id}]'
            )

        with t.subTest('the stamp is in the delta, so it can be undone'):
            t.assertEqual(event['payload']['delta']['ID'], [None, task_id])

    def test_update_task_rejected(t) -> None:
        before = t.path.read_text(encoding='utf-8')
        cases = {
            'an update that names no change': ('9o71lx', {}),
            'a task below the top level': ('Chip the brush', {'P': '5'}),
            'a value btodo cannot read': ('9o71lx', {'DUE': 'someday'}),
        }

        for name, (selector, fields) in cases.items():
            with t.subTest(name), t.assertRaises(ValueError):
                update_task(t.source, selector, fields, TODAY)

        with t.subTest('a rejected update writes nothing at all'):
            t.assertEqual(t.path.read_text(encoding='utf-8'), before)
            t.assertEqual(Journal(t.source).read(), [])
