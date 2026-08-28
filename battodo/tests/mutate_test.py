from datetime import date
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, Mock, patch

from ..mutate import (
    ListError,
    TaskRecord,
    add_subtask,
    add_task,
    backfill_all,
    backfill_file,
    complete,
    parse,
    scratch,
    task_snapshot,
    update_task,
)
from ..repeat import RepeatError

SRC = 'battodo.mutate'

TODAY = date(2026, 8, 8)


class TaskSnapshotTests(TestCase):
    """Unit tests for battodo.mutate.task_snapshot."""

    def test_task_snapshot(t) -> None:
        task = parse('## Open\n\n- [ ] X [P:2] [TAGS:a]\n').tasks[0]
        t.assertEqual(
            task_snapshot(task),
            {
                'title': 'X',
                'done': False,
                'fields': {'P': '2', 'TAGS': 'a'},
            },
        )


UPDATE_DOC = """# Work

## Open

- [ ] Deck rebuild [P:4] [LOE:8] [ID:9o71lx]
      A note that stays put.

## Done
"""


class IsolatedTests(TestCase):
    """Isolation tests: the lookup, the file and the journal are mocked.

    Each suite names the targets it needs in `TARGETS` and builds its
    own document, so what a test stands on stays beside the test.
    """

    TARGETS: tuple[str, ...] = ('TaskSelection', 'Journal', 'new_task_id')

    TaskSelection: MagicMock
    Journal: MagicMock
    new_task_id: MagicMock

    def setUp(t) -> None:
        for target in t.TARGETS:
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        t.new_task_id.return_value = 'zz01ab'
        t.lookup = t.TaskSelection.return_value

        t.path = Mock(spec=Path)
        t.path.name = 'work.md'
        t.dir = Path('/todo')
        t.append = t.Journal.return_value.append


class UpdateTaskTests(IsolatedTests):
    """Unit tests for battodo.mutate.update_task."""

    def setUp(t) -> None:
        super().setUp()
        t.doc = parse(UPDATE_DOC)
        t.lookup.record = TaskRecord(t.path, t.doc, [t.doc.tasks[0]])

    def test_update_task(t) -> None:
        path, entry = update_task(
            t.dir, '9o71lx', {'P': '5'}, TODAY, title='Renamed'
        )

        with t.subTest('the selector is resolved against the directory'):
            t.TaskSelection.assert_called_with(t.dir, '9o71lx')

        with t.subTest('the line carries the new field and the new title'):
            t.assertEqual(entry, '- [ ] Renamed [P:5] [LOE:8] [ID:9o71lx]')
            t.assertEqual(path, t.path)

        with t.subTest('and is the only line the written file changes'):
            t.path.write_text.assert_called_with(
                UPDATE_DOC.replace(
                    '- [ ] Deck rebuild [P:4] [LOE:8] [ID:9o71lx]', entry
                )
            )

    def test_update_task_event(t) -> None:
        update_task(t.dir, '9o71lx', {'P': '5'}, TODAY, title='Renamed')

        with t.subTest('the journal of the source directory'):
            t.Journal.assert_called_with(t.dir)

        with t.subTest('one TaskUpdated, on the task stream'):
            t.append.assert_called_with(
                'TaskUpdated',
                'task/9o71lx',
                {
                    'delta': {
                        'P': ['4', '5'],
                        'title': ['Deck rebuild', 'Renamed'],
                    },
                    # Pre-state, as everywhere but an add: the delta
                    # says what changed, the snapshot what it was.
                    'snapshot': {
                        'title': 'Deck rebuild',
                        'done': False,
                        'fields': {'P': '4', 'LOE': '8', 'ID': '9o71lx'},
                    },
                },
                actor='agent',
                source_file='work.md',
            )

    def test_update_task_stamps_an_id(t) -> None:
        doc = parse('## Open\n\n- [ ] Bare [P:2]\n')
        t.lookup.record = TaskRecord(t.path, doc, [doc.tasks[0]])

        _, entry = update_task(t.dir, 'Bare', {'P': '5'}, TODAY)
        stream, payload = t.append.call_args[0][1:3]

        with t.subTest('a task with no id of its own is given one'):
            t.assertEqual(entry, '- [ ] Bare [P:5] [ID:zz01ab]')

        with t.subTest('which names the stream the event lands on'):
            t.assertEqual(stream, 'task/zz01ab')

        with t.subTest('the stamp rides in the delta, so it can be undone'):
            t.assertEqual(payload['delta']['ID'], [None, 'zz01ab'])

    def test_update_task_reaches_a_subtask(t) -> None:
        doc = parse(SUBTASK_DOC)
        parent = doc.tasks[0]
        t.lookup.record = TaskRecord(t.path, doc, [parent, parent.children[0]])

        _, entry = update_task(
            t.dir, 'Chip the brush', {'DUE': '2026-09-01'}, TODAY
        )
        payload = t.append.call_args[0][2]

        with t.subTest('the child keeps its indent and gains an id'):
            t.assertEqual(
                entry,
                '  - [ ] Chip the brush [LOE:2] [DUE:2026-09-01] [ID:zz01ab]',
            )

        with t.subTest('the event records where the child sits'):
            t.assertEqual(payload['ancestry'], 'Deck rebuild > Chip the brush')

    def test_update_task_reaches_a_third_level(t) -> None:
        doc = parse(
            '## Open\n\n'
            '- [ ] Trip prep [P:12]\n'
            '  - [ ] Pack cooler [LOE:1]\n'
            '    - [ ] Ice packs [LOE:1]\n'
        )
        parent = doc.tasks[0]
        child = parent.children[0]
        t.lookup.record = TaskRecord(
            t.path, doc, [parent, child, child.children[0]]
        )

        update_task(t.dir, 'Ice packs', {'DUE': '2026-09-01'}, TODAY)
        payload = t.append.call_args[0][2]

        with t.subTest('the ancestry names every level above the target'):
            t.assertEqual(
                payload['ancestry'], 'Trip prep > Pack cooler > Ice packs'
            )

    def test_update_task_rejected(t) -> None:
        with (
            t.subTest('an update that names no change'),
            t.assertRaisesRegex(ValueError, 'nothing to update'),
        ):
            update_task(t.dir, '9o71lx', {}, TODAY)

        with (
            t.subTest('a value btodo cannot read'),
            t.assertRaisesRegex(ValueError, 'DUE must be an ISO date'),
        ):
            update_task(t.dir, '9o71lx', {'DUE': 'someday'}, TODAY)

        doc = parse(SUBTASK_DOC)
        parent = doc.tasks[0]
        t.lookup.record = TaskRecord(t.path, doc, [parent, parent.children[0]])

        with (
            t.subTest('a field the top-level task owns'),
            t.assertRaisesRegex(ValueError, 'P belongs to the top-level task'),
        ):
            update_task(t.dir, 'Chip the brush', {'P': '5'}, TODAY)

        with t.subTest('a checklist item, which carries no fields'):
            item = parse('## Open\n\n- [ ] Deck [P:4]\n  - [ ] Sweep up\n')
            t.lookup.record = TaskRecord(
                t.path, item, [item.tasks[0], item.tasks[0].children[0]]
            )
            with t.assertRaisesRegex(ValueError, 'checklist item'):
                update_task(t.dir, 'Sweep up', {'DUE': '2026-09-01'}, TODAY)

        with t.subTest('nothing is written and nothing is logged'):
            t.path.write_text.assert_not_called()


SUBTASK_DOC = """# Work

## Open

- [ ] Deck rebuild [P:4] [LOE:8] [ID:9o71lx]
      A note that stays put.
  - [ ] Chip the brush [LOE:2]
- [ ] Bare [P:2]

## Done
"""


class AddSubtaskTests(IsolatedTests):
    """Unit tests for battodo.mutate.add_subtask."""

    TARGETS = ('discover_lists', 'TaskSelection', 'Journal', 'new_task_id')

    discover_lists: MagicMock

    def setUp(t) -> None:
        super().setUp()
        t.path.stem = 'work'
        t.discover_lists.return_value = [t.path]
        t.doc = parse(SUBTASK_DOC)
        t.lookup.record = TaskRecord(t.path, t.doc, [t.doc.tasks[0]])

    def test_add_subtask(t) -> None:
        path, entry = add_subtask(
            t.dir, 'work', '9o71lx', 'Buy lumber', {'LOE': '2'}
        )

        with t.subTest('the parent selector is resolved in the directory'):
            t.TaskSelection.assert_called_with(t.dir, '9o71lx')

        with t.subTest('the line is indented one level under its parent'):
            t.assertEqual(entry, '  - [ ] Buy lumber [LOE:2] [ID:zz01ab]')
            t.assertEqual(path, t.path)

        with t.subTest('and lands last in the parent block'):
            t.path.write_text.assert_called_with(
                SUBTASK_DOC.replace(
                    '  - [ ] Chip the brush [LOE:2]\n',
                    f'  - [ ] Chip the brush [LOE:2]\n{entry}\n',
                )
            )

    def test_add_subtask_event(t) -> None:
        add_subtask(t.dir, 'work', '9o71lx', 'Buy lumber', {'LOE': '2'})

        with t.subTest('the journal of the source directory'):
            t.Journal.assert_called_with(t.dir)

        with t.subTest('one TaskAdded, on the new subtask stream'):
            t.append.assert_called_once_with(
                'TaskAdded',
                'task/zz01ab',
                {
                    'delta': {'LOE': [None, '2'], 'ID': [None, 'zz01ab']},
                    # Post-state, as for any add: there is no prior
                    # state for a snapshot to describe.
                    'snapshot': {
                        'title': 'Buy lumber',
                        'done': False,
                        'fields': {'LOE': '2', 'ID': 'zz01ab'},
                    },
                    # The file states the hierarchy by indentation, so
                    # the id names the parent here and nowhere else.
                    'parent': '9o71lx',
                },
                actor='agent',
                source_file='work.md',
            )

    def test_add_subtask_stamps_the_parent(t) -> None:
        parent = t.doc.tasks[1]
        t.lookup.record = TaskRecord(t.path, t.doc, [parent])
        t.new_task_id.side_effect = ['pp02cd', 'cc03ef']

        _, entry = add_subtask(t.dir, 'work', 'Bare', 'Get quotes', {})
        stamp, added = t.append.call_args_list

        with t.subTest('a parent with no id of its own is given one'):
            t.assertIn(
                '- [ ] Bare [P:2] [ID:pp02cd]',
                t.path.write_text.call_args[0][0],
            )
            t.assertEqual(entry, '  - [ ] Get quotes [ID:cc03ef]')

        with t.subTest('the stamp is an event of its own, on that stream'):
            t.assertEqual(
                stamp.args,
                (
                    'TaskUpdated',
                    'task/pp02cd',
                    {
                        'delta': {'ID': [None, 'pp02cd']},
                        'snapshot': {
                            'title': 'Bare',
                            'done': False,
                            'fields': {'P': '2'},
                        },
                    },
                ),
            )

        with t.subTest('which the child then names as its parent'):
            t.assertEqual(added.args[1], 'task/cc03ef')
            t.assertEqual(added.args[2]['parent'], 'pp02cd')

    def test_add_subtask_rejected(t) -> None:
        for name in ('P', 'REPEAT'):
            with (
                t.subTest(f'{name} belongs to the top-level task'),
                t.assertRaisesRegex(
                    ValueError, f'{name} belongs to the top-level task'
                ),
            ):
                add_subtask(t.dir, 'work', '9o71lx', 'X', {name: '3'})

        with (
            t.subTest('a value btodo cannot read'),
            t.assertRaisesRegex(ValueError, 'DUE must be an ISO date'),
        ):
            add_subtask(t.dir, 'work', '9o71lx', 'X', {'DUE': 'someday'})

        with t.subTest('an unknown list'), t.assertRaises(ListError):
            add_subtask(t.dir, 'wrk', '9o71lx', 'X', {})

        with t.subTest('a checklist item, which cannot hold an id'):
            item = parse('## Open\n\n- [ ] Deck [P:4]\n  - [ ] Sweep up\n')
            t.lookup.record = TaskRecord(
                t.path, item, [item.tasks[0], item.tasks[0].children[0]]
            )
            with t.assertRaisesRegex(ValueError, 'checklist item'):
                add_subtask(t.dir, 'work', 'Sweep up', 'X', {})

        with t.subTest('a parent that lives in another list'):
            other = Path('chores.md')
            t.lookup.record = TaskRecord(other, t.doc, [t.doc.tasks[0]])
            with t.assertRaisesRegex(ValueError, 'a task in chores.md'):
                add_subtask(t.dir, 'work', '9o71lx', 'X', {})

        with t.subTest('nothing is written and nothing is logged'):
            t.path.write_text.assert_not_called()
            t.append.assert_not_called()


OPEN_DOC = """# Work

## Open

- [ ] Deck rebuild [P:4] [ID:9o71lx]

## Done
"""

CASCADE_DOC = """# Work

## Open

- [ ] Deck rebuild [P:4] [ID:9o71lx]
  - [ ] Chip the brush [LOE:2]
  - [x] Sand it [LOE:1]
- [ ] Bare [P:2]

## Done
"""

REPEAT_DOC = """# Chores

## Open

- [ ] Water the plants [P:3] [REPEAT:7d] [DUE:2026-08-05] [ID:rr01ab]

## Done
"""


class FileIsolatedTests(TestCase):
    """Base: the list file, the directory and the journal stand in.

    The document is real, parsed from the suite's own fixture, so what
    a test stands on stays beside the test. Nothing reaches a disk.
    """

    TARGETS: tuple[str, ...] = ('Journal', 'new_task_id')

    Journal: MagicMock
    new_task_id: MagicMock

    def setUp(t) -> None:
        for target in t.TARGETS:
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        t.new_task_id.return_value = 'zz01ab'
        t.append = t.Journal.return_value.append

        t.path = MagicMock(spec=Path)
        t.path.name = 'work.md'
        t.path.stem = 'work'
        t.dir = MagicMock(spec=Path)
        t.log = t.dir.__truediv__.return_value
        t.log_handle = t.log.open.return_value.__enter__.return_value

    def written(t) -> list[str]:
        """The lines of the document handed to `write_text`."""
        return t.path.write_text.call_args[0][0].split('\n')

    def logged(t) -> str:
        """What the completed log was asked to append."""
        return t.log_handle.write.call_args[0][0]


class AddTaskIsolationTests(FileIsolatedTests):
    """Unit tests for battodo.mutate.add_task."""

    TARGETS = (*FileIsolatedTests.TARGETS, '_resolve_list')

    _resolve_list: MagicMock

    def setUp(t) -> None:
        super().setUp()
        t._resolve_list.return_value = t.path
        t.path.read_text.return_value = OPEN_DOC

    def test_add_task(t) -> None:
        path, entry = add_task(t.dir, 'work', 'Buy lumber', {'P': '3'}, TODAY)

        with t.subTest('the list is resolved in the source directory'):
            t._resolve_list.assert_called_once_with(t.dir, 'work')
            t.assertEqual(path, t.path)

        with t.subTest('the line carries the supplied field and the stamps'):
            t.assertEqual(
                entry,
                f'- [ ] Buy lumber [P:3] [ADDED:{TODAY.isoformat()}] '
                '[ID:zz01ab]',
            )

        with t.subTest('and lands last in the open section'):
            lines = t.written()
            t.assertEqual(lines[lines.index('## Done') - 2], entry)

        with t.subTest('one TaskAdded, on the new task stream'):
            t.Journal.assert_called_once_with(t.dir)
            stream, payload = t.append.call_args[0][1:3]
            t.assertEqual(stream, 'task/zz01ab')
            t.assertEqual(payload['snapshot']['title'], 'Buy lumber')
            t.assertEqual(payload['delta']['P'], [None, '3'])
            t.assertEqual(
                t.append.call_args[1],
                {'actor': 'agent', 'source_file': 'work.md'},
            )

    def test_add_task_rejected(t) -> None:
        cases = {
            'a priority that is not a number': ({'P': 'high'}, ValueError),
            'a level of effort off the scale': ({'LOE': '4'}, ValueError),
            'a due date btodo cannot read': ({'DUE': 'someday'}, ValueError),
            'a recurrence it cannot read': ({'REPEAT': 'often'}, RepeatError),
        }
        for name, (fields, error) in cases.items():
            with t.subTest(name), t.assertRaises(error):
                add_task(t.dir, 'work', 'X', fields, TODAY)

        with t.subTest('nothing is written and nothing is logged'):
            t.path.write_text.assert_not_called()
            t.append.assert_not_called()


class CompleteIsolationTests(FileIsolatedTests):
    """Unit tests for battodo.mutate.complete."""

    TARGETS = (*FileIsolatedTests.TARGETS, 'TaskSelection')

    TaskSelection: MagicMock

    def setUp(t) -> None:
        super().setUp()
        t.doc = parse(CASCADE_DOC)
        t.lookup = t.TaskSelection.return_value

    def record(t, ancestry_titles: list[str]) -> TaskRecord:
        """A record for the ancestry the titles name, deepest last."""
        ancestry: list = []
        tasks = t.doc.tasks
        for title in ancestry_titles:
            found = next(task for task in tasks if task.title == title)
            ancestry.append(found)
            tasks = found.children
        return TaskRecord(t.path, t.doc, ancestry)

    def test_complete(t) -> None:
        t.lookup.record = t.record(['Deck rebuild', 'Chip the brush'])

        entries = complete(t.dir, 'Chip the brush', TODAY)

        with t.subTest('the finished block leaves the open section'):
            written = t.written()
            t.assertNotIn('  - [ ] Chip the brush [LOE:2]', written)
            t.assertNotIn('- [ ] Deck rebuild [P:4] [ID:9o71lx]', written)

        with t.subTest('and the task that followed it stays'):
            t.assertIn('- [ ] Bare [P:2]', written)

        with t.subTest('the log records the child under its ancestry'):
            t.assertEqual(
                entries[0],
                f'{TODAY.isoformat()} | work | DONE | '
                'Deck rebuild > Chip the brush [LOE:2]',
            )

        with t.subTest('then the parent it finished'):
            t.assertEqual(
                entries[1],
                f'{TODAY.isoformat()} | work | DONE | Deck rebuild [P:4]',
            )

        with t.subTest('which is what the completed log is handed'):
            t.assertEqual(t.logged(), '\n'.join(entries) + '\n')

        with t.subTest('one event a completion, deepest first'):
            child, parent = t.append.call_args_list
            t.assertEqual(
                child.args[2]['ancestry'], 'Deck rebuild > Chip the brush'
            )
            t.assertEqual(child.args[2]['delta'], {'done': [False, True]})
            t.assertEqual(parent.args[1], 'task/9o71lx')

    def test_complete_a_child_whose_parent_stays_open(t) -> None:
        doc = parse(
            '## Open\n\n'
            '- [ ] Deck rebuild [P:4] [ID:9o71lx]\n'
            '  - [ ] Chip the brush [LOE:2]\n'
            '  - [ ] Sand it [LOE:1]\n'
        )
        t.doc = doc
        parent = doc.tasks[0]
        t.lookup.record = TaskRecord(t.path, doc, [parent, parent.children[0]])

        entries = complete(t.dir, 'Chip the brush', TODAY)

        with t.subTest('the child box is checked, and the child stamped'):
            written = t.written()
            t.assertIn('  - [x] Chip the brush [LOE:2] [ID:zz01ab]', written)

        with t.subTest('the parent it did not finish stays open'):
            t.assertIn('- [ ] Deck rebuild [P:4] [ID:9o71lx]', written)

        with t.subTest('the parent it did not finish stays out of the log'):
            t.assertEqual(len(entries), 1)
            t.assertIn('Deck rebuild > Chip the brush', entries[0])

        with t.subTest('and one event lands, on the stream just stamped'):
            t.append.assert_called_once()
            t.assertEqual(t.append.call_args[0][1], 'task/zz01ab')

    def test_complete_a_recurrence(t) -> None:
        t.doc = parse(REPEAT_DOC)
        t.path.stem = 'chores'
        t.lookup.record = t.record(['Water the plants'])

        complete(t.dir, 'rr01ab', TODAY)

        with t.subTest('the task stays open, rescheduled to its next due'):
            line = next(
                line for line in t.written() if 'Water the plants' in line
            )
            t.assertIn('- [ ] Water the plants', line)
            t.assertIn('[DUE:2026-08-15]', line)

        with t.subTest('and keeps the id it already carried'):
            t.assertIn('[ID:rr01ab]', line)

        with t.subTest('the event records the reschedule beside the done'):
            payload = t.append.call_args[0][2]
            t.assertEqual(payload['delta']['done'], [False, True])
            t.assertEqual(
                payload['delta']['DUE'], ['2026-08-05', '2026-08-15']
            )


class ScratchIsolationTests(FileIsolatedTests):
    """Unit tests for battodo.mutate.scratch."""

    TARGETS = (*FileIsolatedTests.TARGETS, 'TaskSelection')

    TaskSelection: MagicMock

    def setUp(t) -> None:
        super().setUp()
        t.doc = parse(CASCADE_DOC)
        t.parent = t.doc.tasks[0]
        t.lookup = t.TaskSelection.return_value

    def test_scratch(t) -> None:
        t.lookup.record = TaskRecord(t.path, t.doc, [t.parent])

        entries = scratch(t.dir, '9o71lx', TODAY)

        with t.subTest('the task and everything under it are removed'):
            written = t.written()
            t.assertNotIn('- [ ] Deck rebuild [P:4] [ID:9o71lx]', written)
            t.assertNotIn('  - [ ] Chip the brush [LOE:2]', written)

        with t.subTest('the task that followed it stays'):
            t.assertIn('- [ ] Bare [P:2]', written)

        with t.subTest('the log records the abandonment'):
            logged = (
                f'{TODAY.isoformat()} | work | SCRATCHED | Deck rebuild [P:4]'
            )
            t.assertEqual(entries, [logged])
            t.assertEqual(t.logged(), logged + '\n')

        with t.subTest('one SCRATCHED event, on the task stream'):
            t.append.assert_called_once()
            stream, payload = t.append.call_args[0][1:3]
            t.assertEqual(stream, 'task/9o71lx')
            t.assertEqual(payload['delta'], {'removed': [False, True]})
            t.assertEqual(payload['ancestry'], 'Deck rebuild')

    def test_scratch_collapses_the_blank_run_it_leaves(t) -> None:
        doc = parse(
            '## Open\n\n'
            '- [ ] Deck rebuild [P:4] [ID:9o71lx]\n'
            '\n'
            '- [ ] Bare [P:2]\n'
        )
        t.doc = doc
        t.lookup.record = TaskRecord(t.path, doc, [doc.tasks[0]])

        scratch(t.dir, '9o71lx', TODAY)

        with t.subTest('no pair of blank lines is left behind'):
            written = t.written()
            pairs = [
                index
                for index in range(len(written) - 1)
                if not written[index].strip()
                and not written[index + 1].strip()
            ]
            t.assertEqual(pairs, [])

    def test_scratch_a_checklist_item(t) -> None:
        doc = parse('## Open\n\n- [ ] Deck [P:4]\n  - [ ] Sweep up\n')
        parent = doc.tasks[0]
        t.doc = doc
        t.lookup.record = TaskRecord(t.path, doc, [parent, parent.children[0]])

        entries = scratch(t.dir, 'Sweep up', TODAY)

        with t.subTest('a checklist item is not logged as work abandoned'):
            t.assertEqual(entries, [])
            t.log.open.assert_not_called()

        with t.subTest('the event lands on the ancestor stream instead'):
            t.assertEqual(t.append.call_args[0][1], 'task/zz01ab')

        with t.subTest('whose line is stamped, since it carries the id'):
            t.assertIn('- [ ] Deck [P:4] [ID:zz01ab]', t.written())


class BackfillIsolationTests(FileIsolatedTests):
    """Unit tests for battodo.mutate.backfill_all."""

    TARGETS = (*FileIsolatedTests.TARGETS, 'discover_lists')

    discover_lists: MagicMock

    def setUp(t) -> None:
        super().setUp()
        t.discover_lists.return_value = [t.path]
        t.journal = t.Journal.return_value
        t.path.read_text.return_value = (
            '## Open\n\n'
            '- [ ] No date [P:4]\n'
            '- [ ] Dated [P:3] [ADDED:2026-01-05]\n'
            '- [x] Finished [P:2]\n'
            '- [ ] Placeholder [P:6] [DUE:YYYY-MM-DD]\n'
            '  - [ ] A child [LOE:1]\n'
        )

    def test_backfill_file(t) -> None:
        stamped = backfill_file(t.path, TODAY, t.journal)

        with t.subTest('only the task with no add date is stamped'):
            t.assertEqual(stamped, ['No date'])

        with t.subTest('which gains the date and an id'):
            t.assertIn(
                f'- [ ] No date [P:4] [ADDED:{TODAY.isoformat()}] [ID:zz01ab]',
                t.written(),
            )

        with t.subTest('a line btodo cannot read is left alone'):
            t.assertIn('- [ ] Placeholder [P:6] [DUE:YYYY-MM-DD]', t.written())

        with t.subTest('the event says the date is the migration date'):
            payload = t.journal.append.call_args[0][2]
            t.assertTrue(payload['backfilled'])
            t.assertEqual(payload['delta']['ADDED'], [None, TODAY.isoformat()])

    def test_backfill_file_writes_nothing_when_nothing_is_missing(t) -> None:
        t.path.read_text.return_value = (
            '## Open\n\n- [ ] Dated [P:3] [ADDED:2026-01-05]\n'
        )

        t.assertEqual(backfill_file(t.path, TODAY, t.journal), [])
        t.path.write_text.assert_not_called()

    def test_backfill_all(t) -> None:
        result = backfill_all(t.dir, TODAY)

        with t.subTest('every discovered list is read'):
            t.discover_lists.assert_called_once_with(t.dir)

        with t.subTest('and the stamped titles are keyed by file name'):
            t.assertEqual(result, {'work.md': ['No date']})

        with t.subTest('one journal serves the whole run'):
            t.Journal.assert_called_once_with(t.dir)

    def test_backfill_all_reports_only_the_files_it_changed(t) -> None:
        t.path.read_text.return_value = (
            '## Open\n\n- [ ] Dated [P:3] [ADDED:2026-01-05]\n'
        )

        t.assertEqual(backfill_all(t.dir, TODAY), {})
