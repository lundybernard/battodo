from datetime import date
from io import TextIOWrapper
from pathlib import Path
from unittest import TestCase
from unittest.mock import (
    MagicMock,
    Mock,
    PropertyMock,
    call,
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
    SuppliedTitle,
    TaskNode,
    Update,
)

SRC = 'battodo.mutate'

TODAY = date(2026, 8, 8)
# The source directory, the list a task lives in, and another list.
SOURCE = Path('/a-source')
LIST_PATH = SOURCE / 'a-list.md'
ANOTHER_PATH = SOURCE / 'another-list.md'


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

    @patch(f'{SRC}.SuppliedTitle', autospec=True)
    @patch(f'{SRC}.TodoDocument', autospec=True)
    @patch.object(Addition, 'index', new_callable=PropertyMock)
    @patch.object(Addition, 'written', new_callable=PropertyMock)
    def test_document(
        t,
        written: PropertyMock,
        index: PropertyMock,
        todo_document: MagicMock,
        supplied_title: MagicMock,
    ) -> None:
        written.return_value = sentinel.written
        index.return_value = 4
        supplied_title.return_value.checked = 'A checked title'
        doc = todo_document.return_value
        t.ad.parsed = MagicMock(spec=['text'])

        ret = t.ad.document

        # The bare line goes in last in Open, then its fields go on.
        supplied_title.assert_called_once_with('A new task')
        todo_document.assert_called_once_with(t.ad.parsed.text)
        t.assertEqual(
            doc.method_calls,
            [
                call.insert(4, '- [ ] A checked title'),
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

    @patch(f'{SRC}.SuppliedTitle', autospec=True)
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
        supplied_title: MagicMock,
    ) -> None:
        written.return_value = sentinel.written
        stamped.return_value = False
        node.return_value = t.parent
        index.return_value = 4
        indent.return_value = '  '
        supplied_title.return_value.checked = 'A checked title'
        doc = todo_document.return_value
        t.sa.path = LIST_PATH
        t.sa.parent_id = 'pp02cd'

        with t.subTest('the subtask goes in at its index, its fields on it'):
            ret = t.sa.document

            supplied_title.assert_called_once_with('A new subtask')
            todo_document.assert_called_once_with(t.task.doc.text)
            t.assertEqual(
                doc.method_calls,
                [
                    call.insert(4, '  - [ ] A checked title'),
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

        with t.subTest('a parent whose id is empty is too'):
            node.return_value.fields = {'P': '2', 'ID': ''}
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
    @patch.object(Update, 'new_title', new_callable=PropertyMock)
    @patch.object(Update, 'node', new_callable=PropertyMock)
    @patch.object(Update, 'written', new_callable=PropertyMock)
    def test_document(
        t,
        written: PropertyMock,
        node: PropertyMock,
        new_title: PropertyMock,
        todo_document: MagicMock,
    ) -> None:
        written.return_value = sentinel.written
        node.return_value = t.parent
        new_title.return_value = 'A checked title'
        doc = todo_document.return_value

        with t.subTest('the fields, then the new title, on the task line'):
            ret = t.up.document

            todo_document.assert_called_once_with(t.task.doc.text)
            t.assertEqual(
                doc.method_calls,
                [
                    call.set_fields(1, sentinel.written),
                    call.set_title(1, 'A checked title'),
                ],
            )
            t.assertIs(ret, doc)

        with t.subTest('a title left off is not written'):
            doc.reset_mock()
            new_title.return_value = None

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

    @patch(f'{SRC}.SuppliedTitle', autospec=True)
    def test_new_title(t, supplied_title: MagicMock) -> None:
        with t.subTest('the title the update names, read'):
            ret = t.up.new_title
            supplied_title.assert_called_once_with('A new title')
            t.assertIs(ret, supplied_title.return_value.checked)

        with t.subTest('none, where the update names no title'):
            supplied_title.reset_mock()
            t.up.title = None

            ret = t.up.new_title

            supplied_title.assert_not_called()
            t.assertIsNone(ret)

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

    @patch.object(Update, 'new_title', new_callable=PropertyMock)
    @patch.object(Update, 'node', new_callable=PropertyMock)
    @patch.object(Update, 'written', new_callable=PropertyMock)
    def test_delta(
        t,
        written: PropertyMock,
        node: PropertyMock,
        new_title: PropertyMock,
    ) -> None:
        written.return_value = {'P': '5', 'DUE': '2026-09-01'}
        node.return_value = t.parent
        new_title.return_value = 'A checked title'

        with t.subTest('each field written against the one it replaced'):
            ret = t.up.delta
            t.assertEqual(
                ret,
                {
                    'P': ['4', '5'],
                    'DUE': [None, '2026-09-01'],
                    'title': ['A task', 'A checked title'],
                },
            )

        with t.subTest('a title left off names no title change'):
            new_title.return_value = None
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


class SuppliedTitleTests(TestCase):
    """Unit tests for battodo.mutate.SuppliedTitle."""

    def setUp(t) -> None:
        t.st = SuppliedTitle('A title')

    def test_checked(t) -> None:
        with t.subTest('a title on one line'):
            ret = t.st.checked
            t.assertEqual(ret, 'A title')

        broken = {
            'a line feed': (
                'A\ntitle',
                "title must hold no line break, not 'A\\ntitle'",
            ),
            'a carriage return': (
                'A\rtitle',
                "title must hold no line break, not 'A\\rtitle'",
            ),
        }
        for name, (text, message) in broken.items():
            with t.subTest(name):
                t.st.text = text

                with t.assertRaises(ValueError) as caught:
                    _ = t.st.checked

                t.assertEqual(str(caught.exception), message)


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
