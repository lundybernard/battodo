from datetime import date
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, call, create_autospec, patch

from ..mutate import (
    OPEN_HEADING,
    ListError,
    TaskNode,
    TaskRecord,
    TodoDocument,
    add_subtask,
    add_task,
    backfill_all,
    backfill_file,
    complete,
    scratch,
    task_snapshot,
    update_task,
)
from ..repeat import RepeatError

SRC = 'battodo.mutate'

TODAY = date(2026, 8, 8)
# Raw lines as a hand-written list holds them. The parser renders what
# a mutation writes, so these are input to the unit under test, never
# something it is expected to produce.
TASK_LINE = '- [ ] A task [P:4] [LOE:8] [ID:9o71lx]'
NOTE_LINE = '      A note that stays put.'
CHILD_LINE = '  - [ ] A subtask of it [LOE:2]'
DONE_CHILD_LINE = '  - [x] A finished subtask [LOE:1]'
GRANDCHILD_LINE = '    - [ ] A task below the subtask [LOE:1]'
ITEM_LINE = '  - [ ] A checklist item'
BARE_LINE = '- [ ] A task with no id [P:2]'
REPEAT_LINE = (
    '- [ ] A recurring task [P:3] [REPEAT:7d] [DUE:2026-08-05] [ID:rr01ab]'
)


class TaskSnapshotTests(TestCase):
    """Unit tests for battodo.mutate.task_snapshot."""

    def test_task_snapshot(t) -> None:
        task = TaskNode(
            raw_index=1,
            indent=0,
            done=False,
            title='A task',
            fields={'P': '2', 'TAGS': 'a-tag'},
            raw=TASK_LINE,
        )

        t.assertEqual(
            task_snapshot(task),
            {
                'title': 'A task',
                'done': False,
                'fields': {'P': '2', 'TAGS': 'a-tag'},
            },
        )


class IsolatedTests(TestCase):
    """Base: the list document, the journal and the file all stand in.

    What the document renders is pinned against real files in the
    integration suite, not here.
    """

    TARGETS: tuple[str, ...] = ('Journal', 'new_task_id')

    Journal: MagicMock
    new_task_id: MagicMock

    def setUp(t) -> None:
        for target in t.TARGETS:
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        t.append = t.Journal.return_value.append
        t.new_task_id.return_value = 'zz01ab'

        t.path = MagicMock(spec=Path)
        t.path.name = 'a-list.md'
        t.path.stem = 'a-list'
        t.dir = MagicMock(spec=Path)
        t.log = t.dir.__truediv__.return_value
        t.log.exists.return_value = True
        t.log.read_text.return_value = '# Completed Tasks\n'
        t.log_handle = t.log.open.return_value.__enter__.return_value

    def logged(t) -> str:
        """What the completed log was asked to append."""
        return t.log_handle.write.call_args[0][0]

    def document(t, *lines: str) -> MagicMock:
        """A list document standing in for the one the file holds."""
        doc = create_autospec(TodoDocument, instance=True)
        doc.lines = list(lines)
        return doc

    def dated_list(t) -> MagicMock:
        """A list whose one task already carries its add date."""
        doc = t.document(OPEN_HEADING, DATED_LINE)
        doc.tasks = [
            TaskNode(
                raw_index=1,
                indent=0,
                done=False,
                title='A task already dated',
                fields={'P': '3', 'ADDED': '2026-01-05'},
                raw=DATED_LINE,
            )
        ]
        return doc


class UpdateTaskTests(IsolatedTests):
    """Unit tests for battodo.mutate.update_task."""

    TARGETS = (*IsolatedTests.TARGETS, 'TaskSelection')

    TaskSelection: MagicMock

    def setUp(t) -> None:
        super().setUp()
        t.task = TaskNode(
            raw_index=1,
            indent=0,
            done=False,
            title='A task',
            fields={'P': '4', 'LOE': '8', 'ID': '9o71lx'},
            raw=TASK_LINE,
            note_indices=[2],
        )
        t.doc = t.document(OPEN_HEADING, TASK_LINE, NOTE_LINE, CHILD_LINE)
        t.lookup = t.TaskSelection.return_value
        t.lookup.record = TaskRecord(t.path, t.doc, [t.task])

    def test_line(t) -> None:
        with t.subTest('the selector is resolved against the directory'):
            path, entry = update_task(
                t.dir,
                '9o71lx',
                {'P': '5'},
                TODAY,
                title='A new title',
            )

            t.TaskSelection.assert_called_once_with(t.dir, '9o71lx')

        with t.subTest('the named field is written on to the task line'):
            t.assertEqual(t.doc.set_field.call_args_list, [call(1, 'P', '5')])

        with t.subTest('and the new title over what the fields left'):
            t.doc.set_title.assert_called_once_with(1, 'A new title')
            t.assertEqual(entry, t.doc.set_title.return_value)

        with t.subTest('and the document goes to the file it came from'):
            t.path.write_text.assert_called_once_with(t.doc.text)
            t.assertEqual(path, t.path)

    def test_event(t) -> None:
        update_task(t.dir, '9o71lx', {'P': '5'}, TODAY, title='A new title')

        with t.subTest('the journal of the source directory'):
            t.Journal.assert_called_once_with(t.dir)

        with t.subTest('one TaskUpdated, on the task stream'):
            t.append.assert_called_once_with(
                'TaskUpdated',
                'task/9o71lx',
                {
                    'delta': {
                        'P': ['4', '5'],
                        'title': ['A task', 'A new title'],
                    },
                    # Pre-state, as everywhere but an add: the delta
                    # says what changed, the snapshot what it was.
                    'snapshot': {
                        'title': 'A task',
                        'done': False,
                        'fields': {'P': '4', 'LOE': '8', 'ID': '9o71lx'},
                    },
                },
                actor='agent',
                source_file='a-list.md',
            )

    def test_stamps_an_id(t) -> None:
        with t.subTest('a task with no id of its own is given one'):
            bare = TaskNode(
                raw_index=1,
                indent=0,
                done=False,
                title='A task with no id',
                fields={'P': '2'},
                raw=BARE_LINE,
            )
            t.lookup.record = TaskRecord(t.path, t.doc, [bare])

            _, entry = update_task(t.dir, 'no id', {'P': '5'}, TODAY)

            t.assertEqual(
                t.doc.set_field.call_args_list,
                [call(1, 'P', '5'), call(1, 'ID', 'zz01ab')],
            )
            t.assertEqual(entry, t.doc.lines[1])

        with t.subTest('the stamp names the stream, and rides the delta'):
            stream, payload = t.append.call_args[0][1:3]
            t.assertEqual(stream, 'task/zz01ab')
            t.assertEqual(payload['delta']['ID'], [None, 'zz01ab'])

        with t.subTest('a title left off names no title change'):
            t.doc.set_title.assert_not_called()
            t.assertNotIn('title', payload['delta'])

    def test_reaches_a_subtask(t) -> None:
        with t.subTest('a subtask event records where the child sits'):
            child = TaskNode(
                raw_index=3,
                indent=2,
                done=False,
                title='A subtask of it',
                fields={'LOE': '2'},
                raw=CHILD_LINE,
            )
            t.lookup.record = TaskRecord(t.path, t.doc, [t.task, child])

            update_task(t.dir, 'subtask', {'DUE': '2026-09-01'}, TODAY)

            payload = t.append.call_args[0][2]
            t.assertEqual(payload['ancestry'], 'A task > A subtask of it')

        with t.subTest('a due date is normalised before it is written'):
            t.assertEqual(
                t.doc.set_field.call_args_list[0],
                call(3, 'DUE', '2026-09-01'),
            )

    def test_reaches_a_third_level(t) -> None:
        with t.subTest('the ancestry names every level above the target'):
            child = TaskNode(
                raw_index=3,
                indent=2,
                done=False,
                title='A subtask of it',
                fields={'LOE': '2'},
                raw=CHILD_LINE,
            )
            below = TaskNode(
                raw_index=3,
                indent=4,
                done=False,
                title='A task below the subtask',
                fields={'LOE': '1'},
                raw=GRANDCHILD_LINE,
            )
            t.lookup.record = TaskRecord(t.path, t.doc, [t.task, child, below])

            update_task(t.dir, 'below', {'DUE': '2026-09-01'}, TODAY)

            t.assertEqual(
                t.append.call_args[0][2]['ancestry'],
                'A task > A subtask of it > A task below the subtask',
            )

    def test_rejected(t) -> None:
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

        child = TaskNode(
            raw_index=3,
            indent=2,
            done=False,
            title='A subtask of it',
            fields={'LOE': '2'},
            raw=CHILD_LINE,
        )
        t.lookup.record = TaskRecord(t.path, t.doc, [t.task, child])

        with (
            t.subTest('a field the top-level task owns'),
            t.assertRaisesRegex(ValueError, 'P belongs to the top-level task'),
        ):
            update_task(t.dir, 'subtask', {'P': '5'}, TODAY)

        item = TaskNode(
            raw_index=3,
            indent=2,
            done=False,
            title='A checklist item',
            fields={},
            raw=ITEM_LINE,
        )
        t.lookup.record = TaskRecord(t.path, t.doc, [t.task, item])

        with (
            t.subTest('a checklist item, which carries no fields'),
            t.assertRaisesRegex(ValueError, 'checklist item'),
        ):
            update_task(t.dir, 'checklist', {'DUE': '2026-09-01'}, TODAY)

        with t.subTest('nothing is written and nothing is logged'):
            t.path.write_text.assert_not_called()
            t.append.assert_not_called()


class AddSubtaskTests(IsolatedTests):
    """Unit tests for battodo.mutate.add_subtask."""

    TARGETS = (
        *IsolatedTests.TARGETS,
        'TaskSelection',
        'discover_lists',
        'TodoDocument',
    )

    TaskSelection: MagicMock
    discover_lists: MagicMock
    TodoDocument: MagicMock

    def setUp(t) -> None:
        super().setUp()
        t.discover_lists.return_value = [t.path]
        t.child = TaskNode(
            raw_index=3,
            indent=2,
            done=False,
            title='A subtask of it',
            fields={'LOE': '2'},
            raw=CHILD_LINE,
        )
        t.task = TaskNode(
            raw_index=1,
            indent=0,
            done=False,
            title='A task',
            fields={'P': '4', 'LOE': '8', 'ID': '9o71lx'},
            raw=TASK_LINE,
            children=[t.child],
            note_indices=[2],
        )
        t.bare = TaskNode(
            raw_index=4,
            indent=0,
            done=False,
            title='A task with no id',
            fields={'P': '2'},
            raw=BARE_LINE,
        )
        t.doc = t.document(
            OPEN_HEADING,
            TASK_LINE,
            NOTE_LINE,
            CHILD_LINE,
            BARE_LINE,
        )
        t.lookup = t.TaskSelection.return_value
        t.lookup.record = TaskRecord(t.path, t.doc, [t.task])
        t.added('A new subtask', {'LOE': '2', 'ID': 'zz01ab'})

    def added(t, title: str, fields: dict[str, str]) -> None:
        """What the parser reads back off the line just written."""
        t.TodoDocument.return_value.tasks = [
            TaskNode(
                raw_index=1,
                indent=2,
                done=False,
                title=title,
                fields=fields,
            )
        ]

    def test_line(t) -> None:
        with t.subTest('the list and the parent are resolved in the source'):
            path, entry = add_subtask(
                t.dir,
                'a-list',
                '9o71lx',
                'A new subtask',
                {'LOE': '2'},
            )

            t.discover_lists.assert_called_once_with(t.dir)
            t.TaskSelection.assert_called_once_with(t.dir, '9o71lx')
            t.assertEqual(path, t.path)

        with t.subTest('the line is indented one level under its parent'):
            t.assertEqual(t.doc.lines[4], '  - [ ] A new subtask')

        with t.subTest('and lands after every line the parent owns'):
            t.assertEqual(
                t.doc.lines,
                [
                    OPEN_HEADING,
                    TASK_LINE,
                    NOTE_LINE,
                    CHILD_LINE,
                    '  - [ ] A new subtask',
                    BARE_LINE,
                ],
            )

        with t.subTest('and the entry returned is the line it now holds'):
            t.assertIs(entry, t.doc.lines[4])

        with t.subTest('the fields go on to the line it now occupies'):
            t.assertEqual(
                t.doc.set_field.call_args_list,
                [call(4, 'LOE', '2'), call(4, 'ID', 'zz01ab')],
            )

        with t.subTest('the document goes to the file it came from'):
            t.path.write_text.assert_called_once_with(t.doc.text)

    def test_event(t) -> None:
        _, entry = add_subtask(
            t.dir,
            'a-list',
            '9o71lx',
            'A new subtask',
            {'LOE': '2'},
        )

        with t.subTest('the journal of the source directory'):
            t.Journal.assert_called_once_with(t.dir)

        with t.subTest('one TaskAdded, on the new subtask stream'):
            t.append.assert_called_once_with(
                'TaskAdded',
                'task/zz01ab',
                {
                    'delta': {'LOE': [None, '2'], 'ID': [None, 'zz01ab']},
                    # Post-state, as for any add: there is no prior
                    # state for a snapshot to describe, so the line as
                    # written is read back.
                    'snapshot': {
                        'title': 'A new subtask',
                        'done': False,
                        'fields': {'LOE': '2', 'ID': 'zz01ab'},
                    },
                    # The file states the hierarchy by indentation, so
                    # the id names the parent here and nowhere else.
                    'parent': '9o71lx',
                },
                actor='agent',
                source_file='a-list.md',
            )
            t.TodoDocument.assert_called_once_with(f'{OPEN_HEADING}\n{entry}')

    def test_stamps_the_parent(t) -> None:
        with t.subTest('a parent with no id of its own is given one'):
            t.lookup.record = TaskRecord(t.path, t.doc, [t.bare])
            t.new_task_id.side_effect = ['pp02cd', 'cc03ef']
            t.added('A second subtask', {'ID': 'cc03ef'})

            add_subtask(t.dir, 'a-list', 'no id', 'A second subtask', {})

            t.assertEqual(
                t.doc.set_field.call_args_list,
                [call(4, 'ID', 'pp02cd'), call(5, 'ID', 'cc03ef')],
            )

        with t.subTest('the stamp is an event of its own, on that stream'):
            stamp, added = t.append.call_args_list
            t.assertEqual(
                stamp.args,
                (
                    'TaskUpdated',
                    'task/pp02cd',
                    {
                        'delta': {'ID': [None, 'pp02cd']},
                        'snapshot': {
                            'title': 'A task with no id',
                            'done': False,
                            'fields': {'P': '2'},
                        },
                    },
                ),
            )
            t.assertEqual(
                stamp.kwargs,
                {'actor': 'agent', 'source_file': 'a-list.md'},
            )

        with t.subTest('which the child then names as its parent'):
            t.assertEqual(added.args[1], 'task/cc03ef')
            t.assertEqual(added.args[2]['parent'], 'pp02cd')

    def test_rejected(t) -> None:
        for name in ('P', 'REPEAT'):
            with (
                t.subTest(f'{name} belongs to the top-level task'),
                t.assertRaisesRegex(
                    ValueError,
                    f'{name} belongs to the top-level task',
                ),
            ):
                add_subtask(t.dir, 'a-list', '9o71lx', 'X', {name: '3'})

        with (
            t.subTest('a value btodo cannot read'),
            t.assertRaisesRegex(ValueError, 'DUE must be an ISO date'),
        ):
            add_subtask(t.dir, 'a-list', '9o71lx', 'X', {'DUE': 'someday'})

        with (
            t.subTest('a level of effort off the scale'),
            t.assertRaisesRegex(ValueError, 'LOE must be one of'),
        ):
            add_subtask(t.dir, 'a-list', '9o71lx', 'X', {'LOE': '4'})

        with t.subTest('a list no discovered file carries'):
            with t.assertRaises(ListError) as caught:
                add_subtask(t.dir, 'another-list', '9o71lx', 'X', {})
            t.assertIn('available: a-list', str(caught.exception))

        with t.subTest('a checklist item, which cannot hold an id'):
            item = TaskNode(
                raw_index=3,
                indent=2,
                done=False,
                title='A checklist item',
                fields={},
                raw=ITEM_LINE,
            )
            t.lookup.record = TaskRecord(t.path, t.doc, [t.task, item])
            with t.assertRaisesRegex(ValueError, 'checklist item'):
                add_subtask(t.dir, 'a-list', 'checklist', 'X', {})

        with t.subTest('a parent that lives in another list'):
            other = MagicMock(spec=Path)
            other.name = 'another-list.md'
            t.lookup.record = TaskRecord(other, t.doc, [t.task])
            with t.assertRaisesRegex(ValueError, 'a task in another-list.md'):
                add_subtask(t.dir, 'a-list', '9o71lx', 'X', {})

        with t.subTest('nothing is written and nothing is logged'):
            t.path.write_text.assert_not_called()
            t.append.assert_not_called()


NEW_LINE = '- [ ] A new task'
NO_DATE_LINE = '- [ ] A task with no add date [P:4]'
IDENTIFIED_LINE = '- [ ] A task already identified [P:5] [ID:ii04gh]'
DATED_LINE = '- [ ] A task already dated [P:3] [ADDED:2026-01-05]'
FINISHED_LINE = '- [x] A finished task [P:2]'
PLACEHOLDER_LINE = '- [ ] A task dated YYYY-MM-DD [P:6] [DUE:YYYY-MM-DD]'


class AddTaskTests(IsolatedTests):
    """Unit tests for battodo.mutate.add_task."""

    TARGETS = (*IsolatedTests.TARGETS, '_resolve_list', 'TodoDocument')

    _resolve_list: MagicMock
    TodoDocument: MagicMock

    def setUp(t) -> None:
        super().setUp()
        t._resolve_list.return_value = t.path
        # The document answers as though the append has happened: the
        # new entry is the line the index it hands back names.
        t.doc = t.document(OPEN_HEADING, TASK_LINE, NEW_LINE)
        t.doc.append_open.return_value = 2
        t.written = t.document()
        t.written.tasks = [
            TaskNode(
                raw_index=1,
                indent=0,
                done=False,
                title='A new task',
                fields={
                    'P': '3',
                    'TAGS': 'a-tag',
                    'ADDED': '2026-08-08',
                    'ID': 'zz01ab',
                },
            )
        ]
        t.TodoDocument.side_effect = [t.doc, t.written]

    def test_line(t) -> None:
        with t.subTest('the list is resolved in the source directory'):
            path, entry = add_task(
                t.dir,
                'a-list',
                'A new task',
                {'TAGS': 'a-tag', 'P': '3'},
                TODAY,
            )

            t._resolve_list.assert_called_once_with(t.dir, 'a-list')
            t.assertEqual(path, t.path)

        with t.subTest('the line joins the open section of the document'):
            t.TodoDocument.assert_any_call(t.path.read_text.return_value)
            t.doc.append_open.assert_called_once_with(NEW_LINE)
            t.assertIs(entry, t.doc.lines[2])

        with t.subTest('the fields go on in SCHEMA order, then the stamps'):
            t.assertEqual(
                t.doc.set_field.call_args_list,
                [
                    call(2, 'P', '3'),
                    call(2, 'TAGS', 'a-tag'),
                    call(2, 'ADDED', '2026-08-08'),
                    call(2, 'ID', 'zz01ab'),
                ],
            )

        with t.subTest('which then goes to the file it came from'):
            t.path.write_text.assert_called_once_with(t.doc.text)

    def test_event(t) -> None:
        add_task(
            t.dir,
            'a-list',
            'A new task',
            {'TAGS': 'a-tag', 'P': '3'},
            TODAY,
        )

        with t.subTest('the journal of the source directory'):
            t.Journal.assert_called_once_with(t.dir)

        with t.subTest('one TaskAdded, on the new task stream'):
            t.append.assert_called_once_with(
                'TaskAdded',
                'task/zz01ab',
                {
                    'delta': {
                        'P': [None, '3'],
                        'TAGS': [None, 'a-tag'],
                        'ADDED': [None, '2026-08-08'],
                        'ID': [None, 'zz01ab'],
                    },
                    # Post-state: an add has no prior state, so the
                    # line as written is read back for the snapshot.
                    'snapshot': {
                        'title': 'A new task',
                        'done': False,
                        'fields': {
                            'P': '3',
                            'TAGS': 'a-tag',
                            'ADDED': '2026-08-08',
                            'ID': 'zz01ab',
                        },
                    },
                },
                actor='agent',
                source_file='a-list.md',
            )

    def test_rejected(t) -> None:
        cases = {
            'a priority that is not a number': ({'P': 'high'}, ValueError),
            'a level of effort off the scale': ({'LOE': '4'}, ValueError),
            'a due date btodo cannot read': ({'DUE': 'someday'}, ValueError),
            'a recurrence it cannot read': ({'REPEAT': 'often'}, RepeatError),
        }
        for name, (fields, error) in cases.items():
            with t.subTest(name), t.assertRaises(error):
                add_task(t.dir, 'a-list', 'X', fields, TODAY)

        with t.subTest('nothing is written and nothing is logged'):
            t.path.write_text.assert_not_called()
            t.append.assert_not_called()


class BackfillFileTests(IsolatedTests):
    """Unit tests for battodo.mutate.backfill_file."""

    TARGETS = (*IsolatedTests.TARGETS, 'TodoDocument')

    TodoDocument: MagicMock

    def setUp(t) -> None:
        super().setUp()
        t.journal = t.Journal.return_value
        # One list holding every case the stamp distinguishes.
        placeholder = TaskNode(
            raw_index=5,
            indent=0,
            done=False,
            title='A task dated YYYY-MM-DD',
            fields={'P': '6', 'DUE': 'YYYY-MM-DD'},
            raw=PLACEHOLDER_LINE,
            children=[
                TaskNode(
                    raw_index=6,
                    indent=2,
                    done=False,
                    title='A subtask of it',
                    fields={'LOE': '2'},
                    raw=CHILD_LINE,
                )
            ],
        )
        t.doc = t.document(
            OPEN_HEADING,
            '',
            NO_DATE_LINE,
            IDENTIFIED_LINE,
            DATED_LINE,
            PLACEHOLDER_LINE,
            CHILD_LINE,
            FINISHED_LINE,
        )
        t.doc.tasks = [
            TaskNode(
                raw_index=2,
                indent=0,
                done=False,
                title='A task with no add date',
                fields={'P': '4'},
                raw=NO_DATE_LINE,
            ),
            TaskNode(
                raw_index=3,
                indent=0,
                done=False,
                title='A task already identified',
                fields={'P': '5', 'ID': 'ii04gh'},
                raw=IDENTIFIED_LINE,
            ),
            TaskNode(
                raw_index=4,
                indent=0,
                done=False,
                title='A task already dated',
                fields={'P': '3', 'ADDED': '2026-01-05'},
                raw=DATED_LINE,
            ),
            placeholder,
            TaskNode(
                raw_index=7,
                indent=0,
                done=True,
                title='A finished task',
                fields={'P': '2'},
                raw=FINISHED_LINE,
            ),
        ]
        t.TodoDocument.return_value = t.doc

    def test_stamps(t) -> None:
        with t.subTest('only the tasks with no add date are stamped'):
            stamped = backfill_file(t.path, TODAY, t.journal)

            t.TodoDocument.assert_called_once_with(
                t.path.read_text.return_value
            )
            t.assertEqual(
                stamped,
                ['A task with no add date', 'A task already identified'],
            )

        with t.subTest('one gains the date and an id, the other the date'):
            t.assertEqual(
                t.doc.set_field.call_args_list,
                [
                    call(2, 'ADDED', '2026-08-08'),
                    call(2, 'ID', 'zz01ab'),
                    call(3, 'ADDED', '2026-08-08'),
                ],
            )

        with t.subTest('the document goes to the file it came from'):
            t.path.write_text.assert_called_once_with(t.doc.text)

    def test_event(t) -> None:
        backfill_file(t.path, TODAY, t.journal)

        with t.subTest('the event says the date is the migration date'):
            stamp = t.append.call_args_list[0]
            stream, payload = stamp.args[1:3]
            t.assertEqual(stream, 'task/zz01ab')
            t.assertEqual(
                stamp.kwargs,
                {'actor': 'agent', 'source_file': 'a-list.md'},
            )
            t.assertEqual(
                payload,
                {
                    'delta': {'ADDED': [None, '2026-08-08']},
                    'snapshot': {
                        'title': 'A task with no add date',
                        'done': False,
                        'fields': {'P': '4'},
                    },
                    # A replay must not read the migration date as an
                    # observed fact.
                    'backfilled': True,
                },
            )

    def test_unchanged_file(t) -> None:
        with t.subTest('a file with nothing missing is not rewritten'):
            t.TodoDocument.return_value = t.dated_list()

            t.assertEqual(backfill_file(t.path, TODAY, t.journal), [])
            t.path.write_text.assert_not_called()
            t.append.assert_not_called()


class BackfillAllTests(IsolatedTests):
    """Unit tests for battodo.mutate.backfill_all."""

    TARGETS = (*IsolatedTests.TARGETS, 'TodoDocument', 'discover_lists')

    TodoDocument: MagicMock
    discover_lists: MagicMock

    def setUp(t) -> None:
        super().setUp()
        t.discover_lists.return_value = [t.path]
        doc = t.document(OPEN_HEADING, NO_DATE_LINE)
        doc.tasks = [
            TaskNode(
                raw_index=1,
                indent=0,
                done=False,
                title='A task with no add date',
                fields={'P': '4'},
                raw=NO_DATE_LINE,
            )
        ]
        t.TodoDocument.return_value = doc

    def test_lists(t) -> None:
        with t.subTest('every discovered list is stamped'):
            result = backfill_all(t.dir, TODAY)

            t.discover_lists.assert_called_once_with(t.dir)

        with t.subTest('and the stamped titles come back by file name'):
            t.assertEqual(result, {'a-list.md': ['A task with no add date']})

        with t.subTest('one journal serves the whole run'):
            t.Journal.assert_called_once_with(t.dir)

    def test_nothing_missing(t) -> None:
        with t.subTest('a list with nothing missing is left out'):
            t.TodoDocument.return_value = t.dated_list()

            t.assertEqual(backfill_all(t.dir, TODAY), {})


class CompleteTests(IsolatedTests):
    """Unit tests for battodo.mutate.complete."""

    TARGETS = (*IsolatedTests.TARGETS, 'TaskSelection', 'next_due')

    TaskSelection: MagicMock
    next_due: MagicMock

    def setUp(t) -> None:
        super().setUp()
        t.lookup = t.TaskSelection.return_value
        t.next_due.return_value = date(2026, 8, 15)
        t.child = TaskNode(
            raw_index=3,
            indent=2,
            done=False,
            title='A subtask of it',
            fields={'LOE': '2'},
            raw=CHILD_LINE,
        )
        t.finished = TaskNode(
            raw_index=4,
            indent=2,
            done=True,
            title='A finished subtask',
            fields={'LOE': '1'},
            raw=DONE_CHILD_LINE,
        )
        t.task = TaskNode(
            raw_index=1,
            indent=0,
            done=False,
            title='A task',
            fields={'P': '4', 'LOE': '8', 'ID': '9o71lx'},
            raw=TASK_LINE,
            children=[t.child, t.finished],
            note_indices=[2],
        )
        t.doc = t.document(
            OPEN_HEADING,
            TASK_LINE,
            NOTE_LINE,
            CHILD_LINE,
            DONE_CHILD_LINE,
            BARE_LINE,
        )
        t.doc.tasks = [t.task]
        t.lookup.record = TaskRecord(t.path, t.doc, [t.task, t.child])

    def test_cascade(t) -> None:
        with t.subTest('the finished block leaves the document'):
            entries = complete(t.dir, 'subtask', TODAY)

            t.TaskSelection.assert_called_once_with(t.dir, 'subtask')
            t.assertEqual(t.doc.lines, [OPEN_HEADING, BARE_LINE])

        with t.subTest('which then goes to the file it came from'):
            t.path.write_text.assert_called_once_with(t.doc.text)

        with t.subTest('the log records the child, then the parent'):
            t.assertEqual(
                entries,
                [
                    (
                        '2026-08-08 | a-list | DONE | '
                        'A task > A subtask of it [LOE:2]'
                    ),
                    '2026-08-08 | a-list | DONE | A task [P:4] [LOE:8]',
                ],
            )

        with t.subTest('which is what the completed log is handed'):
            t.dir.__truediv__.assert_called_once_with('completed.md')
            t.assertEqual(t.logged(), '\n'.join(entries) + '\n')

        with t.subTest('one event a completion, deepest first'):
            deepest, root = t.append.call_args_list
            t.assertEqual(
                deepest.args,
                (
                    'TaskCompleted',
                    'task/zz01ab',
                    {
                        'delta': {'done': [False, True]},
                        # Pre-state: the delta says what changed, the
                        # snapshot says what it changed from.
                        'snapshot': {
                            'title': 'A subtask of it',
                            'done': False,
                            'fields': {'LOE': '2'},
                        },
                        'ancestry': 'A task > A subtask of it',
                    },
                ),
            )
            t.assertEqual(root.args[1], 'task/9o71lx')

    def test_parent_stays_open(t) -> None:
        with t.subTest('a parent with another open child stays open'):
            t.finished.done = False

            entries = complete(t.dir, 'subtask', TODAY)

            t.assertEqual(t.doc.lines[1], TASK_LINE)
            t.assertEqual(len(entries), 1)

        with t.subTest('and the child is stamped, then checked off'):
            t.doc.set_field.assert_called_once_with(3, 'ID', 'zz01ab')
            t.assertEqual(t.doc.lines[3], '  - [x] A subtask of it [LOE:2]')

        with t.subTest('one event lands, on the stream just stamped'):
            t.append.assert_called_once()
            t.assertEqual(t.append.call_args[0][1], 'task/zz01ab')

    def test_recurrence(t) -> None:
        with t.subTest('a recurring task is rescheduled, not removed'):
            recurring = TaskNode(
                raw_index=1,
                indent=0,
                done=False,
                title='A recurring task',
                fields={
                    'P': '3',
                    'REPEAT': '7d',
                    'DUE': '2026-08-05',
                    'ID': 'rr01ab',
                },
                raw=REPEAT_LINE,
                note_indices=[2],
            )
            t.doc = t.document(OPEN_HEADING, REPEAT_LINE, NOTE_LINE)
            t.doc.tasks = [recurring]
            t.lookup.record = TaskRecord(t.path, t.doc, [recurring])

            complete(t.dir, 'rr01ab', TODAY)

            t.next_due.assert_called_once_with('7d', TODAY)
            t.assertEqual(
                t.doc.set_field.call_args_list,
                [
                    call(1, 'DUE', '2026-08-15'),
                    # It keeps the id it already carried.
                    call(1, 'ID', 'rr01ab'),
                ],
            )
            # The recurrence is the same task, so its note stays.
            t.assertEqual(
                t.doc.lines,
                [OPEN_HEADING, REPEAT_LINE, NOTE_LINE],
            )

        with t.subTest('the event records the reschedule beside the done'):
            payload = t.append.call_args[0][2]
            t.assertEqual(
                payload['delta'],
                {'done': [False, True], 'DUE': ['2026-08-05', '2026-08-15']},
            )

    def test_checklist_item(t) -> None:
        with t.subTest('a checklist item is logged under nothing'):
            item = TaskNode(
                raw_index=2,
                indent=2,
                done=False,
                title='A checklist item',
                fields={},
                raw=ITEM_LINE,
            )
            sibling = TaskNode(
                raw_index=3,
                indent=2,
                done=False,
                title='A subtask of it',
                fields={'LOE': '2'},
                raw=CHILD_LINE,
            )
            parent = TaskNode(
                raw_index=1,
                indent=0,
                done=False,
                title='A task',
                fields={'P': '4', 'ID': '9o71lx'},
                raw=TASK_LINE,
                children=[item, sibling],
            )
            t.doc = t.document(
                OPEN_HEADING,
                TASK_LINE,
                ITEM_LINE,
                CHILD_LINE,
            )
            t.doc.tasks = [parent]
            t.lookup.record = TaskRecord(t.path, t.doc, [parent, item])

            t.assertEqual(complete(t.dir, 'checklist', TODAY), [])
            t.log.open.assert_not_called()

        with t.subTest('its box is checked where it stands'):
            t.assertEqual(t.doc.lines[2], '  - [x] A checklist item')

        with t.subTest('and its event lands on the nearest stream that can'):
            t.append.assert_called_once()
            stream, payload = t.append.call_args[0][1:3]
            t.assertEqual(stream, 'task/9o71lx')
            t.assertEqual(payload['ancestry'], 'A task > A checklist item')


class ScratchTests(IsolatedTests):
    """Unit tests for battodo.mutate.scratch."""

    TARGETS = (*IsolatedTests.TARGETS, 'TaskSelection')

    TaskSelection: MagicMock

    def setUp(t) -> None:
        super().setUp()
        t.lookup = t.TaskSelection.return_value
        t.child = TaskNode(
            raw_index=4,
            indent=2,
            done=False,
            title='A subtask of it',
            fields={'LOE': '2'},
            raw=CHILD_LINE,
        )
        t.task = TaskNode(
            raw_index=2,
            indent=0,
            done=False,
            title='A task',
            fields={'P': '4', 'LOE': '8', 'ID': '9o71lx'},
            raw=TASK_LINE,
            children=[t.child],
            note_indices=[3],
        )
        t.doc = t.document(
            OPEN_HEADING,
            '',
            TASK_LINE,
            NOTE_LINE,
            CHILD_LINE,
            '',
            BARE_LINE,
        )
        t.doc.tasks = [t.task]
        t.lookup.record = TaskRecord(t.path, t.doc, [t.task])

    def test_block(t) -> None:
        with t.subTest('the task and everything under it are removed'):
            entries = scratch(t.dir, '9o71lx', TODAY)

            t.TaskSelection.assert_called_once_with(t.dir, '9o71lx')
            t.assertEqual(t.doc.lines, [OPEN_HEADING, '', BARE_LINE])

        with t.subTest('and no pair of blank lines is left behind'):
            blanks = [
                index
                for index, line in enumerate(t.doc.lines[:-1])
                if not line.strip() and not t.doc.lines[index + 1].strip()
            ]
            t.assertEqual(blanks, [])

        with t.subTest('which then goes to the file it came from'):
            t.path.write_text.assert_called_once_with(t.doc.text)

        with t.subTest('the log records the abandonment, once'):
            t.assertEqual(
                entries,
                ['2026-08-08 | a-list | SCRATCHED | A task [P:4] [LOE:8]'],
            )
            t.assertEqual(t.logged(), entries[0] + '\n')

        with t.subTest('one SCRATCHED event, on the task stream'):
            t.append.assert_called_once()
            stream, payload = t.append.call_args[0][1:3]
            t.assertEqual(stream, 'task/9o71lx')
            t.assertEqual(payload['delta'], {'removed': [False, True]})
            t.assertEqual(payload['ancestry'], 'A task')

    def test_log_fields(t) -> None:
        with t.subTest('a task carrying no SCHEMA field logs none'):
            t.task.fields = {'ID': '9o71lx'}

            t.assertEqual(
                scratch(t.dir, '9o71lx', TODAY),
                ['2026-08-08 | a-list | SCRATCHED | A task'],
            )

    def test_log_newline(t) -> None:
        with t.subTest('a log with no trailing newline gains one first'):
            t.log.read_text.return_value = '# Completed Tasks'

            entries = scratch(t.dir, '9o71lx', TODAY)

            t.assertEqual(t.logged(), '\n' + entries[0] + '\n')

    def test_log_absent(t) -> None:
        with t.subTest('a log that is not there yet is written from empty'):
            t.log.exists.return_value = False

            entries = scratch(t.dir, '9o71lx', TODAY)

            t.log.read_text.assert_not_called()
            t.assertEqual(t.logged(), entries[0] + '\n')

    def test_checklist_item(t) -> None:
        with t.subTest('a checklist item is not logged as work abandoned'):
            item = TaskNode(
                raw_index=2,
                indent=2,
                done=False,
                title='A checklist item',
                fields={},
                raw=ITEM_LINE,
            )
            parent = TaskNode(
                raw_index=1,
                indent=0,
                done=False,
                title='A task with no id',
                fields={'P': '2'},
                raw=BARE_LINE,
                children=[item],
            )
            t.doc = t.document(OPEN_HEADING, BARE_LINE, ITEM_LINE)
            t.doc.tasks = [parent]
            t.lookup.record = TaskRecord(t.path, t.doc, [parent, item])

            t.assertEqual(scratch(t.dir, 'checklist', TODAY), [])
            t.log.open.assert_not_called()

        with t.subTest('the ancestor that carries the stream is stamped'):
            t.doc.set_field.assert_called_once_with(1, 'ID', 'zz01ab')

        with t.subTest('and the event lands on that stream instead'):
            t.assertEqual(t.append.call_args[0][1], 'task/zz01ab')
