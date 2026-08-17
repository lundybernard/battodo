"""Contract tests for the mutations that edit one line, against real
files.

Inputs are real directories holding real todo lists, and the journal is
read back from disk. This layer asserts state; interaction checks stay
in the isolation tests beside the code.
"""

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from battodo.journal import Journal
from battodo.mutate import SelectionError, add_subtask, update_task

TODAY = date(2026, 8, 8)


def task_id(line: str) -> str:
    """The `[ID:]` value a mutation stamped on `line`."""
    return line.split('[ID:')[1].removesuffix(']')


WORK = """# Work

## Open

- [ ] Deck rebuild [P:4] [LOE:8] [ADDED:2026-07-06] [ID:9o71lx]
      A note that stays put.
  - [ ] Chip the brush [LOE:2]
  - [ ] Sweep up
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

    def test_update_task_reaches_a_subtask(t) -> None:
        _, entry = update_task(
            t.source, 'Chip the brush', {'DUE': '2026-09-01'}, TODAY
        )
        child = task_id(entry)
        (event,) = Journal(t.source).read()

        with t.subTest('the child keeps its indent and gains an id'):
            t.assertEqual(
                entry,
                '  - [ ] Chip the brush [LOE:2] '
                f'[DUE:2026-09-01] [ID:{child}]',
            )
            t.assertIn(entry, t.path.read_text(encoding='utf-8'))

        with t.subTest('the event lands on the child stream'):
            t.assertEqual(event['stream_id'], f'task/{child}')

        with t.subTest('and records where the child sits'):
            t.assertEqual(
                event['payload']['ancestry'], 'Deck rebuild > Chip the brush'
            )

    def test_update_task_rejected(t) -> None:
        before = t.path.read_text(encoding='utf-8')
        cases = {
            'an update that names no change': ('9o71lx', {}),
            'a field the top-level task owns': ('Chip the brush', {'P': '5'}),
            'a checklist item, which carries no fields': (
                'Sweep up',
                {'DUE': '2026-09-01'},
            ),
            'a value btodo cannot read': ('9o71lx', {'DUE': 'someday'}),
        }

        for name, (selector, fields) in cases.items():
            with t.subTest(name), t.assertRaises(ValueError):
                update_task(t.source, selector, fields, TODAY)

        with t.subTest('a rejected update writes nothing at all'):
            t.assertEqual(t.path.read_text(encoding='utf-8'), before)
            t.assertEqual(Journal(t.source).read(), [])


class AddSubtaskTests(TestCase):
    maxDiff = None

    def setUp(t) -> None:
        tmp = TemporaryDirectory()
        t.addCleanup(tmp.cleanup)
        t.source = Path(tmp.name)
        t.path = t.source / 'work.md'
        t.path.write_text(WORK, encoding='utf-8')

    def test_add_subtask(t) -> None:
        path, entry = add_subtask(
            t.source, 'work', '9o71lx', 'Buy lumber', {'LOE': '2'}
        )

        with t.subTest('the list written to, and the line as written'):
            t.assertEqual(path, t.path)
            t.assertRegex(
                entry, r'^  - \[ \] Buy lumber \[LOE:2\] \[ID:\w{6}\]$'
            )

        with t.subTest('the child lands last in its parent block'):
            t.assertEqual(
                t.path.read_text(encoding='utf-8'),
                WORK.replace(
                    '  - [ ] Sweep up\n', f'  - [ ] Sweep up\n{entry}\n'
                ),
            )

    def test_add_subtask_journal(t) -> None:
        _, entry = add_subtask(
            t.source, 'work', '9o71lx', 'Buy lumber', {'LOE': '2'}
        )
        child = task_id(entry)
        (event,) = Journal(t.source).read()

        with t.subTest('one TaskAdded on the new subtask stream'):
            t.assertEqual(event['type'], 'TaskAdded')
            t.assertEqual(event['stream_id'], f'task/{child}')
            t.assertEqual(
                event['metadata'],
                {'actor': 'agent', 'source_file': 'work.md'},
            )

        with t.subTest('the parent rides in the payload, not in the file'):
            t.assertEqual(
                event['payload'],
                {
                    'delta': {'LOE': [None, '2'], 'ID': [None, child]},
                    'snapshot': {
                        'title': 'Buy lumber',
                        'done': False,
                        'fields': {'LOE': '2', 'ID': child},
                    },
                    'parent': '9o71lx',
                },
            )

    def test_add_subtask_nests_deeper(t) -> None:
        """A subtask is itself a parent, as SCHEMA.md allows."""
        _, entry = add_subtask(
            t.source, 'work', 'Chip the brush', 'Rake the chips', {}
        )
        stamp = Journal(t.source).read()[0]
        parent = stamp['stream_id'].removeprefix('task/')

        with t.subTest('the child indents one level under its parent'):
            t.assertRegex(entry, r'^    - \[ \] Rake the chips \[ID:\w{6}\]$')

        with t.subTest('and lands directly beneath it'):
            t.assertIn(
                f'  - [ ] Chip the brush [LOE:2] [ID:{parent}]\n{entry}\n',
                t.path.read_text(encoding='utf-8'),
            )

    def test_add_subtask_stamps_the_parent(t) -> None:
        _, entry = add_subtask(
            t.source, 'work', 'Unidentified', 'Get quotes', {}
        )
        stamp, added = Journal(t.source).read()
        parent = stamp['stream_id'].removeprefix('task/')

        with t.subTest('a parent with no id of its own is given one'):
            t.assertIn(
                f'- [ ] Unidentified task [P:2] [ID:{parent}]',
                t.path.read_text(encoding='utf-8'),
            )

        with t.subTest('the stamp is an event on the parent stream'):
            t.assertEqual(stamp['type'], 'TaskUpdated')
            t.assertEqual(stamp['payload']['delta'], {'ID': [None, parent]})

        with t.subTest('which the child then names as its parent'):
            t.assertEqual(added['stream_id'], f'task/{task_id(entry)}')
            t.assertEqual(added['payload']['parent'], parent)

    def test_add_subtask_rejected(t) -> None:
        before = t.path.read_text(encoding='utf-8')

        with (
            t.subTest('a parent no selector reaches'),
            t.assertRaises(SelectionError),
        ):
            add_subtask(t.source, 'work', 'nothing', 'X', {})

        with (
            t.subTest('a field only the top-level task carries'),
            t.assertRaisesRegex(ValueError, 'P belongs to the top-level task'),
        ):
            add_subtask(t.source, 'work', '9o71lx', 'X', {'P': '3'})

        with (
            t.subTest('a checklist item, which cannot hold an id'),
            t.assertRaisesRegex(ValueError, 'checklist item'),
        ):
            add_subtask(t.source, 'work', 'Sweep up', 'X', {})

        with t.subTest('a rejected add writes nothing at all'):
            t.assertEqual(t.path.read_text(encoding='utf-8'), before)
            t.assertEqual(Journal(t.source).read(), [])
