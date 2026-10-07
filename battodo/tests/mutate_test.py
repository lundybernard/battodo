from datetime import date
from io import TextIOWrapper
from pathlib import Path
from unittest import TestCase
from unittest.mock import (
    MagicMock,
    Mock,
    PropertyMock,
    call,
    create_autospec,
    patch,
    sentinel,
)

from ..mutate import (
    OPEN_HEADING,
    AddedLine,
    Addition,
    Backfill,
    Changeset,
    CompletedLog,
    Completion,
    Event,
    ListBackfill,
    ListError,
    LogEntry,
    NamedList,
    Scratch,
    SubtaskAddition,
    SuppliedFields,
    TaskNode,
    TodoDocument,
    Update,
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
# The source directory, the list a task lives in, and another list.
SOURCE = Path('/a-source')
LIST_PATH = SOURCE / 'a-list.md'
ANOTHER_PATH = SOURCE / 'another-list.md'
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


class AdditionTests(TestCase):
    """Unit tests for battodo.mutate.Addition."""

    def setUp(t) -> None:
        t.ad = Addition(
            SOURCE,
            'a-list',
            'A new task',
            {'TAGS': 'a-tag', 'P': '3'},
            TODAY,
        )

    @patch(f'{SRC}.Changeset', autospec=True)
    @patch.object(Addition, 'events', new_callable=PropertyMock)
    @patch.object(Addition, 'entries', new_callable=PropertyMock)
    @patch.object(Addition, 'text', new_callable=PropertyMock)
    def test_write(
        t,
        text: PropertyMock,
        entries: PropertyMock,
        events: PropertyMock,
        changeset: MagicMock,
    ) -> None:
        text.return_value = sentinel.text
        entries.return_value = sentinel.entries
        events.return_value = sentinel.events
        t.ad.path = LIST_PATH

        with t.subTest('the list, its log records and its events'):
            t.ad.write()

            changeset.assert_called_once_with(
                sentinel.text,
                sentinel.entries,
                sentinel.events,
                LIST_PATH,
                SOURCE,
            )
            changeset.return_value.write.assert_called_once_with()

        with t.subTest('a refused text: nothing else is read or written'):
            changeset.reset_mock()
            entries.reset_mock()
            text.side_effect = ValueError('refused')

            with t.assertRaises(ValueError):
                t.ad.write()

            entries.assert_not_called()
            changeset.assert_not_called()

    @patch(f'{SRC}.NamedList', autospec=True)
    def test_path(t, named_list: MagicMock) -> None:
        # Two reads: discovery reads every list in the source.
        ret = t.ad.path
        named_list.assert_called_once_with(SOURCE, 'a-list')
        t.assertIs(ret, named_list.return_value.path)

        again = t.ad.path
        t.assertIs(again, ret)
        named_list.assert_called_once_with(SOURCE, 'a-list')

    @patch.object(Addition, 'document', new_callable=PropertyMock)
    def test_text(t, document: PropertyMock) -> None:
        document.return_value = MagicMock(spec=['text'])
        ret = t.ad.text
        t.assertIs(ret, document.return_value.text)

    @patch(f'{SRC}.TodoDocument', autospec=True)
    @patch.object(Addition, 'index', new_callable=PropertyMock)
    @patch.object(Addition, 'written', new_callable=PropertyMock)
    def test_document(
        t,
        written: PropertyMock,
        index: PropertyMock,
        todo_document: MagicMock,
    ) -> None:
        written.return_value = sentinel.written
        index.return_value = 4
        doc = todo_document.return_value
        t.ad.parsed = MagicMock(spec=['text'])

        ret = t.ad.document

        # The bare line goes in last in Open, then its fields go on.
        todo_document.assert_called_once_with(t.ad.parsed.text)
        t.assertEqual(
            doc.method_calls,
            [
                call.insert(4, '- [ ] A new task'),
                call.set_fields(4, sentinel.written),
            ],
        )
        t.assertIs(ret, doc)

    @patch(f'{SRC}.TodoDocument', autospec=True)
    def test_parsed(t, todo_document: MagicMock) -> None:
        # Two reads: one read of the file answers every property.
        t.ad.path = MagicMock(spec=Path)

        ret = t.ad.parsed
        todo_document.assert_called_once_with(t.ad.path.read_text.return_value)
        t.assertIs(ret, todo_document.return_value)

        again = t.ad.parsed
        t.assertIs(again, ret)
        t.ad.path.read_text.assert_called_once_with()

    def test_index(t) -> None:
        t.ad.parsed = MagicMock(spec=['open_end'])
        t.ad.parsed.open_end = 9

        ret = t.ad.index

        t.assertEqual(ret, 9)

    @patch.object(Addition, 'index', new_callable=PropertyMock)
    @patch.object(Addition, 'document', new_callable=PropertyMock)
    def test_entry(t, document: PropertyMock, index: PropertyMock) -> None:
        document.return_value = MagicMock(spec=['lines'])
        document.return_value.lines = [OPEN_HEADING, 'the line as written']
        index.return_value = 1

        ret = t.ad.entry

        t.assertEqual(ret, 'the line as written')

    def test_entries(t) -> None:
        ret = t.ad.entries
        # An add logs no completed-log record.
        t.assertEqual(ret, [])

    @patch.object(Addition, 'supplied', new_callable=PropertyMock)
    def test_written(t, supplied: PropertyMock) -> None:
        supplied.return_value = MagicMock(spec=['ordered'])
        supplied.return_value.ordered = {'LOE': '5', 'TAGS': 'a-tag'}
        t.ad.task_id = 'zz01ab'

        ret = t.ad.written

        # The supplied fields as read, then the add date and the id.
        t.assertEqual(
            ret,
            {
                'LOE': '5',
                'TAGS': 'a-tag',
                'ADDED': '2026-08-08',
                'ID': 'zz01ab',
            },
        )

    @patch(f'{SRC}.SuppliedFields', autospec=True)
    def test_supplied(t, supplied_fields: MagicMock) -> None:
        ret = t.ad.supplied

        # The fields, read against the add date.
        supplied_fields.assert_called_once_with(
            {'TAGS': 'a-tag', 'P': '3'},
            TODAY,
        )
        t.assertIs(ret, supplied_fields.return_value)

    @patch(f'{SRC}.new_task_id', autospec=True)
    def test_task_id(t, new_task_id: MagicMock) -> None:
        # Two reads: an id drawn at random must name one task.
        ret = t.ad.task_id
        t.assertIs(ret, new_task_id.return_value)

        again = t.ad.task_id
        t.assertIs(again, ret)
        new_task_id.assert_called_once_with()

    @patch(f'{SRC}.AddedLine', autospec=True)
    @patch.object(Addition, 'written', new_callable=PropertyMock)
    @patch.object(Addition, 'entry', new_callable=PropertyMock)
    def test_events(
        t,
        entry: PropertyMock,
        written: PropertyMock,
        added_line: MagicMock,
    ) -> None:
        entry.return_value = 'the line as written'
        written.return_value = sentinel.written
        t.ad.task_id = 'zz01ab'

        ret = t.ad.events

        # One TaskAdded, on the stream of the new task.
        added_line.assert_called_once_with(
            'the line as written',
            sentinel.written,
        )
        t.assertEqual(
            ret,
            [
                Event(
                    'TaskAdded',
                    'task/zz01ab',
                    added_line.return_value.payload,
                ),
            ],
        )


class SubtaskAdditionTests(TestCase):
    """Unit tests for battodo.mutate.SubtaskAddition."""

    def setUp(t) -> None:
        t.parent = parent_node()
        t.task = named_task(t.parent)
        t.sa = SubtaskAddition(t.task, 'a-list', 'A new subtask', {'LOE': '2'})

    @patch(f'{SRC}.Changeset', autospec=True)
    @patch.object(SubtaskAddition, 'events', new_callable=PropertyMock)
    @patch.object(SubtaskAddition, 'entries', new_callable=PropertyMock)
    @patch.object(SubtaskAddition, 'text', new_callable=PropertyMock)
    def test_write(
        t,
        text: PropertyMock,
        entries: PropertyMock,
        events: PropertyMock,
        changeset: MagicMock,
    ) -> None:
        text.return_value = sentinel.text
        entries.return_value = sentinel.entries
        events.return_value = sentinel.events
        t.sa.path = LIST_PATH

        with t.subTest('the list, its log records and its events'):
            t.sa.write()

            changeset.assert_called_once_with(
                sentinel.text,
                sentinel.entries,
                sentinel.events,
                LIST_PATH,
                SOURCE,
            )
            changeset.return_value.write.assert_called_once_with()

        with t.subTest('a refused text: nothing else is read or written'):
            changeset.reset_mock()
            entries.reset_mock()
            text.side_effect = ValueError('refused')

            with t.assertRaises(ValueError):
                t.sa.write()

            entries.assert_not_called()
            changeset.assert_not_called()

    def test_source(t) -> None:
        ret = t.sa.source
        t.assertIs(ret, t.task.source)

    @patch(f'{SRC}.NamedList', autospec=True)
    def test_path(t, named_list: MagicMock) -> None:
        # Two reads: discovery reads every list in the source.
        ret = t.sa.path
        named_list.assert_called_once_with(SOURCE, 'a-list')
        t.assertIs(ret, named_list.return_value.path)

        again = t.sa.path
        t.assertIs(again, ret)
        named_list.assert_called_once_with(SOURCE, 'a-list')

    @patch.object(SubtaskAddition, 'document', new_callable=PropertyMock)
    def test_text(t, document: PropertyMock) -> None:
        document.return_value = MagicMock(spec=['text'])
        ret = t.sa.text
        t.assertIs(ret, document.return_value.text)

    @patch(f'{SRC}.TodoDocument', autospec=True)
    @patch.object(SubtaskAddition, 'indent', new_callable=PropertyMock)
    @patch.object(SubtaskAddition, 'index', new_callable=PropertyMock)
    @patch.object(SubtaskAddition, 'node', new_callable=PropertyMock)
    @patch.object(SubtaskAddition, 'stamped', new_callable=PropertyMock)
    @patch.object(SubtaskAddition, 'written', new_callable=PropertyMock)
    def test_document(
        t,
        written: PropertyMock,
        stamped: PropertyMock,
        node: PropertyMock,
        index: PropertyMock,
        indent: PropertyMock,
        todo_document: MagicMock,
    ) -> None:
        written.return_value = sentinel.written
        stamped.return_value = False
        node.return_value = t.parent
        index.return_value = 4
        indent.return_value = '  '
        doc = todo_document.return_value
        t.sa.path = LIST_PATH
        t.sa.parent_id = 'pp02cd'

        with t.subTest('the subtask goes in at its index, its fields on it'):
            ret = t.sa.document

            todo_document.assert_called_once_with(t.task.doc.text)
            t.assertEqual(
                doc.method_calls,
                [
                    call.insert(4, '  - [ ] A new subtask'),
                    call.set_fields(4, sentinel.written),
                ],
            )
            t.assertIs(ret, doc)

        with t.subTest('a parent with no id is stamped first'):
            doc.reset_mock()
            stamped.return_value = True

            _ = t.sa.document

            t.assertEqual(
                doc.method_calls[0],
                call.set_field(1, 'ID', 'pp02cd'),
            )

        with t.subTest('a parent in another list is refused'):
            t.sa.path = ANOTHER_PATH

            with t.assertRaises(ValueError) as caught:
                _ = t.sa.document

            t.assertEqual(
                str(caught.exception),
                "'a selector' names a task in a-list.md, not another-list.md",
            )

        with t.subTest('the fields are checked before the parent'):
            node.reset_mock()
            written.side_effect = ValueError('a field')

            with t.assertRaisesRegex(ValueError, 'a field'):
                _ = t.sa.document

            node.assert_not_called()

    @patch.object(SubtaskAddition, 'supplied', new_callable=PropertyMock)
    def test_written(t, supplied: PropertyMock) -> None:
        fields = MagicMock(spec=['refuse_root_fields', 'ordered'])
        fields.ordered = {'LOE': '5', 'TAGS': 'a-tag'}
        supplied.return_value = fields
        t.sa.task_id = 'cc03ef'

        with t.subTest('the supplied fields as read, then the id'):
            ret = t.sa.written

            fields.refuse_root_fields.assert_called_once_with()
            t.assertEqual(ret, {'LOE': '5', 'TAGS': 'a-tag', 'ID': 'cc03ef'})

        with t.subTest('a field the top-level task owns is refused first'):
            refused = MagicMock(spec=['refuse_root_fields', 'ordered'])
            refused.refuse_root_fields.side_effect = ValueError('a P field')
            ordered = PropertyMock(side_effect=ValueError('a value'))
            type(refused).ordered = ordered
            supplied.return_value = refused

            with t.assertRaisesRegex(ValueError, 'a P field'):
                _ = t.sa.written

            ordered.assert_not_called()

    @patch(f'{SRC}.SuppliedFields', autospec=True)
    def test_supplied(t, supplied_fields: MagicMock) -> None:
        ret = t.sa.supplied
        # The fields, read against the day of the parent.
        supplied_fields.assert_called_once_with({'LOE': '2'}, TODAY)
        t.assertIs(ret, supplied_fields.return_value)

    @patch.object(SubtaskAddition, 'node', new_callable=PropertyMock)
    def test_stamped(t, node: PropertyMock) -> None:
        with t.subTest('a parent with an id is not stamped'):
            node.return_value = t.parent
            ret = t.sa.stamped
            t.assertFalse(ret)

        with t.subTest('a parent with no id is'):
            node.return_value = bare_node()
            ret = t.sa.stamped
            t.assertTrue(ret)

    @patch.object(TaskNode, 'refuse_checklist_item', autospec=True)
    def test_node(t, refuse_checklist_item: MagicMock) -> None:
        with t.subTest('the parent the selector names'):
            ret = t.sa.node
            refuse_checklist_item.assert_called_once_with(t.parent)
            t.assertIs(ret, t.parent)

        with t.subTest('a parent that is a checklist item is refused'):
            refuse_checklist_item.side_effect = ValueError('a checklist item')
            with t.assertRaisesRegex(ValueError, 'a checklist item'):
                _ = t.sa.node

    @patch(f'{SRC}.new_task_id', autospec=True)
    @patch.object(SubtaskAddition, 'node', new_callable=PropertyMock)
    def test_parent_id(
        t,
        node: PropertyMock,
        new_task_id: MagicMock,
    ) -> None:
        with t.subTest('the id the parent carries'):
            node.return_value = t.parent
            ret = t.sa.parent_id
            t.assertEqual(ret, '9o71lx')

        with t.subTest('a new one, drawn once, where it carries none'):
            # Two reads: an id drawn at random must name one task.
            t.sa = SubtaskAddition(t.task, 'a-list', 'X', {})
            node.return_value = bare_node()

            ret = t.sa.parent_id
            t.assertIs(ret, new_task_id.return_value)

            again = t.sa.parent_id
            t.assertIs(again, ret)
            new_task_id.assert_called_once_with()

    @patch.object(SubtaskAddition, 'node', new_callable=PropertyMock)
    def test_index(t, node: PropertyMock) -> None:
        node.return_value = t.parent
        ret = t.sa.index
        # After the parent, its note and its child.
        t.assertEqual(ret, 4)

    @patch.object(SubtaskAddition, 'node', new_callable=PropertyMock)
    def test_indent(t, node: PropertyMock) -> None:
        with t.subTest('one level under a top-level task'):
            node.return_value = t.parent
            ret = t.sa.indent
            t.assertEqual(ret, '  ')

        with t.subTest('one level under a subtask'):
            node.return_value = child_node()
            ret = t.sa.indent
            t.assertEqual(ret, '    ')

    @patch(f'{SRC}.new_task_id', autospec=True)
    def test_task_id(t, new_task_id: MagicMock) -> None:
        # Two reads: an id drawn at random must name one task.
        ret = t.sa.task_id
        t.assertIs(ret, new_task_id.return_value)

        again = t.sa.task_id
        t.assertIs(again, ret)
        new_task_id.assert_called_once_with()

    @patch.object(SubtaskAddition, 'index', new_callable=PropertyMock)
    @patch.object(SubtaskAddition, 'document', new_callable=PropertyMock)
    def test_entry(t, document: PropertyMock, index: PropertyMock) -> None:
        document.return_value = MagicMock(spec=['lines'])
        document.return_value.lines = [OPEN_HEADING, 'the line as written']
        index.return_value = 1

        ret = t.sa.entry

        t.assertEqual(ret, 'the line as written')

    def test_entries(t) -> None:
        ret = t.sa.entries
        # An add logs no completed-log record.
        t.assertEqual(ret, [])

    @patch(f'{SRC}.AddedLine', autospec=True)
    @patch.object(SubtaskAddition, 'stamp', new_callable=PropertyMock)
    @patch.object(SubtaskAddition, 'stamped', new_callable=PropertyMock)
    @patch.object(SubtaskAddition, 'written', new_callable=PropertyMock)
    @patch.object(SubtaskAddition, 'entry', new_callable=PropertyMock)
    def test_events(
        t,
        entry: PropertyMock,
        written: PropertyMock,
        stamped: PropertyMock,
        stamp: PropertyMock,
        added_line: MagicMock,
    ) -> None:
        entry.return_value = 'the line as written'
        written.return_value = sentinel.written
        stamped.return_value = False
        stamp.return_value = sentinel.stamp
        added_line.return_value.payload = {'delta': sentinel.delta}
        t.sa.task_id = 'cc03ef'
        t.sa.parent_id = '9o71lx'

        with t.subTest('one TaskAdded, which names the parent'):
            ret = t.sa.events

            added_line.assert_called_once_with(
                'the line as written',
                sentinel.written,
            )
            t.assertEqual(
                ret,
                [
                    Event(
                        'TaskAdded',
                        'task/cc03ef',
                        {'delta': sentinel.delta, 'parent': '9o71lx'},
                    ),
                ],
            )

        with t.subTest('the stamp of a parent with no id goes first'):
            stamped.return_value = True

            ret = t.sa.events

            t.assertEqual(len(ret), 2)
            t.assertIs(ret[0], sentinel.stamp)

    @patch.object(TaskNode, 'snapshot', new_callable=PropertyMock)
    @patch.object(SubtaskAddition, 'node', new_callable=PropertyMock)
    def test_stamp(t, node: PropertyMock, snapshot: PropertyMock) -> None:
        node.return_value = bare_node()
        snapshot.return_value = sentinel.snapshot
        t.sa.parent_id = 'pp02cd'

        ret = t.sa.stamp

        t.assertEqual(
            ret,
            Event(
                'TaskUpdated',
                'task/pp02cd',
                {
                    'delta': {'ID': [None, 'pp02cd']},
                    'snapshot': sentinel.snapshot,
                },
            ),
        )


class UpdateTests(TestCase):
    """Unit tests for battodo.mutate.Update."""

    def setUp(t) -> None:
        t.parent = parent_node()
        t.task = named_task(t.parent)
        t.up = Update(t.task, {'P': '5'}, title='A new title')

    @patch(f'{SRC}.Changeset', autospec=True)
    @patch.object(Update, 'events', new_callable=PropertyMock)
    @patch.object(Update, 'entries', new_callable=PropertyMock)
    @patch.object(Update, 'text', new_callable=PropertyMock)
    def test_write(
        t,
        text: PropertyMock,
        entries: PropertyMock,
        events: PropertyMock,
        changeset: MagicMock,
    ) -> None:
        text.return_value = sentinel.text
        entries.return_value = sentinel.entries
        events.return_value = sentinel.events

        with t.subTest('the list, its log records and its events'):
            t.up.write()

            changeset.assert_called_once_with(
                sentinel.text,
                sentinel.entries,
                sentinel.events,
                LIST_PATH,
                SOURCE,
            )
            changeset.return_value.write.assert_called_once_with()

        with t.subTest('a refused text: nothing else is read or written'):
            changeset.reset_mock()
            entries.reset_mock()
            text.side_effect = ValueError('refused')

            with t.assertRaises(ValueError):
                t.up.write()

            entries.assert_not_called()
            changeset.assert_not_called()

    def test_source(t) -> None:
        ret = t.up.source
        t.assertIs(ret, t.task.source)

    def test_path(t) -> None:
        ret = t.up.path
        t.assertIs(ret, t.task.path)

    @patch.object(Update, 'document', new_callable=PropertyMock)
    def test_text(t, document: PropertyMock) -> None:
        document.return_value = MagicMock(spec=['text'])
        ret = t.up.text
        t.assertIs(ret, document.return_value.text)

    @patch(f'{SRC}.TodoDocument', autospec=True)
    @patch.object(Update, 'node', new_callable=PropertyMock)
    @patch.object(Update, 'written', new_callable=PropertyMock)
    def test_document(
        t,
        written: PropertyMock,
        node: PropertyMock,
        todo_document: MagicMock,
    ) -> None:
        written.return_value = sentinel.written
        node.return_value = t.parent
        doc = todo_document.return_value

        with t.subTest('the fields, then the new title, on the task line'):
            ret = t.up.document

            todo_document.assert_called_once_with(t.task.doc.text)
            t.assertEqual(
                doc.method_calls,
                [
                    call.set_fields(1, sentinel.written),
                    call.set_title(1, 'A new title'),
                ],
            )
            t.assertIs(ret, doc)

        with t.subTest('a title left off is not written'):
            doc.reset_mock()
            t.up.title = None

            _ = t.up.document

            t.assertEqual(
                doc.method_calls,
                [call.set_fields(1, sentinel.written)],
            )

    @patch.object(Update, 'node', new_callable=PropertyMock)
    @patch.object(Update, 'checked', new_callable=PropertyMock)
    def test_written(t, checked: PropertyMock, node: PropertyMock) -> None:
        checked.return_value = {'P': '5'}
        t.up.task_id = 'zz01ab'

        with t.subTest('the named fields, on a task that has an id'):
            node.return_value = t.parent
            ret = t.up.written
            t.assertEqual(ret, {'P': '5'})

        with t.subTest('and an id, on a task that has none'):
            node.return_value = bare_node()
            ret = t.up.written
            t.assertEqual(ret, {'P': '5', 'ID': 'zz01ab'})

    @patch.object(TaskNode, 'refuse_checklist_item', autospec=True)
    @patch.object(Update, 'supplied', new_callable=PropertyMock)
    def test_node(
        t,
        supplied: PropertyMock,
        refuse_checklist_item: MagicMock,
    ) -> None:
        supplied.return_value = MagicMock(spec=['refuse_root_fields'])
        refuse_root_fields = supplied.return_value.refuse_root_fields

        with t.subTest('the task the selector names'):
            ret = t.up.node

            refuse_checklist_item.assert_called_once_with(t.parent)
            refuse_root_fields.assert_not_called()
            t.assertIs(ret, t.parent)

        with t.subTest('a subtask takes no field the top-level task owns'):
            t.task.ancestry = [t.parent, child_node()]
            t.task.node = t.task.ancestry[-1]

            ret = t.up.node

            refuse_root_fields.assert_called_once_with()
            t.assertIs(ret, t.task.node)

        with t.subTest('a checklist item is refused before its fields'):
            refuse_root_fields.reset_mock()
            refuse_checklist_item.side_effect = ValueError('a checklist item')

            with t.assertRaisesRegex(ValueError, 'a checklist item'):
                _ = t.up.node

            refuse_root_fields.assert_not_called()

    @patch.object(Update, 'supplied', new_callable=PropertyMock)
    def test_checked(t, supplied: PropertyMock) -> None:
        supplied.return_value = MagicMock(spec=['checked'])
        supplied.return_value.checked = sentinel.checked

        with t.subTest('the named fields, read'):
            ret = t.up.checked
            t.assertIs(ret, sentinel.checked)

        with t.subTest('a title alone names no field'):
            t.up.fields = {}
            ret = t.up.checked
            t.assertIs(ret, sentinel.checked)

        with t.subTest('neither a field nor a title, before any value'):
            supplied.reset_mock()
            t.up = Update(t.task, {})

            with t.assertRaises(ValueError) as caught:
                _ = t.up.checked

            t.assertEqual(
                str(caught.exception),
                'nothing to update: name a field or a title',
            )
            supplied.assert_not_called()

    @patch(f'{SRC}.SuppliedFields', autospec=True)
    def test_supplied(t, supplied_fields: MagicMock) -> None:
        ret = t.up.supplied
        # The fields, read against the day of the task.
        supplied_fields.assert_called_once_with({'P': '5'}, TODAY)
        t.assertIs(ret, supplied_fields.return_value)

    @patch(f'{SRC}.new_task_id', autospec=True)
    @patch.object(Update, 'node', new_callable=PropertyMock)
    def test_task_id(t, node: PropertyMock, new_task_id: MagicMock) -> None:
        with t.subTest('the id the task carries'):
            node.return_value = t.parent
            ret = t.up.task_id
            t.assertEqual(ret, '9o71lx')

        with t.subTest('a new one, drawn once, where it carries none'):
            # Two reads: an id drawn at random must name one task.
            t.up = Update(t.task, {'P': '5'})
            node.return_value = bare_node()

            ret = t.up.task_id
            t.assertIs(ret, new_task_id.return_value)

            again = t.up.task_id
            t.assertIs(again, ret)
            new_task_id.assert_called_once_with()

    def test_nested(t) -> None:
        with t.subTest('a top-level task is not nested'):
            ret = t.up.nested
            t.assertFalse(ret)

        with t.subTest('a subtask is, at any depth'):
            t.task.ancestry = [t.parent, child_node(), grandchild_node()]
            ret = t.up.nested
            t.assertTrue(ret)

    @patch.object(Update, 'node', new_callable=PropertyMock)
    @patch.object(Update, 'document', new_callable=PropertyMock)
    def test_entry(t, document: PropertyMock, node: PropertyMock) -> None:
        document.return_value = MagicMock(spec=['lines'])
        document.return_value.lines = [OPEN_HEADING, 'the line as written']
        node.return_value = t.parent

        ret = t.up.entry

        t.assertEqual(ret, 'the line as written')

    def test_entries(t) -> None:
        ret = t.up.entries
        # An update logs no completed-log record.
        t.assertEqual(ret, [])

    @patch.object(Update, 'payload', new_callable=PropertyMock)
    def test_events(t, payload: PropertyMock) -> None:
        payload.return_value = sentinel.payload
        t.up.task_id = '9o71lx'

        ret = t.up.events

        t.assertEqual(
            ret,
            [Event('TaskUpdated', 'task/9o71lx', sentinel.payload)],
        )

    @patch.object(TaskNode, 'snapshot', new_callable=PropertyMock)
    @patch.object(Update, 'ancestry', new_callable=PropertyMock)
    @patch.object(Update, 'node', new_callable=PropertyMock)
    @patch.object(Update, 'delta', new_callable=PropertyMock)
    def test_payload(
        t,
        delta: PropertyMock,
        node: PropertyMock,
        ancestry: PropertyMock,
        snapshot: PropertyMock,
    ) -> None:
        delta.return_value = sentinel.delta
        node.return_value = t.parent
        ancestry.return_value = MagicMock(spec=['path'])
        ancestry.return_value.path = 'a path'
        snapshot.return_value = sentinel.snapshot

        with t.subTest('the delta, and the state it changed from'):
            ret = t.up.payload
            t.assertEqual(
                ret,
                {'delta': sentinel.delta, 'snapshot': sentinel.snapshot},
            )

        with t.subTest('a subtask records where it sits'):
            t.task.ancestry = [t.parent, child_node()]
            ret = t.up.payload
            t.assertEqual(ret['ancestry'], 'a path')

    @patch.object(Update, 'node', new_callable=PropertyMock)
    @patch.object(Update, 'written', new_callable=PropertyMock)
    def test_delta(t, written: PropertyMock, node: PropertyMock) -> None:
        written.return_value = {'P': '5', 'DUE': '2026-09-01'}
        node.return_value = t.parent

        with t.subTest('each field written against the one it replaced'):
            ret = t.up.delta
            t.assertEqual(
                ret,
                {
                    'P': ['4', '5'],
                    'DUE': [None, '2026-09-01'],
                    'title': ['A task', 'A new title'],
                },
            )

        with t.subTest('a title left off names no title change'):
            t.up.title = None
            ret = t.up.delta
            t.assertNotIn('title', ret)

    @patch(f'{SRC}.Ancestry', autospec=True)
    def test_ancestry(t, ancestry: MagicMock) -> None:
        ret = t.up.ancestry
        ancestry.assert_called_once_with(t.task.ancestry)
        t.assertIs(ret, ancestry.return_value)


class CompletionTests(TestCase):
    """Unit tests for battodo.mutate.Completion."""

    def setUp(t) -> None:
        t.child = child_node()
        t.parent = parent_node()
        t.parent.children = [t.child, done_child_node()]
        t.task = named_task(t.parent, t.child)
        t.co = Completion(t.task)

    @patch(f'{SRC}.Changeset', autospec=True)
    @patch.object(Completion, 'events', new_callable=PropertyMock)
    @patch.object(Completion, 'entries', new_callable=PropertyMock)
    @patch.object(Completion, 'text', new_callable=PropertyMock)
    def test_write(
        t,
        text: PropertyMock,
        entries: PropertyMock,
        events: PropertyMock,
        changeset: MagicMock,
    ) -> None:
        text.return_value = sentinel.text
        entries.return_value = sentinel.entries
        events.return_value = sentinel.events

        with t.subTest('the list, its log records and its events'):
            t.co.write()

            changeset.assert_called_once_with(
                sentinel.text,
                sentinel.entries,
                sentinel.events,
                LIST_PATH,
                SOURCE,
            )
            changeset.return_value.write.assert_called_once_with()

        with t.subTest('a refused text: nothing else is read or written'):
            changeset.reset_mock()
            entries.reset_mock()
            text.side_effect = ValueError('refused')

            with t.assertRaises(ValueError):
                t.co.write()

            entries.assert_not_called()
            changeset.assert_not_called()

    def test_source(t) -> None:
        ret = t.co.source
        t.assertIs(ret, t.task.source)

    def test_path(t) -> None:
        ret = t.co.path
        t.assertIs(ret, t.task.path)

    @patch.object(Completion, 'document', new_callable=PropertyMock)
    def test_text(t, document: PropertyMock) -> None:
        document.return_value = MagicMock(spec=['text'])
        ret = t.co.text
        t.assertIs(ret, document.return_value.text)

    @patch(f'{SRC}.TodoDocument', autospec=True)
    @patch.object(Completion, 'dropped', new_callable=PropertyMock)
    @patch.object(Completion, 'checked_off', new_callable=PropertyMock)
    @patch.object(Completion, 'stamps', new_callable=PropertyMock)
    def test_document(
        t,
        stamps: PropertyMock,
        checked_off: PropertyMock,
        dropped: PropertyMock,
        todo_document: MagicMock,
    ) -> None:
        stamps.return_value = {3: {'ID': 'zz01ab'}, 1: {'ID': '9o71lx'}}
        checked_off.return_value = [3, 1]
        dropped.return_value = {5}
        doc = todo_document.return_value

        ret = t.co.document

        # Stamped, then checked off, then the dropped lines go.
        todo_document.assert_called_once_with(t.task.doc.text)
        t.assertEqual(
            doc.method_calls,
            [
                call.set_fields(3, {'ID': 'zz01ab'}),
                call.set_fields(1, {'ID': '9o71lx'}),
                call.mark_done(3),
                call.mark_done(1),
                call.drop({5}),
            ],
        )
        t.assertIs(ret, doc)

    @patch.object(Completion, 'rescheduled', new_callable=PropertyMock)
    @patch.object(Completion, 'root_done', new_callable=PropertyMock)
    def test_stamps(
        t,
        root_done: PropertyMock,
        rescheduled: PropertyMock,
    ) -> None:
        t.co.ids = {3: 'zz01ab', 1: '9o71lx'}

        with t.subTest('a block that stays: each stream gains its id'):
            root_done.return_value = False
            ret = t.co.stamps
            t.assertEqual(ret, {3: {'ID': 'zz01ab'}, 1: {'ID': '9o71lx'}})

        with t.subTest('a finished block that goes: nothing'):
            root_done.return_value = True
            rescheduled.return_value = None

            ret = t.co.stamps

            t.assertEqual(ret, {})

        with t.subTest('a recurrence: its next due date, and its id'):
            rescheduled.return_value = date(2026, 8, 15)

            ret = t.co.stamps

            t.assertEqual(ret, {1: {'DUE': '2026-08-15', 'ID': '9o71lx'}})

    @patch.object(Completion, 'ancestries', new_callable=PropertyMock)
    @patch.object(Completion, 'root_done', new_callable=PropertyMock)
    def test_checked_off(
        t,
        root_done: PropertyMock,
        ancestries: PropertyMock,
    ) -> None:
        ancestries.return_value = [
            ancestry_of(t.parent, t.child),
            ancestry_of(t.parent),
        ]

        with t.subTest('a block that stays: each completed task'):
            root_done.return_value = False
            ret = t.co.checked_off
            t.assertEqual(ret, [3, 1])

        with t.subTest('a finished block: none, as the block goes'):
            root_done.return_value = True
            ret = t.co.checked_off
            t.assertEqual(ret, [])

    @patch.object(Completion, 'rescheduled', new_callable=PropertyMock)
    @patch.object(Completion, 'root_done', new_callable=PropertyMock)
    def test_dropped(
        t,
        root_done: PropertyMock,
        rescheduled: PropertyMock,
    ) -> None:
        with t.subTest('a block that stays: nothing'):
            root_done.return_value = False
            ret = t.co.dropped
            t.assertEqual(ret, set())

        with t.subTest('a finished block: every line of it'):
            root_done.return_value = True
            rescheduled.return_value = None

            ret = t.co.dropped

            t.assertEqual(ret, {1, 2, 3, 4})

        with t.subTest('a recurrence: its children, not it or its notes'):
            rescheduled.return_value = date(2026, 8, 15)

            ret = t.co.dropped

            t.assertEqual(ret, {3, 4})

    @patch.object(Completion, 'ancestries', new_callable=PropertyMock)
    def test_root_done(t, ancestries: PropertyMock) -> None:
        with t.subTest('a cascade that ends below the top level'):
            ancestries.return_value = [ancestry_of(t.parent, t.child)]
            ret = t.co.root_done
            t.assertFalse(ret)

        with t.subTest('one that reaches it'):
            ancestries.return_value = [
                ancestry_of(t.parent, t.child),
                ancestry_of(t.parent),
            ]

            ret = t.co.root_done

            t.assertTrue(ret)

    @patch(f'{SRC}.new_task_id', autospec=True)
    @patch.object(Completion, 'ancestries', new_callable=PropertyMock)
    def test_ids(t, ancestries: PropertyMock, new_task_id: MagicMock) -> None:
        new_task_id.return_value = 'zz01ab'

        with t.subTest('a stream keeps its id; one with none is given one'):
            # A checklist item lands on its parent's stream.
            ancestries.return_value = [
                ancestry_of(t.parent, checklist_node(), stream=t.parent),
                ancestry_of(t.parent, t.child),
            ]

            ret = t.co.ids

            t.assertEqual(ret, {1: '9o71lx', 3: 'zz01ab'})

        with t.subTest('a new id is drawn once, however often it is read'):
            # Two reads: an id drawn at random must name one task.
            new_task_id.reset_mock()
            t.co = Completion(t.task)
            bare = bare_node()
            ancestries.return_value = [
                ancestry_of(bare, checklist_node(), stream=bare),
                ancestry_of(bare),
            ]

            ret = t.co.ids
            t.assertEqual(ret, {1: 'zz01ab'})

            again = t.co.ids
            t.assertIs(again, ret)
            new_task_id.assert_called_once_with()

    @patch(f'{SRC}.next_due', autospec=True)
    @patch.object(Completion, 'root_done', new_callable=PropertyMock)
    def test_rescheduled(
        t,
        root_done: PropertyMock,
        next_due: MagicMock,
    ) -> None:
        t.parent.fields = {'P': '3', 'REPEAT': '7d', 'ID': '9o71lx'}

        with t.subTest('a finished recurring task, against the day'):
            root_done.return_value = True

            ret = t.co.rescheduled

            next_due.assert_called_once_with('7d', TODAY)
            t.assertIs(ret, next_due.return_value)

        with t.subTest('none while the top-level task stays open'):
            root_done.return_value = False
            ret = t.co.rescheduled
            t.assertIsNone(ret)

        with t.subTest('none for a task that does not repeat'):
            root_done.return_value = True
            t.parent.fields = {'P': '3'}

            ret = t.co.rescheduled

            t.assertIsNone(ret)

    def test_root(t) -> None:
        ret = t.co.root
        t.assertIs(ret, t.parent)

    @patch(f'{SRC}.Ancestry', autospec=True)
    def test_ancestries(t, ancestry: MagicMock) -> None:
        # Each ancestry stands in as the tuple of the tasks it holds.
        ancestry.side_effect = tuple

        with t.subTest('an open sibling stops the cascade'):
            t.parent.children[1].done = False
            ret = t.co.ancestries
            t.assertEqual(ret, [(t.parent, t.child)])

        with t.subTest('the last open child completes its parent'):
            t.parent.children[1].done = True
            ret = t.co.ancestries
            t.assertEqual(ret, [(t.parent, t.child), (t.parent,)])

        with t.subTest('and that may complete its own parent, deepest first'):
            below = grandchild_node()
            t.child.children = [below]
            t.task.ancestry = [t.parent, t.child, below]

            ret = t.co.ancestries

            t.assertEqual(
                ret,
                [(t.parent, t.child, below), (t.parent, t.child), (t.parent,)],
            )

    @patch(f'{SRC}.LogEntry', autospec=True)
    @patch.object(Completion, 'ancestries', new_callable=PropertyMock)
    def test_entries(
        t, ancestries: PropertyMock, log_entry: MagicMock
    ) -> None:
        log_entry.return_value.text = 'a record'
        below, top = ancestry_of(t.parent, t.child), ancestry_of(t.parent)

        with t.subTest('one record a completion, deepest first'):
            ancestries.return_value = [below, top]

            ret = t.co.entries

            t.assertEqual(
                log_entry.call_args_list,
                [
                    call(LIST_PATH, below, 'DONE', TODAY),
                    call(LIST_PATH, top, 'DONE', TODAY),
                ],
            )
            t.assertEqual(ret, ['a record', 'a record'])

        with t.subTest('a checklist item is not logged'):
            log_entry.reset_mock()
            ancestries.return_value = [ancestry_of(t.parent, checklist_node())]

            ret = t.co.entries

            log_entry.assert_not_called()
            t.assertEqual(ret, [])

    @patch.object(TaskNode, 'snapshot', new_callable=PropertyMock)
    @patch.object(Completion, 'rescheduled', new_callable=PropertyMock)
    @patch.object(Completion, 'ancestries', new_callable=PropertyMock)
    def test_events(
        t,
        ancestries: PropertyMock,
        rescheduled: PropertyMock,
        snapshot: PropertyMock,
    ) -> None:
        ancestries.return_value = [
            ancestry_of(t.parent, t.child, path='a path to the subtask'),
            ancestry_of(t.parent, path='a path to the task'),
        ]
        rescheduled.return_value = None
        t.co.ids = {3: 'zz01ab', 1: '9o71lx'}

        with t.subTest('one TaskCompleted a completion, deepest first'):
            snapshot.side_effect = [sentinel.subtask, sentinel.task]

            ret = t.co.events

            t.assertEqual(
                ret,
                [
                    Event(
                        'TaskCompleted',
                        'task/zz01ab',
                        {
                            'delta': {'done': [False, True]},
                            'snapshot': sentinel.subtask,
                            'ancestry': 'a path to the subtask',
                        },
                    ),
                    Event(
                        'TaskCompleted',
                        'task/9o71lx',
                        {
                            'delta': {'done': [False, True]},
                            'snapshot': sentinel.task,
                            'ancestry': 'a path to the task',
                        },
                    ),
                ],
            )

        with t.subTest('a recurrence records its new due date too'):
            snapshot.side_effect = [sentinel.subtask, sentinel.task]
            rescheduled.return_value = date(2026, 8, 15)

            ret = t.co.events

            t.assertEqual(
                ret[1].payload['delta'],
                {'done': [False, True], 'DUE': [None, '2026-08-15']},
            )


class ScratchTests(TestCase):
    """Unit tests for battodo.mutate.Scratch."""

    def setUp(t) -> None:
        t.parent = parent_node()
        t.task = named_task(t.parent)
        t.sc = Scratch(t.task)

    @patch(f'{SRC}.Changeset', autospec=True)
    @patch.object(Scratch, 'events', new_callable=PropertyMock)
    @patch.object(Scratch, 'entries', new_callable=PropertyMock)
    @patch.object(Scratch, 'text', new_callable=PropertyMock)
    def test_write(
        t,
        text: PropertyMock,
        entries: PropertyMock,
        events: PropertyMock,
        changeset: MagicMock,
    ) -> None:
        text.return_value = sentinel.text
        entries.return_value = sentinel.entries
        events.return_value = sentinel.events

        with t.subTest('the list, its log records and its events'):
            t.sc.write()

            changeset.assert_called_once_with(
                sentinel.text,
                sentinel.entries,
                sentinel.events,
                LIST_PATH,
                SOURCE,
            )
            changeset.return_value.write.assert_called_once_with()

        with t.subTest('a refused text: nothing else is read or written'):
            changeset.reset_mock()
            entries.reset_mock()
            text.side_effect = ValueError('refused')

            with t.assertRaises(ValueError):
                t.sc.write()

            entries.assert_not_called()
            changeset.assert_not_called()

    def test_source(t) -> None:
        ret = t.sc.source
        t.assertIs(ret, t.task.source)

    def test_path(t) -> None:
        ret = t.sc.path
        t.assertIs(ret, t.task.path)

    @patch.object(Scratch, 'document', new_callable=PropertyMock)
    def test_text(t, document: PropertyMock) -> None:
        document.return_value = MagicMock(spec=['text'])
        ret = t.sc.text
        t.assertIs(ret, document.return_value.text)

    @patch(f'{SRC}.TodoDocument', autospec=True)
    @patch.object(Scratch, 'stream', new_callable=PropertyMock)
    def test_document(
        t,
        stream: PropertyMock,
        todo_document: MagicMock,
    ) -> None:
        doc = todo_document.return_value

        with t.subTest('the whole block goes'):
            stream.return_value = t.parent

            ret = t.sc.document

            todo_document.assert_called_once_with(t.task.doc.text)
            t.assertEqual(doc.method_calls, [call.drop({1, 2, 3})])
            t.assertIs(ret, doc)

        with t.subTest('a checklist item: its stream task is stamped'):
            doc.reset_mock()
            t.task.node = checklist_node()
            t.sc.stream_id = 'zz01ab'

            _ = t.sc.document

            t.assertEqual(
                doc.method_calls,
                [call.set_field(1, 'ID', 'zz01ab'), call.drop({3})],
            )

    @patch.object(Scratch, 'ancestry', new_callable=PropertyMock)
    def test_stream(t, ancestry: PropertyMock) -> None:
        ancestry.return_value = MagicMock(spec=['stream'])
        ancestry.return_value.stream = sentinel.stream

        ret = t.sc.stream

        t.assertIs(ret, sentinel.stream)

    @patch(f'{SRC}.Ancestry', autospec=True)
    def test_ancestry(t, ancestry: MagicMock) -> None:
        ret = t.sc.ancestry
        ancestry.assert_called_once_with(t.task.ancestry)
        t.assertIs(ret, ancestry.return_value)

    def test_node(t) -> None:
        ret = t.sc.node
        t.assertIs(ret, t.parent)

    @patch(f'{SRC}.new_task_id', autospec=True)
    @patch.object(Scratch, 'stream', new_callable=PropertyMock)
    def test_stream_id(
        t,
        stream: PropertyMock,
        new_task_id: MagicMock,
    ) -> None:
        with t.subTest('the id the stream task carries'):
            stream.return_value = t.parent
            ret = t.sc.stream_id
            t.assertEqual(ret, '9o71lx')

        with t.subTest('a new one, drawn once, where it carries none'):
            # Two reads: an id drawn at random must name one task.
            t.sc = Scratch(t.task)
            stream.return_value = bare_node()

            ret = t.sc.stream_id
            t.assertIs(ret, new_task_id.return_value)

            again = t.sc.stream_id
            t.assertIs(again, ret)
            new_task_id.assert_called_once_with()

    @patch(f'{SRC}.LogEntry', autospec=True)
    @patch.object(Scratch, 'ancestry', new_callable=PropertyMock)
    def test_entries(t, ancestry: PropertyMock, log_entry: MagicMock) -> None:
        ancestry.return_value = sentinel.ancestry

        with t.subTest('one SCRATCHED record'):
            ret = t.sc.entries

            log_entry.assert_called_once_with(
                LIST_PATH,
                sentinel.ancestry,
                'SCRATCHED',
                TODAY,
            )
            t.assertEqual(ret, [log_entry.return_value.text])

        with t.subTest('a checklist item is not logged'):
            log_entry.reset_mock()
            t.task.node = checklist_node()

            ret = t.sc.entries

            log_entry.assert_not_called()
            t.assertEqual(ret, [])

    @patch.object(TaskNode, 'snapshot', new_callable=PropertyMock)
    @patch.object(Scratch, 'ancestry', new_callable=PropertyMock)
    @patch.object(Scratch, 'stream_id', new_callable=PropertyMock)
    def test_events(
        t,
        stream_id: PropertyMock,
        ancestry: PropertyMock,
        snapshot: PropertyMock,
    ) -> None:
        stream_id.return_value = '9o71lx'
        ancestry.return_value = MagicMock(spec=['path'])
        ancestry.return_value.path = 'a path'
        snapshot.return_value = sentinel.snapshot

        ret = t.sc.events

        t.assertEqual(
            ret,
            [
                Event(
                    'TaskScratched',
                    'task/9o71lx',
                    {
                        'delta': {'removed': [False, True]},
                        'snapshot': sentinel.snapshot,
                        'ancestry': 'a path',
                    },
                )
            ],
        )


class BackfillTests(TestCase):
    """Unit tests for battodo.mutate.Backfill."""

    def setUp(t) -> None:
        t.bf = Backfill(SOURCE, TODAY)

    def test_write(t) -> None:
        first, second = MagicMock(spec=['write']), MagicMock(spec=['write'])
        t.bf.lists = [first, second]

        t.bf.write()

        # Each list with a task to stamp writes itself.
        first.write.assert_called_once_with()
        second.write.assert_called_once_with()

    @patch(f'{SRC}.ListBackfill', autospec=True)
    @patch(f'{SRC}.discover_lists', autospec=True)
    def test_lists(
        t,
        discover_lists: MagicMock,
        list_backfill: MagicMock,
    ) -> None:
        discover_lists.return_value = [ANOTHER_PATH, LIST_PATH]
        dated = MagicMock(spec=['tasks'])
        dated.tasks = []
        undated = MagicMock(spec=['tasks'])
        undated.tasks = [bare_node()]
        list_backfill.side_effect = [dated, undated]

        # Two reads: the write changes the lists the report reads after.
        # Each discovered list, read on the day; only one has a task.
        ret = t.bf.lists
        discover_lists.assert_called_once_with(SOURCE)
        t.assertEqual(
            list_backfill.call_args_list,
            [call(ANOTHER_PATH, TODAY), call(LIST_PATH, TODAY)],
        )
        t.assertEqual(ret, [undated])

        again = t.bf.lists
        t.assertIs(again, ret)
        discover_lists.assert_called_once_with(SOURCE)


class CompletedLogTests(TestCase):
    """Unit tests for battodo.mutate.CompletedLog."""

    def setUp(t) -> None:
        t.cl = CompletedLog(SOURCE)

    def test_path(t) -> None:
        ret = t.cl.path
        t.assertEqual(ret, SOURCE / 'completed.md')

    @patch.object(CompletedLog, 'path', new_callable=PropertyMock)
    def test_lead(t, path: PropertyMock) -> None:
        log = MagicMock(spec=Path)
        log.exists.return_value = True
        path.return_value = log

        cases = {
            'a log that ends on a newline': ('# A log\n', ''),
            'an empty log': ('', ''),
            'a log that ends mid-line gains a newline': ('# A log', '\n'),
        }
        for name, (text, expected) in cases.items():
            with t.subTest(name):
                log.read_text.return_value = text
                ret = t.cl.lead
                t.assertEqual(ret, expected)

        with t.subTest('a log that is not there yet'):
            log.exists.return_value = False
            log.read_text.reset_mock()

            ret = t.cl.lead

            t.assertEqual(ret, '')
            log.read_text.assert_not_called()

    @patch.object(CompletedLog, 'lead', new_callable=PropertyMock)
    @patch.object(CompletedLog, 'path', new_callable=PropertyMock)
    def test_append(t, path: PropertyMock, lead: PropertyMock) -> None:
        log = MagicMock(spec=Path)
        handle = MagicMock(spec=TextIOWrapper)
        log.open.return_value.__enter__.return_value = handle
        path.return_value = log
        lead.return_value = '\n'

        with t.subTest('the entries, after the lead, one per line'):
            t.cl.append(['a record', 'another record'])

            log.open.assert_called_once_with('a', encoding='utf-8')
            handle.write.assert_called_once_with(
                '\na record\nanother record\n'
            )

        with t.subTest('no entry: the log is not opened'):
            log.open.reset_mock()
            t.cl.append([])
            log.open.assert_not_called()


class ChangesetTests(TestCase):
    """Unit tests for battodo.mutate.Changeset."""

    def setUp(t) -> None:
        t.path = MagicMock(spec=Path)
        t.path.name = 'a-list.md'
        t.events = [
            Event('TaskUpdated', 'task/pp02cd', sentinel.stamp),
            Event('TaskAdded', 'task/cc03ef', sentinel.added),
        ]
        t.cs = Changeset(
            'the list as written',
            ['a record'],
            t.events,
            t.path,
            SOURCE,
        )

    @patch(f'{SRC}.Journal', autospec=True)
    @patch(f'{SRC}.CompletedLog', autospec=True)
    def test_write(t, completed_log: MagicMock, journal: MagicMock) -> None:
        steps: list[str] = []
        t.path.write_text.side_effect = lambda text: steps.append('list')
        log = completed_log.return_value
        log.append.side_effect = lambda entries: steps.append('log')
        appended = journal.return_value.append
        appended.side_effect = lambda *args, **kwargs: steps.append('event')

        t.cs.write()

        with t.subTest('the list, then the log, then each event'):
            t.assertEqual(steps, ['list', 'log', 'event', 'event'])

        with t.subTest('the text goes to the list file'):
            t.path.write_text.assert_called_once_with('the list as written')

        with t.subTest('the log of the source takes the records'):
            completed_log.assert_called_once_with(SOURCE)
            log.append.assert_called_once_with(['a record'])

        with t.subTest('one append an event, naming the agent and the list'):
            journal.assert_called_once_with(SOURCE)
            t.assertEqual(
                appended.call_args_list,
                [
                    call(
                        'TaskUpdated',
                        'task/pp02cd',
                        sentinel.stamp,
                        actor='agent',
                        source_file='a-list.md',
                    ),
                    call(
                        'TaskAdded',
                        'task/cc03ef',
                        sentinel.added,
                        actor='agent',
                        source_file='a-list.md',
                    ),
                ],
            )


class NamedListTests(TestCase):
    """Unit tests for battodo.mutate.NamedList."""

    def setUp(t) -> None:
        t.nl = NamedList(SOURCE, 'a-list')

    def test_path(t) -> None:
        t.nl.lists = [ANOTHER_PATH, LIST_PATH]

        with t.subTest('the discovered list whose stem is the name'):
            ret = t.nl.path
            t.assertEqual(ret, LIST_PATH)

        with t.subTest('a name no list carries is refused'):
            t.nl.name = 'a-missing-list'

            with t.assertRaises(ListError) as caught:
                _ = t.nl.path

            t.assertEqual(
                str(caught.exception),
                "no list named 'a-missing-list' in /a-source; "
                'available: another-list, a-list',
            )

    @patch(f'{SRC}.discover_lists', autospec=True)
    def test_lists(t, discover_lists: MagicMock) -> None:
        # Two reads: discovery reads every list in the source.
        ret = t.nl.lists
        t.assertIs(ret, discover_lists.return_value)

        again = t.nl.lists
        t.assertIs(again, ret)
        discover_lists.assert_called_once_with(SOURCE)


class SuppliedFieldsTests(TestCase):
    """Unit tests for battodo.mutate.SuppliedFields."""

    def setUp(t) -> None:
        t.sf = SuppliedFields({'TAGS': 'a-tag', 'P': '3'}, TODAY)

    @patch.object(SuppliedFields, 'checked', new_callable=PropertyMock)
    def test_ordered(t, checked: PropertyMock) -> None:
        checked.return_value = {
            'TAGS': 'a-tag',
            'REPEAT': '7d',
            'DUE': '2026-09-01',
            'LOE': '2',
            'P': '3',
        }

        ret = t.sf.ordered

        # The fields as read, in SCHEMA.md order.
        t.assertEqual(
            list(ret.items()),
            [
                ('P', '3'),
                ('LOE', '2'),
                ('DUE', '2026-09-01'),
                ('REPEAT', '7d'),
                ('TAGS', 'a-tag'),
            ],
        )

    @patch(f'{SRC}.parse_date', autospec=True)
    @patch(f'{SRC}.next_due', autospec=True)
    def test_checked(t, next_due: MagicMock, parse_date: MagicMock) -> None:
        with t.subTest('the supplied fields, each value read'):
            ret = t.sf.checked
            t.assertEqual(ret, {'TAGS': 'a-tag', 'P': '3'})

        with t.subTest('a due date is written as the parser reads it'):
            t.sf.fields = {'DUE': 'a due date'}
            parse_date.return_value = date(2026, 9, 1)

            ret = t.sf.checked

            parse_date.assert_called_once_with('a due date')
            t.assertEqual(ret, {'DUE': '2026-09-01'})

        with t.subTest('a recurrence is read against the day'):
            t.sf.fields = {'REPEAT': 'a recurrence'}

            ret = t.sf.checked

            next_due.assert_called_once_with('a recurrence', TODAY)
            t.assertEqual(ret, {'REPEAT': 'a recurrence'})

        with t.subTest('a recurrence the scheduler cannot read'):
            next_due.side_effect = ValueError('unrecognised REPEAT value')
            with t.assertRaisesRegex(ValueError, 'unrecognised REPEAT'):
                _ = t.sf.checked

        parse_date.return_value = None
        refused = {
            'a priority that is not a number': (
                {'P': 'high'},
                "P must be a whole number, not 'high'",
            ),
            'a level of effort off the scale': (
                {'LOE': '4'},
                "LOE must be one of 1, 2, 3, 5, 8, not '4'",
            ),
            'a due date that does not read': (
                {'DUE': 'someday'},
                "DUE must be an ISO date, not 'someday'",
            ),
            'a priority is read first, a recurrence last': (
                {'REPEAT': 'often', 'DUE': 'x', 'LOE': '4', 'P': 'high'},
                "P must be a whole number, not 'high'",
            ),
        }
        for name, (fields, message) in refused.items():
            with t.subTest(name):
                t.sf.fields = fields

                with t.assertRaises(ValueError) as caught:
                    _ = t.sf.checked

                t.assertEqual(str(caught.exception), message)

    def test_refuse_root_fields(t) -> None:
        with t.subTest('the fields a subtask carries'):
            # Nothing to refuse: the call returns.
            t.sf.fields = {'LOE': '2', 'DUE': '2026-09-01', 'TAGS': 'a-tag'}
            t.sf.refuse_root_fields()

        refused = {
            'a priority, which the top-level task owns': (
                {'P': '3'},
                'P belongs to the top-level task, not to a subtask',
            ),
            'a recurrence, which the top-level task owns': (
                {'REPEAT': '7d'},
                'REPEAT belongs to the top-level task, not to a subtask',
            ),
            'both: the priority first': (
                {'REPEAT': '7d', 'P': '3'},
                'P belongs to the top-level task, not to a subtask',
            ),
        }
        for name, (fields, message) in refused.items():
            with t.subTest(name):
                t.sf.fields = fields

                with t.assertRaises(ValueError) as caught:
                    t.sf.refuse_root_fields()

                t.assertEqual(str(caught.exception), message)


class AddedLineTests(TestCase):
    """Unit tests for battodo.mutate.AddedLine."""

    def setUp(t) -> None:
        t.al = AddedLine('the line as written', {'P': '3', 'ID': 'zz01ab'})

    @patch.object(AddedLine, 'node', new_callable=PropertyMock)
    def test_payload(t, node: PropertyMock) -> None:
        node.return_value = MagicMock(spec=['snapshot'])
        node.return_value.snapshot = sentinel.snapshot

        ret = t.al.payload

        # Each field written against nothing, and the line as written.
        t.assertEqual(
            ret,
            {
                'delta': {'P': [None, '3'], 'ID': [None, 'zz01ab']},
                'snapshot': sentinel.snapshot,
            },
        )

    @patch(f'{SRC}.TodoDocument', autospec=True)
    def test_node(t, todo_document: MagicMock) -> None:
        todo_document.return_value.tasks = [sentinel.node]

        ret = t.al.node

        # The line alone in an open section, as the parser reads it.
        todo_document.assert_called_once_with(
            f'{OPEN_HEADING}\nthe line as written'
        )
        t.assertIs(ret, sentinel.node)


class LogEntryTests(TestCase):
    """Unit tests for battodo.mutate.LogEntry."""

    def setUp(t) -> None:
        t.ancestry = MagicMock(spec=['path', 'node'])
        t.ancestry.path = 'A task > A subtask of it'
        t.ancestry.node = MagicMock(spec=['schema_fields'])
        t.ancestry.node.schema_fields = {'LOE': '2', 'DUE': '2026-08-20'}
        t.le = LogEntry(LIST_PATH, t.ancestry, 'DONE', TODAY)

    @patch.object(LogEntry, 'fields', new_callable=PropertyMock)
    def test_text(t, fields: PropertyMock) -> None:
        with t.subTest('the day, the list, the status, the path, the fields'):
            fields.return_value = '[LOE:2]'

            ret = t.le.text

            t.assertEqual(
                ret,
                '2026-08-08 | a-list | DONE | A task > A subtask of it [LOE:2]',
            )

        with t.subTest('a task with no SCHEMA.md field ends at its path'):
            fields.return_value = ''

            ret = t.le.text

            t.assertEqual(
                ret,
                '2026-08-08 | a-list | DONE | A task > A subtask of it',
            )

    def test_fields(t) -> None:
        ret = t.le.fields
        t.assertEqual(ret, '[LOE:2] [DUE:2026-08-20]')


class ListBackfillTests(TestCase):
    """Unit tests for battodo.mutate.ListBackfill."""

    def setUp(t) -> None:
        t.path = MagicMock(spec=Path)
        t.lb = ListBackfill(t.path, TODAY)

    @patch(f'{SRC}.Changeset', autospec=True)
    @patch.object(ListBackfill, 'events', new_callable=PropertyMock)
    @patch.object(ListBackfill, 'entries', new_callable=PropertyMock)
    @patch.object(ListBackfill, 'text', new_callable=PropertyMock)
    def test_write(
        t,
        text: PropertyMock,
        entries: PropertyMock,
        events: PropertyMock,
        changeset: MagicMock,
    ) -> None:
        text.return_value = sentinel.text
        entries.return_value = sentinel.entries
        events.return_value = sentinel.events

        with t.subTest('the list, its log records and its events'):
            t.lb.write()

            changeset.assert_called_once_with(
                sentinel.text,
                sentinel.entries,
                sentinel.events,
                t.path,
                t.path.parent,
            )
            changeset.return_value.write.assert_called_once_with()

        with t.subTest('a refused text: nothing else is read or written'):
            changeset.reset_mock()
            entries.reset_mock()
            text.side_effect = ValueError('refused')

            with t.assertRaises(ValueError):
                t.lb.write()

            entries.assert_not_called()
            changeset.assert_not_called()

    def test_source(t) -> None:
        ret = t.lb.source
        t.assertIs(ret, t.path.parent)

    @patch.object(ListBackfill, 'document', new_callable=PropertyMock)
    def test_text(t, document: PropertyMock) -> None:
        document.return_value = MagicMock(spec=['text'])
        ret = t.lb.text
        t.assertIs(ret, document.return_value.text)

    @patch(f'{SRC}.TodoDocument', autospec=True)
    @patch.object(ListBackfill, 'stamps', new_callable=PropertyMock)
    def test_document(
        t,
        stamps: PropertyMock,
        todo_document: MagicMock,
    ) -> None:
        t.lb.parsed = MagicMock(spec=['text'])
        stamps.return_value = {
            2: {'ADDED': '2026-08-08', 'ID': 'zz01ab'},
            4: {'ADDED': '2026-08-08'},
        }
        doc = todo_document.return_value

        ret = t.lb.document

        todo_document.assert_called_once_with(t.lb.parsed.text)
        t.assertEqual(
            doc.method_calls,
            [
                call.set_fields(2, {'ADDED': '2026-08-08', 'ID': 'zz01ab'}),
                call.set_fields(4, {'ADDED': '2026-08-08'}),
            ],
        )
        t.assertIs(ret, doc)

    @patch(f'{SRC}.TodoDocument', autospec=True)
    def test_parsed(t, todo_document: MagicMock) -> None:
        # Two reads: one read of the file answers every property.
        ret = t.lb.parsed
        todo_document.assert_called_once_with(t.path.read_text.return_value)
        t.assertIs(ret, todo_document.return_value)

        again = t.lb.parsed
        t.assertIs(again, ret)
        t.path.read_text.assert_called_once_with()

    @patch.object(ListBackfill, 'tasks', new_callable=PropertyMock)
    def test_stamps(t, tasks: PropertyMock) -> None:
        tasks.return_value = [bare_node(), undated_due_node()]
        t.lb.ids = {1: 'zz01ab', 6: 'ud05ef'}

        ret = t.lb.stamps

        # The add date on each; an id only where the task has none.
        t.assertEqual(
            ret,
            {
                1: {'ADDED': '2026-08-08', 'ID': 'zz01ab'},
                6: {'ADDED': '2026-08-08'},
            },
        )

    def test_tasks(t) -> None:
        undated = MagicMock(spec=['needs_added'], needs_added=True)
        dated = MagicMock(spec=['needs_added'], needs_added=False)
        t.lb.parsed = MagicMock(spec=['tasks'])
        t.lb.parsed.tasks = [undated, dated]

        ret = t.lb.tasks

        # The tasks that take an add date, in file order.
        t.assertEqual(ret, [undated])

    @patch(f'{SRC}.new_task_id', autospec=True)
    @patch.object(ListBackfill, 'tasks', new_callable=PropertyMock)
    def test_ids(t, tasks: PropertyMock, new_task_id: MagicMock) -> None:
        # Two reads: an id drawn at random must name one task.
        tasks.return_value = [bare_node(), undated_due_node()]
        new_task_id.return_value = 'zz01ab'

        ret = t.lb.ids
        t.assertEqual(ret, {1: 'zz01ab', 6: 'ud05ef'})

        again = t.lb.ids
        t.assertIs(again, ret)
        new_task_id.assert_called_once_with()

    def test_entries(t) -> None:
        ret = t.lb.entries
        # A backfill logs no completed-log record.
        t.assertEqual(ret, [])

    @patch.object(TaskNode, 'snapshot', new_callable=PropertyMock)
    @patch.object(ListBackfill, 'tasks', new_callable=PropertyMock)
    def test_events(t, tasks: PropertyMock, snapshot: PropertyMock) -> None:
        tasks.return_value = [bare_node()]
        snapshot.return_value = sentinel.snapshot
        t.lb.ids = {1: 'zz01ab'}

        ret = t.lb.events

        # The date is the migration's: a replay must not read it as an
        # observed fact.
        t.assertEqual(
            ret,
            [
                Event(
                    'TaskAdded',
                    'task/zz01ab',
                    {
                        'delta': {'ADDED': [None, '2026-08-08']},
                        'snapshot': sentinel.snapshot,
                        'backfilled': True,
                    },
                )
            ],
        )


def stand_in(t: TestCase, *targets: str) -> None:
    """Patch each `battodo.mutate` target and set its mock on `t`.

    What the document renders is pinned against real files in the
    integration suite, not here.
    """
    for target in targets:
        patcher = patch(f'{SRC}.{target}', autospec=True)
        setattr(t, target, patcher.start())
        t.addCleanup(patcher.stop)


def logged(handle: MagicMock) -> str:
    """What the completed log was asked to append."""
    return handle.write.call_args[0][0]


def selected(
    directory: MagicMock,
    path: MagicMock,
    doc: MagicMock,
    ancestry: list[TaskNode],
) -> MagicMock:
    """A task a selector reached, with the list and document it sits in."""
    task = MagicMock(
        spec=['source', 'selector', 'today', 'path', 'doc', 'ancestry', 'node']
    )
    task.source = directory
    task.selector = 'a selector'
    task.today = TODAY
    task.path = path
    task.doc = doc
    task.ancestry = ancestry
    task.node = ancestry[-1]
    return task


def document(*lines: str) -> MagicMock:
    """A list document standing in for the one the file holds."""
    doc = create_autospec(TodoDocument, instance=True)
    doc.lines = list(lines)
    return doc


def dated_list() -> MagicMock:
    """A list whose one task already carries its add date."""
    doc = document(OPEN_HEADING, DATED_LINE)
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


class TaskSnapshotTests(TestCase):
    """Unit tests for battodo.mutate.task_snapshot."""

    def test_shape(t) -> None:
        task = TaskNode(
            raw_index=1,
            indent=0,
            done=False,
            title='A task',
            fields={'P': '2', 'TAGS': 'a-tag'},
            raw=TASK_LINE,
        )

        ret = task_snapshot(task)

        t.assertEqual(
            ret,
            {
                'title': 'A task',
                'done': False,
                'fields': {'P': '2', 'TAGS': 'a-tag'},
            },
        )


class UpdateTaskTests(TestCase):
    """Unit tests for battodo.mutate.update_task."""

    Journal: MagicMock
    new_task_id: MagicMock

    def setUp(t) -> None:
        stand_in(t, 'Journal', 'new_task_id')
        t.append = t.Journal.return_value.append
        t.new_task_id.return_value = 'zz01ab'
        t.path = MagicMock(spec=Path)
        t.path.name = 'a-list.md'
        t.path.stem = 'a-list'
        t.dir = MagicMock(spec=Path)
        t.task = TaskNode(
            raw_index=1,
            indent=0,
            done=False,
            title='A task',
            fields={'P': '4', 'LOE': '8', 'ID': '9o71lx'},
            raw=TASK_LINE,
            note_indices=[2],
        )
        t.doc = document(OPEN_HEADING, TASK_LINE, NOTE_LINE, CHILD_LINE)
        t.target = selected(t.dir, t.path, t.doc, [t.task])

    def test_line(t) -> None:
        path, entry = update_task(t.target, {'P': '5'}, title='A new title')

        with t.subTest('the named field is written on to the task line'):
            t.assertEqual(t.doc.set_field.call_args_list, [call(1, 'P', '5')])

        with t.subTest('and the new title over what the fields left'):
            t.doc.set_title.assert_called_once_with(1, 'A new title')
            t.assertEqual(entry, t.doc.set_title.return_value)

        with t.subTest('and the document goes to the file it came from'):
            t.path.write_text.assert_called_once_with(t.doc.text)
            t.assertEqual(path, t.path)

    def test_event(t) -> None:
        update_task(t.target, {'P': '5'}, title='A new title')

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
            t.target = selected(t.dir, t.path, t.doc, [bare])

            _, entry = update_task(t.target, {'P': '5'})

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
            t.target = selected(t.dir, t.path, t.doc, [t.task, child])

            update_task(t.target, {'DUE': '2026-09-01'})

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
            t.target = selected(t.dir, t.path, t.doc, [t.task, child, below])

            update_task(t.target, {'DUE': '2026-09-01'})

            t.assertEqual(
                t.append.call_args[0][2]['ancestry'],
                'A task > A subtask of it > A task below the subtask',
            )

    def test_rejected(t) -> None:
        with (
            t.subTest('an update that names no change'),
            t.assertRaisesRegex(ValueError, 'nothing to update'),
        ):
            update_task(t.target, {})

        with (
            t.subTest('a value btodo cannot read'),
            t.assertRaisesRegex(ValueError, 'DUE must be an ISO date'),
        ):
            update_task(t.target, {'DUE': 'someday'})

        child = TaskNode(
            raw_index=3,
            indent=2,
            done=False,
            title='A subtask of it',
            fields={'LOE': '2'},
            raw=CHILD_LINE,
        )
        t.target = selected(t.dir, t.path, t.doc, [t.task, child])

        with (
            t.subTest('a field the top-level task owns'),
            t.assertRaisesRegex(ValueError, 'P belongs to the top-level task'),
        ):
            update_task(t.target, {'P': '5'})

        item = TaskNode(
            raw_index=3,
            indent=2,
            done=False,
            title='A checklist item',
            fields={},
            raw=ITEM_LINE,
        )
        t.target = selected(t.dir, t.path, t.doc, [t.task, item])

        with (
            t.subTest('a checklist item, which carries no fields'),
            t.assertRaisesRegex(ValueError, 'checklist item'),
        ):
            update_task(t.target, {'DUE': '2026-09-01'})

        with t.subTest('nothing is written and nothing is logged'):
            t.path.write_text.assert_not_called()
            t.append.assert_not_called()


class AddSubtaskTests(TestCase):
    """Unit tests for battodo.mutate.add_subtask."""

    Journal: MagicMock
    new_task_id: MagicMock
    discover_lists: MagicMock
    TodoDocument: MagicMock

    def setUp(t) -> None:
        stand_in(
            t,
            'Journal',
            'new_task_id',
            'discover_lists',
            'TodoDocument',
        )
        t.append = t.Journal.return_value.append
        t.new_task_id.return_value = 'zz01ab'
        t.path = MagicMock(spec=Path)
        t.path.name = 'a-list.md'
        t.path.stem = 'a-list'
        t.dir = MagicMock(spec=Path)
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
        t.doc = document(
            OPEN_HEADING,
            TASK_LINE,
            NOTE_LINE,
            CHILD_LINE,
            BARE_LINE,
        )
        t.target = selected(t.dir, t.path, t.doc, [t.task])
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
        with t.subTest('the list is resolved in the source of the parent'):
            path, entry = add_subtask(
                t.target,
                'a-list',
                'A new subtask',
                {'LOE': '2'},
            )

            t.discover_lists.assert_called_once_with(t.dir)
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
            t.target,
            'a-list',
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
            t.target = selected(t.dir, t.path, t.doc, [t.bare])
            t.new_task_id.side_effect = ['pp02cd', 'cc03ef']
            t.added('A second subtask', {'ID': 'cc03ef'})

            add_subtask(t.target, 'a-list', 'A second subtask', {})

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
                add_subtask(t.target, 'a-list', 'X', {name: '3'})

        with (
            t.subTest('a value btodo cannot read'),
            t.assertRaisesRegex(ValueError, 'DUE must be an ISO date'),
        ):
            add_subtask(t.target, 'a-list', 'X', {'DUE': 'someday'})

        with (
            t.subTest('a level of effort off the scale'),
            t.assertRaisesRegex(ValueError, 'LOE must be one of'),
        ):
            add_subtask(t.target, 'a-list', 'X', {'LOE': '4'})

        with t.subTest('a list no discovered file carries'):
            with t.assertRaises(ListError) as caught:
                add_subtask(t.target, 'another-list', 'X', {})
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
            t.target = selected(t.dir, t.path, t.doc, [t.task, item])
            with t.assertRaisesRegex(ValueError, 'checklist item'):
                add_subtask(t.target, 'a-list', 'X', {})

        with t.subTest('a parent that lives in another list'):
            other = MagicMock(spec=Path)
            other.name = 'another-list.md'
            t.target = selected(t.dir, other, t.doc, [t.task])
            with t.assertRaisesRegex(ValueError, 'a task in another-list.md'):
                add_subtask(t.target, 'a-list', 'X', {})

        with t.subTest('nothing is written and nothing is logged'):
            t.path.write_text.assert_not_called()
            t.append.assert_not_called()


NEW_LINE = '- [ ] A new task'
NO_DATE_LINE = '- [ ] A task with no add date [P:4]'
IDENTIFIED_LINE = '- [ ] A task already identified [P:5] [ID:ii04gh]'
DATED_LINE = '- [ ] A task already dated [P:3] [ADDED:2026-01-05]'
FINISHED_LINE = '- [x] A finished task [P:2]'
PLACEHOLDER_LINE = '- [ ] A task dated YYYY-MM-DD [P:6] [DUE:YYYY-MM-DD]'


class AddTaskTests(TestCase):
    """Unit tests for battodo.mutate.add_task."""

    Journal: MagicMock
    new_task_id: MagicMock
    _resolve_list: MagicMock
    TodoDocument: MagicMock

    def setUp(t) -> None:
        stand_in(t, 'Journal', 'new_task_id', '_resolve_list', 'TodoDocument')
        t.append = t.Journal.return_value.append
        t.new_task_id.return_value = 'zz01ab'
        t.path = MagicMock(spec=Path)
        t.path.name = 'a-list.md'
        t.path.stem = 'a-list'
        t.dir = MagicMock(spec=Path)
        t._resolve_list.return_value = t.path
        # The document answers as though the append has happened: the
        # new entry is the line the index it hands back names.
        t.doc = document(OPEN_HEADING, TASK_LINE, NEW_LINE)
        t.doc.append_open.return_value = 2
        t.written = document()
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


class BackfillFileTests(TestCase):
    """Unit tests for battodo.mutate.backfill_file."""

    Journal: MagicMock
    new_task_id: MagicMock
    TodoDocument: MagicMock

    def setUp(t) -> None:
        stand_in(t, 'Journal', 'new_task_id', 'TodoDocument')
        t.append = t.Journal.return_value.append
        t.new_task_id.return_value = 'zz01ab'
        t.path = MagicMock(spec=Path)
        t.path.name = 'a-list.md'
        t.path.stem = 'a-list'
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
        t.doc = document(
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
            t.TodoDocument.return_value = dated_list()

            ret = backfill_file(t.path, TODAY, t.journal)

            t.assertEqual(ret, [])
            t.path.write_text.assert_not_called()
            t.append.assert_not_called()


class BackfillAllTests(TestCase):
    """Unit tests for battodo.mutate.backfill_all."""

    Journal: MagicMock
    new_task_id: MagicMock
    TodoDocument: MagicMock
    discover_lists: MagicMock

    def setUp(t) -> None:
        stand_in(t, 'Journal', 'new_task_id', 'TodoDocument', 'discover_lists')
        t.append = t.Journal.return_value.append
        t.new_task_id.return_value = 'zz01ab'
        t.path = MagicMock(spec=Path)
        t.path.name = 'a-list.md'
        t.path.stem = 'a-list'
        t.dir = MagicMock(spec=Path)
        t.discover_lists.return_value = [t.path]
        doc = document(OPEN_HEADING, NO_DATE_LINE)
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
            t.TodoDocument.return_value = dated_list()
            ret = backfill_all(t.dir, TODAY)
            t.assertEqual(ret, {})


class CompleteTests(TestCase):
    """Unit tests for battodo.mutate.complete."""

    Journal: MagicMock
    new_task_id: MagicMock
    next_due: MagicMock

    def setUp(t) -> None:
        stand_in(t, 'Journal', 'new_task_id', 'next_due')
        t.append = t.Journal.return_value.append
        t.new_task_id.return_value = 'zz01ab'
        t.path = MagicMock(spec=Path)
        t.path.name = 'a-list.md'
        t.path.stem = 'a-list'
        t.dir = MagicMock(spec=Path)
        t.log = MagicMock(spec=Path)
        t.dir.__truediv__.return_value = t.log
        t.log.exists.return_value = True
        t.log.read_text.return_value = '# Completed Tasks\n'
        t.log_handle = MagicMock(spec=TextIOWrapper)
        t.log.open.return_value.__enter__.return_value = t.log_handle
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
        t.doc = document(
            OPEN_HEADING,
            TASK_LINE,
            NOTE_LINE,
            CHILD_LINE,
            DONE_CHILD_LINE,
            BARE_LINE,
        )
        t.doc.tasks = [t.task]
        t.target = selected(t.dir, t.path, t.doc, [t.task, t.child])

    def test_cascade(t) -> None:
        with t.subTest('the finished block leaves the document'):
            entries = complete(t.target)

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
            t.assertEqual(logged(t.log_handle), '\n'.join(entries) + '\n')

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

            entries = complete(t.target)

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
            t.doc = document(OPEN_HEADING, REPEAT_LINE, NOTE_LINE)
            t.doc.tasks = [recurring]
            t.target = selected(t.dir, t.path, t.doc, [recurring])

            complete(t.target)

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
            t.doc = document(
                OPEN_HEADING,
                TASK_LINE,
                ITEM_LINE,
                CHILD_LINE,
            )
            t.doc.tasks = [parent]
            t.target = selected(t.dir, t.path, t.doc, [parent, item])

            ret = complete(t.target)

            t.assertEqual(ret, [])
            t.log.open.assert_not_called()

        with t.subTest('its box is checked where it stands'):
            t.assertEqual(t.doc.lines[2], '  - [x] A checklist item')

        with t.subTest('and its event lands on the nearest stream that can'):
            t.append.assert_called_once()
            stream, payload = t.append.call_args[0][1:3]
            t.assertEqual(stream, 'task/9o71lx')
            t.assertEqual(payload['ancestry'], 'A task > A checklist item')


class ScratchFunctionTests(TestCase):
    """Unit tests for battodo.mutate.scratch."""

    Journal: MagicMock
    new_task_id: MagicMock

    def setUp(t) -> None:
        stand_in(t, 'Journal', 'new_task_id')
        t.append = t.Journal.return_value.append
        t.new_task_id.return_value = 'zz01ab'
        t.path = MagicMock(spec=Path)
        t.path.name = 'a-list.md'
        t.path.stem = 'a-list'
        t.dir = MagicMock(spec=Path)
        t.log = MagicMock(spec=Path)
        t.dir.__truediv__.return_value = t.log
        t.log.exists.return_value = True
        t.log.read_text.return_value = '# Completed Tasks\n'
        t.log_handle = MagicMock(spec=TextIOWrapper)
        t.log.open.return_value.__enter__.return_value = t.log_handle
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
        t.doc = document(
            OPEN_HEADING,
            '',
            TASK_LINE,
            NOTE_LINE,
            CHILD_LINE,
            '',
            BARE_LINE,
        )
        t.doc.tasks = [t.task]
        t.target = selected(t.dir, t.path, t.doc, [t.task])

    def test_block(t) -> None:
        with t.subTest('the task and everything under it are removed'):
            entries = scratch(t.target)

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
            t.assertEqual(logged(t.log_handle), entries[0] + '\n')

        with t.subTest('one SCRATCHED event, on the task stream'):
            t.append.assert_called_once()
            stream, payload = t.append.call_args[0][1:3]
            t.assertEqual(stream, 'task/9o71lx')
            t.assertEqual(payload['delta'], {'removed': [False, True]})
            t.assertEqual(payload['ancestry'], 'A task')

    def test_log_fields(t) -> None:
        with t.subTest('a task carrying no SCHEMA field logs none'):
            t.task.fields = {'ID': '9o71lx'}

            ret = scratch(t.target)

            t.assertEqual(
                ret,
                ['2026-08-08 | a-list | SCRATCHED | A task'],
            )

    def test_log_newline(t) -> None:
        with t.subTest('a log with no trailing newline gains one first'):
            t.log.read_text.return_value = '# Completed Tasks'
            entries = scratch(t.target)
            t.assertEqual(logged(t.log_handle), '\n' + entries[0] + '\n')

    def test_log_absent(t) -> None:
        with t.subTest('a log that is not there yet is written from empty'):
            t.log.exists.return_value = False

            entries = scratch(t.target)

            t.log.read_text.assert_not_called()
            t.assertEqual(logged(t.log_handle), entries[0] + '\n')

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
            t.doc = document(OPEN_HEADING, BARE_LINE, ITEM_LINE)
            t.doc.tasks = [parent]
            t.target = selected(t.dir, t.path, t.doc, [parent, item])

            ret = scratch(t.target)

            t.assertEqual(ret, [])
            t.log.open.assert_not_called()

        with t.subTest('the ancestor that carries the stream is stamped'):
            t.doc.set_field.assert_called_once_with(1, 'ID', 'zz01ab')

        with t.subTest('and the event lands on that stream instead'):
            t.assertEqual(t.append.call_args[0][1], 'task/zz01ab')


def named_task(*ancestry: TaskNode) -> Mock:
    """The task a selector names, the last of `ancestry`, in a list."""
    task = Mock(
        spec=['source', 'path', 'doc', 'ancestry', 'node', 'today', 'selector']
    )
    task.source = SOURCE
    task.path = LIST_PATH
    task.doc = Mock(spec=['text'])
    task.doc.text = 'the list as read'
    task.ancestry = list(ancestry)
    task.node = ancestry[-1]
    task.today = TODAY
    task.selector = 'a selector'
    return task


def ancestry_of(
    *tasks: TaskNode,
    stream: TaskNode | None = None,
    path: str = 'a path',
) -> MagicMock:
    """The ancestry of the last of `tasks`, outermost first.

    Its events land on `stream`, the last task unless one is named.
    """
    ancestry = MagicMock(spec=['tasks', 'node', 'path', 'stream'])
    ancestry.tasks = list(tasks)
    ancestry.node = tasks[-1]
    ancestry.path = path
    ancestry.stream = tasks[-1] if stream is None else stream
    return ancestry


def parent_node() -> TaskNode:
    """A top-level task with an id, a note and a subtask."""
    return TaskNode(
        raw_index=1,
        indent=0,
        done=False,
        title='A task',
        fields={'P': '4', 'LOE': '8', 'ID': '9o71lx'},
        children=[child_node()],
        note_indices=[2],
    )


def child_node() -> TaskNode:
    """An open subtask with no id."""
    return TaskNode(
        raw_index=3,
        indent=2,
        done=False,
        title='A subtask of it',
        fields={'LOE': '2'},
    )


def done_child_node() -> TaskNode:
    """A subtask already done."""
    return TaskNode(
        raw_index=4,
        indent=2,
        done=True,
        title='A finished subtask',
        fields={'LOE': '1'},
    )


def grandchild_node() -> TaskNode:
    """A task one level below a subtask."""
    return TaskNode(
        raw_index=5,
        indent=4,
        done=False,
        title='A task below the subtask',
        fields={'LOE': '1'},
    )


def checklist_node() -> TaskNode:
    """A child that carries no field."""
    return TaskNode(
        raw_index=3,
        indent=2,
        done=False,
        title='A checklist item',
        fields={},
    )


def bare_node() -> TaskNode:
    """A top-level task with no id and no add date."""
    return TaskNode(
        raw_index=1,
        indent=0,
        done=False,
        title='A task with no id',
        fields={'P': '2'},
    )


def undated_due_node() -> TaskNode:
    """A top-level task with an id and a due date, but no add date."""
    return TaskNode(
        raw_index=6,
        indent=0,
        done=False,
        title='A task due soon',
        fields={'P': '1', 'DUE': '2026-08-20', 'ID': 'ud05ef'},
    )
