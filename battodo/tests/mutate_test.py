from datetime import date
from io import TextIOWrapper
from pathlib import Path
from typing import Any
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
    Annotation,
    Backfill,
    Changeset,
    CompletedLog,
    Completion,
    CompletionLines,
    Event,
    IdAssignment,
    ListBackfill,
    ListError,
    LogEntry,
    NamedList,
    OpenedTask,
    RecordedTask,
    Reopen,
    SubtaskAddition,
    SuppliedAttributes,
    SuppliedDescription,
    SuppliedEdit,
    SuppliedFields,
    SuppliedTitle,
    TaskCompletion,
    TaskNode,
    Update,
)

SRC = 'battodo.mutate'

TODAY = date(2026, 8, 8)
# A completion day the user gives, earlier than TODAY.
GIVEN_DAY = date(2026, 8, 1)
# The source directory, the list a task lives in, and another list.
SOURCE = Path('/a-source')
LIST_PATH = SOURCE / 'a-list.md'
ANOTHER_PATH = SOURCE / 'another-list.md'
# A document as an add writes it: the new line at index 1, one
# description line under it, then the line that follows the block.
BLOCK_LINES = [
    OPEN_HEADING,
    'the line as written',
    '      A line.',
    'the next line',
]


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
                {LIST_PATH: sentinel.text},
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
    @patch.object(Addition, 'description_lines', new_callable=PropertyMock)
    @patch.object(Addition, 'index', new_callable=PropertyMock)
    @patch.object(Addition, 'written', new_callable=PropertyMock)
    def test_document(
        t,
        written: PropertyMock,
        index: PropertyMock,
        description_lines: PropertyMock,
        todo_document: MagicMock,
        supplied_title: MagicMock,
    ) -> None:
        written.return_value = sentinel.written
        index.return_value = 4
        description_lines.return_value = sentinel.description_lines
        supplied_title.return_value.checked = 'A checked title'
        doc = todo_document.return_value
        t.ad.parsed = MagicMock(spec=['text'])

        ret = t.ad.document

        # The bare line goes in last in Open, then its fields go on,
        # then its description lines go under it.
        supplied_title.assert_called_once_with('A new task')
        todo_document.assert_called_once_with(t.ad.parsed.text)
        t.assertEqual(
            doc.method_calls,
            [
                call.insert(4, '- [ ] A checked title'),
                call.set_fields(4, sentinel.written),
                call.insert_description(4, sentinel.description_lines),
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

    @patch.object(Addition, 'description_lines', new_callable=PropertyMock)
    @patch.object(Addition, 'index', new_callable=PropertyMock)
    @patch.object(Addition, 'document', new_callable=PropertyMock)
    def test_block(
        t,
        document: PropertyMock,
        index: PropertyMock,
        description_lines: PropertyMock,
    ) -> None:
        document.return_value = MagicMock(spec=['lines'])
        document.return_value.lines = BLOCK_LINES
        index.return_value = 1
        description_lines.return_value = ['A line.']

        ret = t.ad.block

        t.assertEqual(ret, 'the line as written\n      A line.')

    @patch(f'{SRC}.SuppliedDescription', autospec=True)
    def test_description_lines(t, supplied_description: MagicMock) -> None:
        with t.subTest('none, where no description is given'):
            ret = t.ad.description_lines
            supplied_description.assert_not_called()
            t.assertEqual(ret, [])

        with t.subTest('the lines of the description given, read'):
            t.ad.description = 'A description'

            ret = t.ad.description_lines

            supplied_description.assert_called_once_with('A description')
            t.assertIs(ret, supplied_description.return_value.lines)

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
    @patch.object(Addition, 'block', new_callable=PropertyMock)
    @patch.object(Addition, 'entry', new_callable=PropertyMock)
    def test_events(
        t,
        entry: PropertyMock,
        block: PropertyMock,
        written: PropertyMock,
        added_line: MagicMock,
    ) -> None:
        entry.return_value = 'the line as written'
        block.return_value = 'the block as written'
        written.return_value = sentinel.written
        t.ad.task_id = 'zz01ab'
        t.ad.attrs = sentinel.attrs
        t.ad.path = LIST_PATH

        ret = t.ad.events

        # One TaskAdded, on the stream of the new task, which carries
        # the attributes and names the list.
        added_line.assert_called_once_with(
            'the block as written',
            sentinel.written,
            'a-list',
            sentinel.attrs,
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
                {LIST_PATH: sentinel.text},
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
    @patch.object(
        SubtaskAddition,
        'description_lines',
        new_callable=PropertyMock,
    )
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
        description_lines: PropertyMock,
        todo_document: MagicMock,
        supplied_title: MagicMock,
    ) -> None:
        written.return_value = sentinel.written
        stamped.return_value = False
        node.return_value = t.parent
        index.return_value = 4
        indent.return_value = '  '
        description_lines.return_value = sentinel.description_lines
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
                    call.insert_description(4, sentinel.description_lines),
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

    @patch.object(
        SubtaskAddition,
        'description_lines',
        new_callable=PropertyMock,
    )
    @patch.object(SubtaskAddition, 'index', new_callable=PropertyMock)
    @patch.object(SubtaskAddition, 'document', new_callable=PropertyMock)
    def test_block(
        t,
        document: PropertyMock,
        index: PropertyMock,
        description_lines: PropertyMock,
    ) -> None:
        document.return_value = MagicMock(spec=['lines'])
        document.return_value.lines = BLOCK_LINES
        index.return_value = 1
        description_lines.return_value = ['A line.']

        ret = t.sa.block

        t.assertEqual(ret, 'the line as written\n      A line.')

    @patch(f'{SRC}.SuppliedDescription', autospec=True)
    def test_description_lines(t, supplied_description: MagicMock) -> None:
        with t.subTest('none, where no description is given'):
            ret = t.sa.description_lines
            supplied_description.assert_not_called()
            t.assertEqual(ret, [])

        with t.subTest('the lines of the description given, read'):
            t.sa.description = 'A description'

            ret = t.sa.description_lines

            supplied_description.assert_called_once_with('A description')
            t.assertIs(ret, supplied_description.return_value.lines)

    def test_entries(t) -> None:
        ret = t.sa.entries
        # An add logs no completed-log record.
        t.assertEqual(ret, [])

    @patch(f'{SRC}.AddedLine', autospec=True)
    @patch.object(SubtaskAddition, 'stamp', new_callable=PropertyMock)
    @patch.object(SubtaskAddition, 'stamped', new_callable=PropertyMock)
    @patch.object(SubtaskAddition, 'written', new_callable=PropertyMock)
    @patch.object(SubtaskAddition, 'block', new_callable=PropertyMock)
    @patch.object(SubtaskAddition, 'entry', new_callable=PropertyMock)
    def test_events(
        t,
        entry: PropertyMock,
        block: PropertyMock,
        written: PropertyMock,
        stamped: PropertyMock,
        stamp: PropertyMock,
        added_line: MagicMock,
    ) -> None:
        entry.return_value = 'the line as written'
        block.return_value = 'the block as written'
        written.return_value = sentinel.written
        stamped.return_value = False
        stamp.return_value = sentinel.stamp
        added_line.return_value.payload = {'delta': sentinel.delta}
        t.sa.task_id = 'cc03ef'
        t.sa.parent_id = '9o71lx'
        t.sa.attrs = sentinel.attrs
        t.sa.path = LIST_PATH

        with t.subTest('one TaskAdded, which names the parent'):
            ret = t.sa.events

            # The TaskAdded carries the attributes and names the list.
            added_line.assert_called_once_with(
                'the block as written',
                sentinel.written,
                'a-list',
                sentinel.attrs,
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

    @patch(f'{SRC}.IdAssignment', autospec=True)
    @patch.object(SubtaskAddition, 'node', new_callable=PropertyMock)
    def test_stamp(t, node: PropertyMock, id_assignment: MagicMock) -> None:
        node.return_value = bare_node()
        t.sa.parent_id = 'pp02cd'
        t.sa.path = LIST_PATH

        ret = t.sa.stamp

        id_assignment.assert_called_once_with(
            node.return_value, 'pp02cd', 'a-list'
        )
        t.assertIs(ret, id_assignment.return_value.event)


class UpdateTests(TestCase):
    """Unit tests for battodo.mutate.Update."""

    def setUp(t) -> None:
        t.parent = parent_node()
        t.task = named_task(t.parent)
        t.up = Update(t.task, {'P': '5'}, title='A new title')

    @patch(f'{SRC}.Changeset', autospec=True)
    @patch.object(Update, 'events', new_callable=PropertyMock)
    @patch.object(Update, 'entries', new_callable=PropertyMock)
    @patch.object(Update, 'lists', new_callable=PropertyMock)
    def test_write(
        t,
        lists: PropertyMock,
        entries: PropertyMock,
        events: PropertyMock,
        changeset: MagicMock,
    ) -> None:
        lists.return_value = sentinel.lists
        entries.return_value = sentinel.entries
        events.return_value = sentinel.events
        t.up.path = ANOTHER_PATH

        with t.subTest('the lists, the log records and the events'):
            t.up.write()

            changeset.assert_called_once_with(
                sentinel.lists,
                sentinel.entries,
                sentinel.events,
                ANOTHER_PATH,
                SOURCE,
            )
            changeset.return_value.write.assert_called_once_with()

        with t.subTest('a refused list: nothing else is read or written'):
            changeset.reset_mock()
            entries.reset_mock()
            lists.side_effect = ValueError('refused')

            with t.assertRaises(ValueError):
                t.up.write()

            entries.assert_not_called()
            changeset.assert_not_called()

    @patch.object(Update, 'joined', new_callable=PropertyMock)
    @patch.object(Update, 'moved', new_callable=PropertyMock)
    @patch.object(Update, 'text', new_callable=PropertyMock)
    def test_lists(
        t,
        text: PropertyMock,
        moved: PropertyMock,
        joined: PropertyMock,
    ) -> None:
        text.return_value = sentinel.text
        joined.return_value = MagicMock(spec=['text'], text=sentinel.joined)
        t.up.path = ANOTHER_PATH

        with t.subTest('the list that holds the task'):
            moved.return_value = False
            ret = t.up.lists
            t.assertEqual(ret, {LIST_PATH: sentinel.text})

        with t.subTest('a move: the list it leaves, then the one it joins'):
            moved.return_value = True

            ret = t.up.lists

            t.assertEqual(
                ret,
                {LIST_PATH: sentinel.text, ANOTHER_PATH: sentinel.joined},
            )

    def test_source(t) -> None:
        ret = t.up.source
        t.assertIs(ret, t.task.source)

    @patch(f'{SRC}.NamedList', autospec=True)
    def test_path(t, named_list: MagicMock) -> None:
        with t.subTest('the list that holds the task'):
            ret = t.up.path
            named_list.assert_not_called()
            t.assertIs(ret, t.task.path)

        with t.subTest('the list the update names'):
            t.up = Update(t.task, {}, list_name='another-list')

            ret = t.up.path

            named_list.assert_called_once_with(SOURCE, 'another-list')
            t.assertIs(ret, named_list.return_value.path)

    def test_moved(t) -> None:
        with t.subTest('a task that stays in its list'):
            t.up.path = LIST_PATH
            ret = t.up.moved
            t.assertFalse(ret)

        with t.subTest('a task bound for another list'):
            t.up.path = ANOTHER_PATH
            ret = t.up.moved
            t.assertTrue(ret)

    @patch.object(Update, 'rewritten', new_callable=PropertyMock)
    @patch.object(Update, 'moved', new_callable=PropertyMock)
    @patch.object(Update, 'document', new_callable=PropertyMock)
    def test_text(
        t,
        document: PropertyMock,
        moved: PropertyMock,
        rewritten: PropertyMock,
    ) -> None:
        document.return_value = MagicMock(spec=['text', 'drop'])
        rewritten.return_value = MagicMock(spec=['block'], block={1, 2, 3})

        with t.subTest('the list with the task rewritten'):
            moved.return_value = False

            ret = t.up.text

            document.return_value.drop.assert_not_called()
            t.assertIs(ret, document.return_value.text)

        with t.subTest('a move: the list without the rewritten block'):
            moved.return_value = True

            ret = t.up.text

            document.return_value.drop.assert_called_once_with({1, 2, 3})
            t.assertIs(ret, document.return_value.text)

    @patch(f'{SRC}.TodoDocument', autospec=True)
    @patch.object(Update, 'new_description', new_callable=PropertyMock)
    @patch.object(Update, 'new_title', new_callable=PropertyMock)
    @patch.object(Update, 'node', new_callable=PropertyMock)
    @patch.object(Update, 'written', new_callable=PropertyMock)
    def test_document(
        t,
        written: PropertyMock,
        node: PropertyMock,
        new_title: PropertyMock,
        new_description: PropertyMock,
        todo_document: MagicMock,
    ) -> None:
        written.return_value = sentinel.written
        node.return_value = t.parent
        new_title.return_value = 'A checked title'
        new_description.return_value = None
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

        with t.subTest('a description replaces the description lines'):
            doc.reset_mock()
            new_description.return_value = sentinel.lines

            _ = t.up.document

            t.assertEqual(
                doc.method_calls,
                [
                    call.set_fields(1, sentinel.written),
                    call.set_description(t.parent, sentinel.lines),
                ],
            )

    @patch(f'{SRC}.TodoDocument', autospec=True)
    @patch.object(Update, 'node', new_callable=PropertyMock)
    @patch.object(Update, 'document', new_callable=PropertyMock)
    def test_rewritten(
        t,
        document: PropertyMock,
        node: PropertyMock,
        todo_document: MagicMock,
    ) -> None:
        document.return_value = MagicMock(spec=['text'], text=sentinel.text)
        node.return_value = t.parent
        other = MagicMock(spec=['raw_index'], raw_index=8)
        rewritten = MagicMock(spec=['raw_index'], raw_index=1)
        todo_document.return_value.tasks = [other, rewritten]

        ret = t.up.rewritten

        # The task that keeps the line of the task the update names.
        todo_document.assert_called_once_with(sentinel.text)
        t.assertIs(ret, rewritten)

    @patch.object(Update, 'rewritten', new_callable=PropertyMock)
    @patch.object(Update, 'document', new_callable=PropertyMock)
    def test_block(t, document: PropertyMock, rewritten: PropertyMock) -> None:
        document.return_value = MagicMock(spec=['lines'])
        document.return_value.lines = [
            OPEN_HEADING,
            'the task line',
            'its description line',
            'a line of another task',
            'its child line',
        ]
        rewritten.return_value = MagicMock(spec=['block'], block={4, 1, 2})

        ret = t.up.block

        t.assertEqual(
            ret,
            ['the task line', 'its description line', 'its child line'],
        )

    @patch(f'{SRC}.TodoDocument', autospec=True)
    @patch.object(Update, 'block', new_callable=PropertyMock)
    def test_joined(t, block: PropertyMock, todo_document: MagicMock) -> None:
        block.return_value = ['the task line', 'its child line']
        path = MagicMock(spec=Path)
        path.read_text.return_value = 'the other list as read'
        t.up.path = path
        doc = todo_document.return_value

        ret = t.up.joined

        # The block goes in whole, after the last open entry.
        todo_document.assert_called_once_with('the other list as read')
        t.assertEqual(
            doc.method_calls,
            [
                call.append_open('the task line'),
                call.append_open('its child line'),
            ],
        )
        t.assertIs(ret, doc)

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
    @patch.object(Update, 'edit', new_callable=PropertyMock)
    def test_node(
        t,
        edit: PropertyMock,
        refuse_checklist_item: MagicMock,
    ) -> None:
        edit.return_value = MagicMock(spec=['refuse_root_fields'])
        refuse_root_fields = edit.return_value.refuse_root_fields

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

        with t.subTest('a subtask moves with its top-level task alone'):
            t.up.list_name = 'another-list'

            with t.assertRaises(ValueError) as caught:
                _ = t.up.node

            t.assertEqual(
                str(caught.exception),
                "'A subtask of it' is a subtask: --list moves a top-level "
                'task, and its subtasks with it',
            )

        with t.subTest('a checklist item is refused before its fields'):
            t.up.list_name = None
            refuse_root_fields.reset_mock()
            refuse_checklist_item.side_effect = ValueError('a checklist item')

            with t.assertRaisesRegex(ValueError, 'a checklist item'):
                _ = t.up.node

            refuse_root_fields.assert_not_called()

    @patch.object(Update, 'node', new_callable=PropertyMock)
    @patch.object(Update, 'edit', new_callable=PropertyMock)
    def test_new_title(t, edit: PropertyMock, node: PropertyMock) -> None:
        edit.return_value = MagicMock(spec=['checked_title', 'new_title'])
        edited = edit.return_value
        node.return_value = t.parent

        with t.subTest('the title that changes the task'):
            edited.checked_title = 'A new title'

            ret = t.up.new_title

            edited.new_title.assert_called_once_with(node.return_value)
            t.assertIs(ret, edited.new_title.return_value)

        with t.subTest('none, where none is named: the task is not read'):
            edited.new_title.reset_mock()
            node.reset_mock()
            edited.checked_title = None

            ret = t.up.new_title

            edited.new_title.assert_not_called()
            node.assert_not_called()
            t.assertIsNone(ret)

    @patch.object(Update, 'node', new_callable=PropertyMock)
    @patch.object(Update, 'edit', new_callable=PropertyMock)
    def test_new_description(
        t,
        edit: PropertyMock,
        node: PropertyMock,
    ) -> None:
        edit.return_value = MagicMock(
            spec=['checked_description', 'new_description']
        )
        edited = edit.return_value
        node.return_value = t.parent

        with t.subTest('the description lines that change the task'):
            edited.checked_description = ['A line.']

            ret = t.up.new_description

            edited.new_description.assert_called_once_with(node.return_value)
            t.assertIs(ret, edited.new_description.return_value)

        with t.subTest('none, where none is named: the task is not read'):
            edited.new_description.reset_mock()
            node.reset_mock()
            edited.checked_description = None

            ret = t.up.new_description

            edited.new_description.assert_not_called()
            node.assert_not_called()
            t.assertIsNone(ret)

    @patch.object(Update, 'new_description', new_callable=PropertyMock)
    @patch.object(Update, 'new_title', new_callable=PropertyMock)
    @patch.object(Update, 'changes', new_callable=PropertyMock)
    @patch.object(Update, 'moved', new_callable=PropertyMock)
    def test_checked(
        t,
        moved: PropertyMock,
        changes: PropertyMock,
        new_title: PropertyMock,
        new_description: PropertyMock,
    ) -> None:
        # Each case: the changes, the new title, the new description, a
        # list named, and whether it moves the task.
        cases = {
            'the named fields that change the task': (
                {'P': '5'},
                None,
                None,
                None,
                False,
            ),
            'a title alone names no field': ({}, 'A title', None, None, False),
            'nor does a description alone': (
                {},
                None,
                ['A line.'],
                None,
                False,
            ),
            'nor does a move alone': ({}, None, None, 'another-list', True),
        }
        for name, (fields, title, lines, list_name, moves) in cases.items():
            with t.subTest(name):
                changes.return_value = fields
                new_title.return_value = title
                new_description.return_value = lines
                t.up = Update(t.task, {}, list_name=list_name)
                moved.return_value = moves

                ret = t.up.checked

                t.assertEqual(ret, fields)

        refused = {
            'no change, and no list': None,
            'the list the task is in, and no change': 'a-list',
        }
        for name, list_name in refused.items():
            with t.subTest(name):
                changes.return_value = {}
                new_title.return_value = None
                new_description.return_value = None
                t.up = Update(t.task, {}, list_name=list_name)
                moved.return_value = False

                with t.assertRaises(ValueError) as caught:
                    _ = t.up.checked

                t.assertEqual(
                    str(caught.exception),
                    'nothing to update: name a field, a title, a description '
                    'or a list',
                )

        with t.subTest('an open task takes no --with-subtasks, first'):
            changes.reset_mock()
            t.up = Update(t.task, {'P': '5'}, with_subtasks=True)

            with t.assertRaises(ValueError) as caught:
                _ = t.up.checked

            t.assertEqual(
                str(caught.exception),
                "'a selector' names an open task: --with-subtasks reopens "
                'a closed task and its subtasks',
            )
            changes.assert_not_called()

    @patch.object(Update, 'node', new_callable=PropertyMock)
    @patch.object(Update, 'edit', new_callable=PropertyMock)
    def test_changes(t, edit: PropertyMock, node: PropertyMock) -> None:
        edit.return_value = MagicMock(spec=['changed', 'changes'])
        edited = edit.return_value
        node.return_value = t.parent

        with t.subTest('the named fields that change the task'):
            edited.changed = {'P': '5'}

            ret = t.up.changes

            edited.changes.assert_called_once_with(node.return_value)
            t.assertIs(ret, edited.changes.return_value)

        with t.subTest('none, where no field is named: the task is not read'):
            edited.changes.reset_mock()
            node.reset_mock()
            edited.changed = {}

            ret = t.up.changes

            edited.changes.assert_not_called()
            node.assert_not_called()
            t.assertEqual(ret, {})

    @patch(f'{SRC}.SuppliedEdit', autospec=True)
    def test_edit(t, supplied_edit: MagicMock) -> None:
        ret = t.up.edit
        # The named values, read against the day of the task.
        supplied_edit.assert_called_once_with(
            {'P': '5'}, 'A new title', None, TODAY
        )
        t.assertIs(ret, supplied_edit.return_value)

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

    @patch.object(TaskNode, 'listed_snapshot', autospec=True)
    @patch.object(Update, 'ancestry', new_callable=PropertyMock)
    @patch.object(Update, 'nested', new_callable=PropertyMock)
    @patch.object(Update, 'node', new_callable=PropertyMock)
    @patch.object(Update, 'delta', new_callable=PropertyMock)
    def test_payload(
        t,
        delta: PropertyMock,
        node: PropertyMock,
        nested: PropertyMock,
        ancestry: PropertyMock,
        snapshot: MagicMock,
    ) -> None:
        delta.return_value = sentinel.delta
        node.return_value = t.parent
        nested.return_value = False
        ancestry.return_value = MagicMock(spec=['path'])
        ancestry.return_value.path = 'a path'
        snapshot.return_value = sentinel.snapshot

        with t.subTest('the delta, and the state it changed from'):
            ret = t.up.payload

            snapshot.assert_called_once_with(t.parent, 'a-list')
            t.assertEqual(
                ret,
                {'delta': sentinel.delta, 'snapshot': sentinel.snapshot},
            )

        with t.subTest('a subtask records where it sits'):
            nested.return_value = True
            ret = t.up.payload
            t.assertEqual(ret['ancestry'], 'a path')

        with t.subTest('the attributes, where any are given'):
            nested.return_value = False
            t.up.attrs = {'cost': '45.00'}

            ret = t.up.payload

            t.assertEqual(
                ret,
                {
                    'delta': sentinel.delta,
                    'snapshot': sentinel.snapshot,
                    'attrs': {'cost': '45.00'},
                },
            )

    @patch.object(Update, 'moved', new_callable=PropertyMock)
    @patch.object(Update, 'edit', new_callable=PropertyMock)
    @patch.object(Update, 'node', new_callable=PropertyMock)
    @patch.object(Update, 'written', new_callable=PropertyMock)
    def test_delta(
        t,
        written: PropertyMock,
        node: PropertyMock,
        edit: PropertyMock,
        moved: PropertyMock,
    ) -> None:
        written.return_value = sentinel.written
        node.return_value = t.parent
        edit.return_value = MagicMock(spec=['delta'])
        edit_delta = edit.return_value.delta
        moved.return_value = False

        with t.subTest('the fields written, the title and the description'):
            edit_delta.return_value = {'P': ['4', '5']}

            ret = t.up.delta

            edit_delta.assert_called_once_with(t.parent, sentinel.written)
            t.assertEqual(ret, {'P': ['4', '5']})

        with t.subTest('a move, from the list it leaves to the one it joins'):
            edit_delta.return_value = {}
            moved.return_value = True
            t.up.path = ANOTHER_PATH

            ret = t.up.delta

            t.assertEqual(ret, {'list': ['a-list', 'another-list']})

    @patch(f'{SRC}.Ancestry', autospec=True)
    def test_ancestry(t, ancestry: MagicMock) -> None:
        ret = t.up.ancestry
        ancestry.assert_called_once_with(t.task.ancestry)
        t.assertIs(ret, ancestry.return_value)


class ReopenTests(TestCase):
    """Unit tests for battodo.mutate.Reopen."""

    def setUp(t) -> None:
        t.task = Mock(spec=['source', 'selector', 'today', 'selection'])
        t.task.source = SOURCE
        t.task.selector = 'a selector'
        t.task.today = TODAY
        t.ro = Reopen(t.task, sentinel.zone, {'P': '5'}, title='A new title')

    @patch(f'{SRC}.Changeset', autospec=True)
    @patch.object(Reopen, 'events', new_callable=PropertyMock)
    @patch.object(Reopen, 'entries', new_callable=PropertyMock)
    @patch.object(Reopen, 'text', new_callable=PropertyMock)
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
        t.ro.path = LIST_PATH

        with t.subTest('the list, its log records and its events'):
            t.ro.write()

            changeset.assert_called_once_with(
                {LIST_PATH: sentinel.text},
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
                t.ro.write()

            entries.assert_not_called()
            changeset.assert_not_called()

    def test_source(t) -> None:
        ret = t.ro.source
        t.assertIs(ret, SOURCE)

    @patch.object(Reopen, 'document', new_callable=PropertyMock)
    def test_text(t, document: PropertyMock) -> None:
        document.return_value = MagicMock(spec=['text'])
        ret = t.ro.text
        t.assertIs(ret, document.return_value.text)

    @patch(f'{SRC}.TodoDocument', autospec=True)
    @patch.object(Reopen, 'new_description', new_callable=PropertyMock)
    @patch.object(Reopen, 'new_title', new_callable=PropertyMock)
    @patch.object(Reopen, 'node', new_callable=PropertyMock)
    @patch.object(Reopen, 'opened', new_callable=PropertyMock)
    @patch.object(Reopen, 'restored', new_callable=PropertyMock)
    @patch.object(Reopen, 'refuse_nested_changes', autospec=True)
    @patch.object(Reopen, 'checked', new_callable=PropertyMock)
    def test_document(
        t,
        checked: PropertyMock,
        refuse_nested_changes: MagicMock,
        restored: PropertyMock,
        opened: PropertyMock,
        node: PropertyMock,
        new_title: PropertyMock,
        new_description: PropertyMock,
        todo_document: MagicMock,
    ) -> None:
        checked.return_value = sentinel.checked
        child = child_node()
        child.note_indices = [4]
        opened.return_value = [parent_node(), child]
        node.return_value = child
        new_title.return_value = 'A checked title'
        new_description.return_value = None
        t.ro.ids = {1: '9o71lx', 3: 'zz01ab'}
        restored.return_value = MagicMock(spec=['text'])
        restored.return_value.text = 'the restored list'
        doc = todo_document.return_value

        with t.subTest('each closed task opens, then the named one changes'):
            ret = t.ro.document

            # The refusals of the fields and of a subtask come first, and
            # the edits go to a copy of the restored list.
            refuse_nested_changes.assert_called_once_with(t.ro)
            todo_document.assert_called_once_with('the restored list')
            t.assertEqual(
                doc.method_calls,
                [
                    call.mark_open(1),
                    call.mark_open(3),
                    call.set_field(3, 'ID', 'zz01ab'),
                    call.set_fields(3, sentinel.checked),
                    call.set_title(3, 'A checked title'),
                ],
            )
            t.assertIs(ret, doc)

        with t.subTest('a description replaces the description lines'):
            doc.reset_mock()
            new_title.return_value = None
            new_description.return_value = sentinel.lines

            _ = t.ro.document

            t.assertEqual(
                doc.method_calls[-2:],
                [
                    call.set_fields(3, sentinel.checked),
                    call.set_description(node.return_value, sentinel.lines),
                ],
            )

    @patch.object(Reopen, 'node', new_callable=PropertyMock)
    @patch.object(Reopen, 'edit', new_callable=PropertyMock)
    def test_checked(t, edit: PropertyMock, node: PropertyMock) -> None:
        edit.return_value = MagicMock(spec=['changed', 'changes'])
        edited = edit.return_value
        node.return_value = parent_node()

        with t.subTest('the named fields that change the task'):
            edited.changed = {'P': '5'}

            ret = t.ro.checked

            edited.changes.assert_called_once_with(node.return_value)
            t.assertIs(ret, edited.changes.return_value)

        with t.subTest('none, where no field is named: the task is not read'):
            edited.changes.reset_mock()
            node.reset_mock()
            edited.changed = {}

            ret = t.ro.checked

            edited.changes.assert_not_called()
            node.assert_not_called()
            t.assertEqual(ret, {})

    @patch(f'{SRC}.SuppliedEdit', autospec=True)
    def test_edit(t, supplied_edit: MagicMock) -> None:
        ret = t.ro.edit
        # The named values, read against the day of the task.
        supplied_edit.assert_called_once_with(
            {'P': '5'}, 'A new title', None, TODAY
        )
        t.assertIs(ret, supplied_edit.return_value)

    @patch(f'{SRC}.StreamSelection', autospec=True)
    @patch.object(Reopen, 'refuse_checklist_item', autospec=True)
    @patch.object(Reopen, 'streams', new_callable=PropertyMock)
    def test_stream(
        t,
        streams: PropertyMock,
        refuse_checklist_item: MagicMock,
        stream_selection: MagicMock,
    ) -> None:
        closed = Mock(spec=['closed'], closed=True)
        still_open = Mock(spec=['closed'], closed=False)
        streams.return_value = [still_open, closed]
        selection = stream_selection.return_value

        with t.subTest('the closed stream the selector names'):
            selection.candidates = [sentinel.candidate]

            ret = t.ro.stream

            stream_selection.assert_called_once_with([closed], 'a selector')
            refuse_checklist_item.assert_not_called()
            t.assertIs(ret, selection.stream)

        with t.subTest('none: a checklist item, then no task at all'):
            selection.candidates = []

            with t.assertRaises(Exception) as caught:
                _ = t.ro.stream

            refuse_checklist_item.assert_called_once_with(t.ro)
            t.assertEqual(
                str(caught.exception),
                "no open task matches 'a selector'",
            )

    @patch(f'{SRC}.TaskStream', autospec=True)
    @patch.object(Reopen, 'journal', new_callable=PropertyMock)
    def test_streams(t, journal: PropertyMock, task_stream: MagicMock) -> None:
        journal.return_value = Mock(spec=['streams'])
        journal.return_value.streams = {
            'task/aa': sentinel.aa_events,
            'task/bb': sentinel.bb_events,
        }
        task_stream.side_effect = [sentinel.aa, sentinel.bb]

        ret = t.ro.streams

        t.assertEqual(ret, [sentinel.aa, sentinel.bb])
        t.assertEqual(
            task_stream.call_args_list,
            [
                call('task/aa', sentinel.aa_events, sentinel.zone),
                call('task/bb', sentinel.bb_events, sentinel.zone),
            ],
        )

    @patch(f'{SRC}.Journal', autospec=True)
    def test_journal(t, journal: MagicMock) -> None:
        # Two reads: one journal answers every stream the reopen reads.
        ret = t.ro.journal
        t.assertIs(ret, journal.return_value)

        again = t.ro.journal
        t.assertIs(again, ret)
        journal.assert_called_once_with(SOURCE)

    @patch.object(Reopen, 'streams', new_callable=PropertyMock)
    def test_refuse_checklist_item(t, streams: PropertyMock) -> None:
        streams.return_value = [
            Mock(
                spec=['task_id', 'checklist_titles'],
                task_id='ab12cd',
                checklist_titles=['Print A Selector'],
            ),
            Mock(
                spec=['task_id', 'checklist_titles'],
                task_id='zz99yy',
                checklist_titles=['Water'],
            ),
            Mock(
                spec=['task_id', 'checklist_titles'],
                task_id='cc03ef',
                checklist_titles=['Find a selector'],
            ),
        ]

        with t.subTest('the owner of each item whose title holds it'):
            with t.assertRaises(ValueError) as caught:
                t.ro.refuse_checklist_item()

            t.assertEqual(
                str(caught.exception),
                "'a selector' names a checklist item of [ID:ab12cd], "
                '[ID:cc03ef]: a checklist item opens with its task, not on '
                'its own',
            )

        with t.subTest('no item holds it: no refusal'):
            t.task.selector = 'nothing'
            t.ro.refuse_checklist_item()

    @patch.object(Reopen, 'edit', new_callable=PropertyMock)
    @patch.object(Reopen, 'stream', new_callable=PropertyMock)
    def test_refuse_nested_changes(
        t,
        stream: PropertyMock,
        edit: PropertyMock,
    ) -> None:
        stream.return_value = Mock(spec=['nested', 'title'])
        stream.return_value.title = 'A subtask'
        edit.return_value = MagicMock(spec=['refuse_root_fields'])
        refuse_root_fields = edit.return_value.refuse_root_fields

        with t.subTest('a top-level task takes any change'):
            stream.return_value.nested = False
            t.ro.list_name = 'another-list'

            t.ro.refuse_nested_changes()

            refuse_root_fields.assert_not_called()

        with t.subTest('a subtask takes no list'):
            stream.return_value.nested = True

            with t.assertRaises(ValueError) as caught:
                t.ro.refuse_nested_changes()

            t.assertEqual(
                str(caught.exception),
                "'A subtask' is a subtask: --list moves a top-level task, "
                'and its subtasks with it',
            )

        with t.subTest('and no field the top-level task owns'):
            t.ro.list_name = None
            t.ro.refuse_nested_changes()
            refuse_root_fields.assert_called_once_with()

    @patch(f'{SRC}.NamedList', autospec=True)
    @patch.object(Reopen, 'record', new_callable=PropertyMock)
    @patch.object(Reopen, 'held', new_callable=PropertyMock)
    def test_path(
        t,
        held: PropertyMock,
        record: PropertyMock,
        named_list: MagicMock,
    ) -> None:
        record.return_value = Mock(spec=['list_name'], list_name='a-list')

        with t.subTest('the list that holds the line of a subtask'):
            held.return_value = LIST_PATH
            ret = t.ro.path
            t.assertIs(ret, LIST_PATH)

        held.return_value = None
        cases = {
            'the list the reopen names': ('another-list', 'another-list'),
            'or else the list the record names': (None, 'a-list'),
        }
        for name, (list_name, expected) in cases.items():
            with t.subTest(name):
                named_list.reset_mock()
                t.ro.__dict__.pop('path', None)
                t.ro.list_name = list_name

                ret = t.ro.path

                named_list.assert_called_once_with(SOURCE, expected)
                t.assertIs(ret, named_list.return_value.path)

    @patch.object(Reopen, 'stream', new_callable=PropertyMock)
    def test_held(t, stream: PropertyMock) -> None:
        stream.return_value = Mock(spec=['nested', 'task_id'])
        stream.return_value.task_id = 'cc03ef'
        done = child_node()
        done.done, done.fields = True, {'LOE': '2', 'ID': 'cc03ef'}
        parent = parent_node()
        parent.children = [done]
        # The lists as the selection read them, each beside its path.
        t.task.selection = Mock(spec=['lists'])
        held = [[parent], [parent, done]]
        t.task.selection.lists = [
            (LIST_PATH, Mock(spec=['ancestries'], ancestries=[])),
            (ANOTHER_PATH, Mock(spec=['ancestries'], ancestries=held)),
        ]

        with t.subTest('the list that holds the closed line, at any depth'):
            stream.return_value.nested = True
            ret = t.ro.held
            t.assertIs(ret, ANOTHER_PATH)

        with t.subTest('an open line with the id is not a closed one'):
            done.done = False
            ret = t.ro.held
            t.assertIsNone(ret)

        with t.subTest('a top-level task is never looked for'):
            # A selection read here would raise: it holds no lists.
            t.task.selection = Mock(spec=[])
            stream.return_value.nested = False

            ret = t.ro.held

            t.assertIsNone(ret)

    @patch(f'{SRC}.RecordedTask', autospec=True)
    @patch.object(Reopen, 'parent', new_callable=PropertyMock)
    @patch.object(Reopen, 'streams', new_callable=PropertyMock)
    @patch.object(Reopen, 'stream', new_callable=PropertyMock)
    def test_record(
        t,
        stream: PropertyMock,
        streams: PropertyMock,
        parent: PropertyMock,
        recorded_task: MagicMock,
    ) -> None:
        stream.return_value = Mock(spec=['nested', 'task_id', 'title'])
        stream.return_value.task_id = 'cc03ef'
        stream.return_value.title = 'A subtask'
        holder = a_record(sentinel.holder_snapshot)
        other = a_record(sentinel.other_snapshot)
        nested = a_record(sentinel.nested_snapshot, nested=True)
        still_open = a_record(sentinel.open_snapshot, closed=False)
        streams.return_value = [other, nested, still_open, holder]
        recorded_task.side_effect = lambda snapshot, depth: Mock(
            spec=['ids'],
            ids={'cc03ef'} if snapshot is sentinel.holder_snapshot else set(),
        )
        parent.return_value = '[ID:pf11pf]'

        with t.subTest('a top-level task is its own record'):
            stream.return_value.nested = False
            ret = t.ro.record
            t.assertIs(ret, stream.return_value)

        with t.subTest('a subtask: the closed top-level record that holds it'):
            stream.return_value.nested = True
            ret = t.ro.record
            t.assertIs(ret, holder)

        with t.subTest('no record holds it: refused, the parent named'):
            streams.return_value = [other]

            with t.assertRaises(ValueError) as caught:
                _ = t.ro.record

            t.assertEqual(
                str(caught.exception),
                "'A subtask' is a subtask of [ID:pf11pf], and no list and "
                'no record of a closed task holds its line',
            )

    @patch.object(Reopen, 'stream', new_callable=PropertyMock)
    def test_parent(t, stream: PropertyMock) -> None:
        stream.return_value = Mock(spec=['parent_id', 'own'])
        stream.return_value.own = [
            {
                'payload': {
                    'snapshot': {'title': 'A subtask'},
                    'ancestry': 'A task > A step > A subtask',
                },
            },
        ]

        with t.subTest('the id its add names'):
            stream.return_value.parent_id = 'pf11pf'
            ret = t.ro.parent
            t.assertEqual(ret, '[ID:pf11pf]')

        with t.subTest('or else the path above it'):
            stream.return_value.parent_id = None
            ret = t.ro.parent
            t.assertEqual(ret, "'A task > A step'")

    @patch(f'{SRC}.TodoDocument', autospec=True)
    @patch.object(Reopen, 'recorded', new_callable=PropertyMock)
    @patch.object(Reopen, 'held', new_callable=PropertyMock)
    def test_restored(
        t,
        held: PropertyMock,
        recorded: PropertyMock,
        todo_document: MagicMock,
    ) -> None:
        path = MagicMock(spec=Path)
        path.read_text.return_value = 'the list as read'
        t.ro.path = path
        recorded.return_value = MagicMock(spec=['lines'])
        recorded.return_value.lines = ['the task line', 'its child line']
        doc = todo_document.return_value

        with t.subTest('the recorded block, after the last open entry'):
            held.return_value = None

            ret = t.ro.restored

            todo_document.assert_called_once_with('the list as read')
            t.assertEqual(
                doc.method_calls,
                [
                    call.append_open('the task line'),
                    call.append_open('its child line'),
                ],
            )
            t.assertIs(ret, doc)

        with t.subTest('a list that holds the line: the list as read'):
            t.ro.__dict__.pop('restored', None)
            doc.reset_mock()
            held.return_value = path

            ret = t.ro.restored

            t.assertEqual(doc.method_calls, [])
            t.assertIs(ret, doc)

    @patch(f'{SRC}.RecordedTask', autospec=True)
    @patch.object(Reopen, 'record', new_callable=PropertyMock)
    def test_recorded(
        t, record: PropertyMock, recorded_task: MagicMock
    ) -> None:
        record.return_value = Mock(spec=['snapshot', 'task_id'])
        record.return_value.task_id = 'ab12cd'
        snapshot = {'title': 'A task', 'done': False, 'fields': {'P': '2'}}

        with t.subTest('a record with no id takes the id of its stream'):
            record.return_value.snapshot = snapshot

            ret = t.ro.recorded

            recorded_task.assert_called_once_with(
                {**snapshot, 'fields': {'P': '2', 'ID': 'ab12cd'}},
                0,
            )
            t.assertIs(ret, recorded_task.return_value)

        with t.subTest('a record with an id keeps it'):
            recorded_task.reset_mock()
            kept = {**snapshot, 'fields': {'ID': 'ab12cd', 'P': '2'}}
            record.return_value.snapshot = kept

            _ = t.ro.recorded

            recorded_task.assert_called_once_with(kept, 0)

    @patch.object(Reopen, 'chains', new_callable=PropertyMock)
    @patch.object(Reopen, 'stream', new_callable=PropertyMock)
    def test_ancestry(t, stream: PropertyMock, chains: PropertyMock) -> None:
        parent = parent_node()
        child = child_node()
        child.fields = {'LOE': '2', 'ID': 'cc03ef'}
        chains.return_value = {1: [parent], 3: [parent, child]}
        stream.return_value = Mock(spec=['task_id'])

        cases = {
            'a top-level task alone': ('9o71lx', [parent]),
            'a subtask, below each task above it': ('cc03ef', [parent, child]),
        }
        for name, (task_id, expected) in cases.items():
            with t.subTest(name):
                stream.return_value.task_id = task_id
                ret = t.ro.ancestry
                t.assertEqual(ret, expected)

    @patch.object(Reopen, '_breadth_first', new_callable=PropertyMock)
    def test_chains(t, breadth_first: PropertyMock) -> None:
        parent = parent_node()
        child = child_node()
        bare = bare_node()
        bare.raw_index = 6
        breadth_first.return_value = [[parent], [bare], [parent, child]]

        ret = t.ro.chains

        # Each task by its line, below every task above it, in the order
        # read.
        t.assertEqual(
            list(ret.items()),
            [(1, [parent]), (6, [bare]), (3, [parent, child])],
        )

    @patch.object(Reopen, 'restored', new_callable=PropertyMock)
    def test_breadth_first(t, restored: PropertyMock) -> None:
        parent = parent_node()
        child = child_node()
        grandchild = grandchild_node()
        bare = bare_node()
        bare.raw_index = 6
        # Every task of the list with its ancestry, in file order.
        restored.return_value = Mock(spec=['ancestries'])
        restored.return_value.ancestries = [
            [parent],
            [parent, child],
            [parent, child, grandchild],
            [bare],
        ]

        ret = t.ro._breadth_first

        # Pins the current match; a ruling may change it. Shallowest
        # first: `ancestry` takes the first task with the id.
        t.assertEqual(
            ret,
            [[parent], [bare], [parent, child], [parent, child, grandchild]],
        )

    @patch.object(Reopen, 'subtasks', new_callable=PropertyMock)
    @patch.object(Reopen, 'ancestry', new_callable=PropertyMock)
    def test_opened(t, ancestry: PropertyMock, subtasks: PropertyMock) -> None:
        parent, child, grandchild = (
            parent_node(),
            done_child_node(),
            grandchild_node(),
        )
        grandchild.done = True
        ancestry.return_value = [parent, child, grandchild]
        subtasks.return_value = [sentinel.subtask]

        with t.subTest('the closed tasks alone; an open one stays as it is'):
            ret = t.ro.opened
            t.assertEqual(ret, [child, grandchild])

        with t.subTest('with its subtasks, each closed one below it too'):
            t.ro.with_subtasks = True
            ret = t.ro.opened
            t.assertEqual(ret, [child, grandchild, sentinel.subtask])

    @patch.object(Reopen, 'chains', new_callable=PropertyMock)
    @patch.object(Reopen, 'node', new_callable=PropertyMock)
    def test_subtasks(t, node: PropertyMock, chains: PropertyMock) -> None:
        parent = parent_node()
        parent.done = True
        closed, still_open = done_child_node(), child_node()
        item = checklist_node()
        item.raw_index, item.done = 6, True
        below = grandchild_node()
        below.done = True
        elsewhere = done_child_node()
        elsewhere.raw_index = 9
        other = bare_node()
        other.raw_index = 8
        # Breadth first, as `chains` builds them: not in file order.
        chains.return_value = {
            1: [parent],
            8: [other],
            5: [parent, closed, below],
            3: [parent, still_open],
            6: [parent, item],
            4: [parent, closed],
            9: [other, elsewhere],
        }
        node.return_value = parent

        ret = t.ro.subtasks

        # Closed, below the task, at any depth, in file order; neither
        # an open subtask nor a checklist item.
        t.assertEqual(ret, [closed, below])

    @patch(f'{SRC}.new_task_id', autospec=True)
    @patch.object(Reopen, 'opened', new_callable=PropertyMock)
    def test_ids(t, opened: PropertyMock, new_task_id: MagicMock) -> None:
        # Two reads: an id drawn at random must name one task.
        opened.return_value = [parent_node(), done_child_node()]
        new_task_id.return_value = 'zz01ab'

        ret = t.ro.ids
        t.assertEqual(ret, {1: '9o71lx', 4: 'zz01ab'})

        again = t.ro.ids
        t.assertIs(again, ret)
        new_task_id.assert_called_once_with()

    @patch.object(Reopen, 'ancestry', new_callable=PropertyMock)
    def test_node(t, ancestry: PropertyMock) -> None:
        ancestry.return_value = [sentinel.parent, sentinel.named]
        ret = t.ro.node
        t.assertIs(ret, sentinel.named)

    @patch.object(Reopen, 'node', new_callable=PropertyMock)
    @patch.object(Reopen, 'edit', new_callable=PropertyMock)
    def test_new_title(t, edit: PropertyMock, node: PropertyMock) -> None:
        edit.return_value = MagicMock(spec=['checked_title', 'new_title'])
        edited = edit.return_value
        node.return_value = parent_node()

        with t.subTest('the title that changes the task'):
            edited.checked_title = 'A new title'

            ret = t.ro.new_title

            edited.new_title.assert_called_once_with(node.return_value)
            t.assertIs(ret, edited.new_title.return_value)

        with t.subTest('none, where none is named: the task is not read'):
            edited.new_title.reset_mock()
            node.reset_mock()
            edited.checked_title = None

            ret = t.ro.new_title

            edited.new_title.assert_not_called()
            node.assert_not_called()
            t.assertIsNone(ret)

    @patch.object(Reopen, 'node', new_callable=PropertyMock)
    @patch.object(Reopen, 'edit', new_callable=PropertyMock)
    def test_new_description(
        t,
        edit: PropertyMock,
        node: PropertyMock,
    ) -> None:
        edit.return_value = MagicMock(
            spec=['checked_description', 'new_description']
        )
        edited = edit.return_value
        node.return_value = parent_node()

        with t.subTest('the description lines that change the task'):
            edited.checked_description = ['A line.']

            ret = t.ro.new_description

            edited.new_description.assert_called_once_with(node.return_value)
            t.assertIs(ret, edited.new_description.return_value)

        with t.subTest('none, where none is named: the task is not read'):
            edited.new_description.reset_mock()
            node.reset_mock()
            edited.checked_description = None

            ret = t.ro.new_description

            edited.new_description.assert_not_called()
            node.assert_not_called()
            t.assertIsNone(ret)

    @patch.object(Reopen, 'node', new_callable=PropertyMock)
    @patch.object(Reopen, 'document', new_callable=PropertyMock)
    def test_entry(t, document: PropertyMock, node: PropertyMock) -> None:
        document.return_value = MagicMock(spec=['lines'])
        document.return_value.lines = [OPEN_HEADING, 'the line as written']
        node.return_value = parent_node()

        ret = t.ro.entry

        t.assertEqual(ret, 'the line as written')

    def test_entries(t) -> None:
        ret = t.ro.entries
        # A reopen logs no completed-log record.
        t.assertEqual(ret, [])

    @patch(f'{SRC}.OpenedTask', autospec=True)
    @patch.object(Reopen, '_paths', new_callable=PropertyMock)
    @patch.object(Reopen, 'delta', new_callable=PropertyMock)
    @patch.object(Reopen, 'list_left', new_callable=PropertyMock)
    @patch.object(Reopen, 'ancestry', new_callable=PropertyMock)
    def test_events(
        t,
        ancestry: PropertyMock,
        list_left: PropertyMock,
        delta: PropertyMock,
        paths: PropertyMock,
        opened_task: MagicMock,
    ) -> None:
        parent, child = parent_node(), done_child_node()
        parent.done = True
        ancestry.return_value = [parent, child]
        list_left.return_value = 'a-list'
        delta.return_value = {'P': ['4', '5']}
        paths.return_value = [sentinel.top, sentinel.below]
        t.ro.ids = {1: '9o71lx', 4: 'cc03ef'}
        opened_task.side_effect = [
            Mock(spec=['event'], event=sentinel.top_event),
            Mock(spec=['event'], event=sentinel.named_event),
        ]
        t.ro.attrs = {'cost': '45.00'}

        ret = t.ro.events

        # One opening a closed task, outermost first. The named task
        # carries the changes and the attributes.
        t.assertEqual(
            opened_task.call_args_list,
            [
                call(sentinel.top, '9o71lx', 'a-list', None, None),
                call(
                    sentinel.below,
                    'cc03ef',
                    'a-list',
                    {'P': ['4', '5']},
                    {'cost': '45.00'},
                ),
            ],
        )
        t.assertEqual(ret, [sentinel.top_event, sentinel.named_event])

    @patch(f'{SRC}.Ancestry', autospec=True)
    @patch.object(Reopen, 'chains', new_callable=PropertyMock)
    @patch.object(Reopen, 'opened', new_callable=PropertyMock)
    def test_paths(
        t,
        opened: PropertyMock,
        chains: PropertyMock,
        ancestry_class: MagicMock,
    ) -> None:
        parent, child = parent_node(), done_child_node()
        opened.return_value = [parent, child]
        chains.return_value = {1: [parent], 4: [parent, child]}
        ancestry_class.side_effect = [sentinel.top, sentinel.below]

        ret = t.ro._paths

        # The ancestry of each task the reopen opens, outermost first.
        t.assertEqual(
            ancestry_class.call_args_list,
            [call([parent]), call([parent, child])],
        )
        t.assertEqual(ret, [sentinel.top, sentinel.below])

    @patch.object(Reopen, 'path', new_callable=PropertyMock)
    @patch.object(Reopen, 'list_left', new_callable=PropertyMock)
    @patch.object(Reopen, 'edit', new_callable=PropertyMock)
    @patch.object(Reopen, 'checked', new_callable=PropertyMock)
    @patch.object(Reopen, 'node', new_callable=PropertyMock)
    def test_delta(
        t,
        node: PropertyMock,
        checked: PropertyMock,
        edit: PropertyMock,
        list_left: PropertyMock,
        path: PropertyMock,
    ) -> None:
        node.return_value = sentinel.node
        checked.return_value = sentinel.checked
        edit.return_value = MagicMock(spec=['delta'])
        edit_delta = edit.return_value.delta
        list_left.return_value = 'a-list'
        path.return_value = LIST_PATH

        with t.subTest('the values written, the title and the description'):
            edit_delta.return_value = {'P': ['4', '5']}

            ret = t.ro.delta

            edit_delta.assert_called_once_with(sentinel.node, sentinel.checked)
            t.assertEqual(ret, {'P': ['4', '5']})

        with t.subTest('another list, against the list it left'):
            edit_delta.return_value = {}
            path.return_value = ANOTHER_PATH
            ret = t.ro.delta
            t.assertEqual(ret, {'list': ['a-list', 'another-list']})

    @patch.object(Reopen, 'record', new_callable=PropertyMock)
    @patch.object(Reopen, 'held', new_callable=PropertyMock)
    def test_list_left(t, held: PropertyMock, record: PropertyMock) -> None:
        record.return_value = Mock(spec=['list_name'], list_name='a-list')

        with t.subTest('the list that holds the line of a subtask'):
            held.return_value = ANOTHER_PATH
            ret = t.ro.list_left
            t.assertEqual(ret, 'another-list')

        with t.subTest('or else the list the record names'):
            held.return_value = None
            ret = t.ro.list_left
            t.assertEqual(ret, 'a-list')


def a_record(
    snapshot: object, closed: bool = True, nested: bool = False
) -> Mock:
    """A stand-in for a stream whose last snapshot is `snapshot`."""
    record = Mock(spec=['closed', 'nested', 'snapshot'])
    record.closed, record.nested, record.snapshot = closed, nested, snapshot
    return record


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
                {LIST_PATH: sentinel.text},
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

    @patch.object(Completion, 'refuse_repeating_subtask', autospec=True)
    @patch.object(Completion, 'document', new_callable=PropertyMock)
    def test_text(
        t,
        document: PropertyMock,
        refuse_repeating_subtask: MagicMock,
    ) -> None:
        document.return_value = MagicMock(spec=['text'])

        with t.subTest('the text of the document, once nothing refuses it'):
            ret = t.co.text

            refuse_repeating_subtask.assert_called_once_with(t.co)
            t.assertIs(ret, document.return_value.text)

        with t.subTest('a refused completion reads no document'):
            document.reset_mock()
            refuse_repeating_subtask.side_effect = ValueError('refused')

            with t.assertRaises(ValueError):
                _ = t.co.text

            document.assert_not_called()

    @patch.object(TaskNode, 'repeating_subtasks', new_callable=PropertyMock)
    def test_refuse_repeating_subtask(
        t,
        repeating_subtasks: PropertyMock,
    ) -> None:
        t.task.node = t.parent

        with t.subTest('a task with no repeating subtask'):
            # Nothing to refuse: the call returns.
            repeating_subtasks.return_value = []
            t.co.refuse_repeating_subtask()

        with t.subTest('the first repeating subtask, by its title and id'):
            t.child.fields = {'REPEAT': '7d', 'ID': 'zz01ab'}
            repeating_subtasks.return_value = [t.child, grandchild_node()]

            with t.assertRaises(ValueError) as caught:
                t.co.refuse_repeating_subtask()

            t.assertEqual(
                str(caught.exception),
                "'A task' has a repeating subtask, 'A subtask of it' "
                '[ID:zz01ab]: remove its repeat first with update zz01ab '
                '--repeat None',
            )

        with t.subTest('one with no id, by its title alone'):
            t.child.fields = {'REPEAT': '7d'}

            with t.assertRaises(ValueError) as caught:
                t.co.refuse_repeating_subtask()

            t.assertEqual(
                str(caught.exception),
                "'A task' has a repeating subtask, 'A subtask of it': "
                "remove its repeat first with update 'A subtask of it' "
                '--repeat None',
            )

        with t.subTest('a scratch, which completes nothing'):
            # Nothing to refuse: the call returns.
            t.co.scratched = True
            t.co.refuse_repeating_subtask()

    @patch(f'{SRC}.TodoDocument', autospec=True)
    def test_document(t, todo_document: MagicMock) -> None:
        t.co.lines = MagicMock(spec=['stamps', 'checked_off', 'dropped'])
        t.co.lines.stamps = {3: {'ID': 'zz01ab'}, 1: {'ID': '9o71lx'}}
        t.co.lines.checked_off = [3, 1]
        t.co.lines.dropped = {5}
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

    @patch(f'{SRC}.CompletionLines', autospec=True)
    def test_lines(t, completion_lines: MagicMock) -> None:
        # Two reads: the lines draw new ids, which the events must name.
        ret = t.co.lines
        again = t.co.lines

        completion_lines.assert_called_once_with(t.task.ancestry, TODAY, False)
        t.assertIs(ret, completion_lines.return_value)
        t.assertIs(again, ret)

    def test_completed_on(t) -> None:
        ret = t.co.completed_on
        t.assertIs(ret, t.task.today)

    @patch(f'{SRC}.LogEntry', autospec=True)
    @patch.object(Completion, 'completions', new_callable=PropertyMock)
    def test_entries(
        t,
        completions: PropertyMock,
        log_entry: MagicMock,
    ) -> None:
        log_entry.return_value.text = 'a record'
        below = MagicMock(spec=['ancestry'])
        below.ancestry = ancestry_of(t.parent, t.child)
        top = MagicMock(spec=['ancestry'])
        top.ancestry = ancestry_of(t.parent)

        with t.subTest('one record a task finished, deepest first'):
            completions.return_value = [below, top]

            ret = t.co.entries

            t.assertEqual(
                log_entry.call_args_list,
                [call(LIST_PATH, below), call(LIST_PATH, top)],
            )
            t.assertEqual(ret, ['a record', 'a record'])

        with t.subTest('a checklist item is not logged'):
            log_entry.reset_mock()
            below.ancestry = ancestry_of(t.parent, checklist_node())

            ret = t.co.entries

            t.assertEqual(log_entry.call_args_list, [call(LIST_PATH, top)])
            t.assertEqual(ret, ['a record'])

    @patch(f'{SRC}.TaskCompletion', autospec=True)
    @patch.object(Completion, 'completed_on', new_callable=PropertyMock)
    def test_completions(
        t,
        completed_on: PropertyMock,
        task_completion: MagicMock,
    ) -> None:
        below, top = ancestry_of(t.parent, t.child), ancestry_of(t.parent)
        lines = MagicMock(
            spec=['ancestries', 'recurrence', 'recurrence_fields']
        )
        lines.ancestries = [below, top]
        lines.recurrence_fields = sentinel.recurrence_fields
        t.co.lines = lines
        completed_on.return_value = GIVEN_DAY
        t.co.attrs = sentinel.attrs

        with t.subTest('one a task finished, deepest first'):
            lines.recurrence = None

            ret = t.co.completions

            # Only the task the caller named carries the attributes.
            t.assertEqual(
                task_completion.call_args_list,
                [
                    call(
                        below, {}, GIVEN_DAY, 'a-list', sentinel.attrs, False
                    ),
                    call(top, {}, GIVEN_DAY, 'a-list', None, False),
                ],
            )
            t.assertEqual(ret, [task_completion.return_value] * 2)

        with t.subTest('a recurrence takes the fields it gains'):
            task_completion.reset_mock()
            lines.recurrence = t.parent

            _ = t.co.completions

            t.assertEqual(
                task_completion.call_args_list,
                [
                    call(
                        below, {}, GIVEN_DAY, 'a-list', sentinel.attrs, False
                    ),
                    call(
                        top,
                        sentinel.recurrence_fields,
                        GIVEN_DAY,
                        'a-list',
                        None,
                        False,
                    ),
                ],
            )

        with t.subTest('the recurrence, whichever task it is'):
            task_completion.reset_mock()
            lines.recurrence = t.child

            _ = t.co.completions

            t.assertEqual(
                task_completion.call_args_list,
                [
                    call(
                        below,
                        sentinel.recurrence_fields,
                        GIVEN_DAY,
                        'a-list',
                        sentinel.attrs,
                        False,
                    ),
                    call(top, {}, GIVEN_DAY, 'a-list', None, False),
                ],
            )

        with t.subTest('a scratch marks each one scratched'):
            task_completion.reset_mock()
            lines.recurrence = None
            lines.ancestries = [below]
            t.co.scratched = True

            _ = t.co.completions

            task_completion.assert_called_once_with(
                below, {}, GIVEN_DAY, 'a-list', sentinel.attrs, True
            )

    @patch.object(TaskNode, 'refuse_attributes', autospec=True)
    @patch.object(Completion, '_closes', new_callable=PropertyMock)
    @patch.object(Completion, 'assignments', new_callable=PropertyMock)
    def test_events(
        t,
        assignments: PropertyMock,
        closes: PropertyMock,
        refuse_attributes: MagicMock,
    ) -> None:
        assignments.return_value = [sentinel.stamp]
        closes.return_value = [sentinel.close]
        t.co.attrs = sentinel.attrs

        with t.subTest('each id stamp, then each close'):
            ret = t.co.events

            refuse_attributes.assert_called_once_with(t.child, sentinel.attrs)
            t.assertEqual(ret, [sentinel.stamp, sentinel.close])

        with t.subTest('a refused attribute: nothing else is read'):
            assignments.reset_mock()
            closes.reset_mock()
            refuse_attributes.side_effect = ValueError('refused')

            with t.assertRaises(ValueError):
                _ = t.co.events

            assignments.assert_not_called()
            closes.assert_not_called()

    @patch.object(Completion, '_streams', new_callable=PropertyMock)
    @patch.object(Completion, 'completions', new_callable=PropertyMock)
    def test_closes(
        t,
        completions: PropertyMock,
        streams: PropertyMock,
    ) -> None:
        below = MagicMock(spec=['payload'])
        below.payload = sentinel.below
        top = MagicMock(spec=['payload'])
        top.payload = sentinel.top
        completions.return_value = [below, top]
        streams.return_value = ['task/zz01ab', 'task/9o71lx']

        with t.subTest('one TaskCompleted a completion, deepest first'):
            ret = t.co._closes
            t.assertEqual(
                ret,
                [
                    Event('TaskCompleted', 'task/zz01ab', sentinel.below),
                    Event('TaskCompleted', 'task/9o71lx', sentinel.top),
                ],
            )

        with t.subTest('a scratch: one TaskScratched each'):
            completions.return_value = [below]
            streams.return_value = ['task/zz01ab']
            t.co.scratched = True

            ret = t.co._closes

            t.assertEqual(
                ret,
                [Event('TaskScratched', 'task/zz01ab', sentinel.below)],
            )

    def test_kind(t) -> None:
        cases = {
            'a completion': (False, 'TaskCompleted'),
            'a scratch': (True, 'TaskScratched'),
        }
        for name, (scratched, expected) in cases.items():
            with t.subTest(name):
                t.co.scratched = scratched
                ret = t.co._kind
                t.assertEqual(ret, expected)

    @patch.object(Completion, 'completions', new_callable=PropertyMock)
    def test_streams(t, completions: PropertyMock) -> None:
        below = MagicMock(spec=['ancestry'])
        below.ancestry = ancestry_of(t.parent, t.child)
        top = MagicMock(spec=['ancestry'])
        top.ancestry = ancestry_of(t.parent)
        completions.return_value = [below, top]
        t.co.lines = MagicMock(spec=['ids'])
        t.co.lines.ids = {3: 'zz01ab', 1: '9o71lx'}

        ret = t.co._streams

        # The stream of each completion, by the id of its stream task.
        t.assertEqual(ret, ['task/zz01ab', 'task/9o71lx'])

    @patch(f'{SRC}.IdAssignment', autospec=True)
    def test_assignments(t, id_assignment: MagicMock) -> None:
        bare = bare_node()
        event = id_assignment.return_value.event
        lines = MagicMock(spec=['ancestries', 'stamps'])
        t.co.lines = lines

        with t.subTest('a stream with no id: its new id, on its own event'):
            # A checklist item lands on the stream of its parent.
            lines.ancestries = [
                ancestry_of(bare, checklist_node(), stream=bare),
            ]
            lines.stamps = {1: {'ID': 'zz01ab'}}

            ret = t.co.assignments

            id_assignment.assert_called_once_with(bare, 'zz01ab', 'a-list')
            t.assertEqual(ret, [event])

        with t.subTest('a stream whose id is empty counts as none'):
            id_assignment.reset_mock()
            empty = bare_node()
            empty.fields = {'P': '2', 'ID': ''}
            lines.ancestries = [
                ancestry_of(empty, checklist_node(), stream=empty),
            ]
            lines.stamps = {1: {'ID': 'ee04gh'}}

            ret = t.co.assignments

            id_assignment.assert_called_once_with(empty, 'ee04gh', 'a-list')
            t.assertEqual(ret, [event])

        with t.subTest('a stream that keeps its id: none'):
            id_assignment.reset_mock()
            lines.ancestries = [
                ancestry_of(t.parent, checklist_node(), stream=t.parent),
            ]
            lines.stamps = {1: {'ID': '9o71lx'}}

            ret = t.co.assignments

            id_assignment.assert_not_called()
            t.assertEqual(ret, [])

        with t.subTest('a recurrence: its new id beside its due date'):
            id_assignment.reset_mock()
            lines.ancestries = [ancestry_of(bare)]
            lines.stamps = {1: {'DUE': '2026-08-15', 'ID': 'rr01ab'}}

            ret = t.co.assignments

            id_assignment.assert_called_once_with(bare, 'rr01ab', 'a-list')
            t.assertEqual(ret, [event])

        with t.subTest('a finished block that goes: none'):
            id_assignment.reset_mock()
            lines.stamps = {}

            ret = t.co.assignments

            id_assignment.assert_not_called()
            t.assertEqual(ret, [])

        with t.subTest('each stream given an id, deepest first'):
            id_assignment.reset_mock()
            lines.ancestries = [
                ancestry_of(bare, t.child),
                ancestry_of(bare),
            ]
            lines.stamps = {
                3: {'ID': 'cc03ef'},
                1: {'ID': 'pp02cd'},
            }

            ret = t.co.assignments

            t.assertEqual(
                id_assignment.call_args_list,
                [
                    call(t.child, 'cc03ef', 'a-list'),
                    call(bare, 'pp02cd', 'a-list'),
                ],
            )
            t.assertEqual(ret, [event, event])


class AnnotationTests(TestCase):
    """Unit tests for battodo.mutate.Annotation."""

    def setUp(t) -> None:
        t.parent = parent_node()
        t.task = named_task(t.parent)
        t.an = Annotation(t.task, {'note': 'a note'})

    @patch(f'{SRC}.Changeset', autospec=True)
    @patch.object(Annotation, 'events', new_callable=PropertyMock)
    @patch.object(Annotation, 'entries', new_callable=PropertyMock)
    @patch.object(Annotation, 'text', new_callable=PropertyMock)
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
            t.an.write()

            changeset.assert_called_once_with(
                {LIST_PATH: sentinel.text},
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
                t.an.write()

            entries.assert_not_called()
            changeset.assert_not_called()

    def test_source(t) -> None:
        ret = t.an.source
        t.assertIs(ret, t.task.source)

    def test_path(t) -> None:
        ret = t.an.path
        t.assertIs(ret, t.task.path)

    @patch.object(Annotation, 'document', new_callable=PropertyMock)
    def test_text(t, document: PropertyMock) -> None:
        document.return_value = MagicMock(spec=['text'])
        ret = t.an.text
        t.assertIs(ret, document.return_value.text)

    @patch(f'{SRC}.TodoDocument', autospec=True)
    @patch.object(Annotation, 'stamped', new_callable=PropertyMock)
    @patch.object(Annotation, 'refuse_empty', autospec=True)
    def test_document(
        t,
        refuse_empty: MagicMock,
        stamped: PropertyMock,
        todo_document: MagicMock,
    ) -> None:
        stamped.return_value = False
        doc = todo_document.return_value

        with t.subTest('a task with an id: the list as read'):
            ret = t.an.document

            refuse_empty.assert_called_once_with(t.an)
            todo_document.assert_called_once_with(t.task.doc.text)
            t.assertEqual(doc.method_calls, [])
            t.assertIs(ret, doc)

        with t.subTest('a task with no id is stamped'):
            stamped.return_value = True
            t.an.task_id = 'pp02cd'

            _ = t.an.document

            t.assertEqual(
                doc.method_calls, [call.set_field(1, 'ID', 'pp02cd')]
            )

        with t.subTest('an empty note is refused before the task is read'):
            todo_document.reset_mock()
            stamped.reset_mock()
            refuse_empty.side_effect = ValueError('nothing to note')

            with t.assertRaisesRegex(ValueError, 'nothing to note'):
                _ = t.an.document

            stamped.assert_not_called()
            todo_document.assert_not_called()

    def test_refuse_empty(t) -> None:
        with t.subTest('a note that carries an attribute'):
            # Nothing to refuse: the call returns.
            t.an.refuse_empty()

        with t.subTest('a note that carries nothing'):
            t.an.attrs = {}

            with t.assertRaises(ValueError) as caught:
                t.an.refuse_empty()

            t.assertEqual(
                str(caught.exception),
                'nothing to note: give a note or an attribute',
            )

    @patch.object(Annotation, 'node', new_callable=PropertyMock)
    def test_stamped(t, node: PropertyMock) -> None:
        with t.subTest('a task with an id is not stamped'):
            node.return_value = t.parent
            ret = t.an.stamped
            t.assertFalse(ret)

        with t.subTest('a task with no id is'):
            node.return_value = bare_node()
            ret = t.an.stamped
            t.assertTrue(ret)

        with t.subTest('a task whose id is empty is too'):
            node.return_value.fields = {'P': '2', 'ID': ''}
            ret = t.an.stamped
            t.assertTrue(ret)

    @patch.object(TaskNode, 'refuse_attributes', autospec=True)
    def test_node(t, refuse_attributes: MagicMock) -> None:
        with t.subTest('the task the selector names'):
            ret = t.an.node

            refuse_attributes.assert_called_once_with(
                t.parent,
                {'note': 'a note'},
            )
            t.assertIs(ret, t.parent)

        with t.subTest('a checklist item is refused'):
            refuse_attributes.side_effect = ValueError('a checklist item')
            with t.assertRaisesRegex(ValueError, 'a checklist item'):
                _ = t.an.node

    @patch(f'{SRC}.new_task_id', autospec=True)
    @patch.object(Annotation, 'node', new_callable=PropertyMock)
    def test_task_id(t, node: PropertyMock, new_task_id: MagicMock) -> None:
        with t.subTest('the id the task carries'):
            node.return_value = t.parent
            ret = t.an.task_id
            t.assertEqual(ret, '9o71lx')

        with t.subTest('a new one, drawn once, where it carries none'):
            # Two reads: an id drawn at random must name one task.
            t.an = Annotation(t.task, {'note': 'a note'})
            node.return_value = bare_node()

            ret = t.an.task_id
            t.assertIs(ret, new_task_id.return_value)

            again = t.an.task_id
            t.assertIs(again, ret)
            new_task_id.assert_called_once_with()

    @patch.object(Annotation, 'document', new_callable=PropertyMock)
    def test_entry(t, document: PropertyMock) -> None:
        document.return_value = MagicMock(spec=['lines'])
        document.return_value.lines = [OPEN_HEADING, 'the line as written']

        ret = t.an.entry

        t.assertEqual(ret, 'the line as written')

    def test_entries(t) -> None:
        ret = t.an.entries
        # A note logs no completed-log record.
        t.assertEqual(ret, [])

    @patch.object(Annotation, 'payload', new_callable=PropertyMock)
    @patch.object(Annotation, 'stamp', new_callable=PropertyMock)
    @patch.object(Annotation, 'stamped', new_callable=PropertyMock)
    def test_events(
        t,
        stamped: PropertyMock,
        stamp: PropertyMock,
        payload: PropertyMock,
    ) -> None:
        stamped.return_value = False
        stamp.return_value = sentinel.stamp
        payload.return_value = sentinel.payload
        t.an.task_id = '9o71lx'
        annotated = Event('TaskAnnotated', 'task/9o71lx', sentinel.payload)

        with t.subTest('one TaskAnnotated, on the stream of the task'):
            ret = t.an.events
            t.assertEqual(ret, [annotated])

        with t.subTest('the stamp of a task with no id goes first'):
            stamped.return_value = True
            ret = t.an.events
            t.assertEqual(ret, [sentinel.stamp, annotated])

    @patch(f'{SRC}.IdAssignment', autospec=True)
    def test_stamp(t, id_assignment: MagicMock) -> None:
        t.an.task_id = 'pp02cd'

        ret = t.an.stamp

        id_assignment.assert_called_once_with(t.parent, 'pp02cd', 'a-list')
        t.assertIs(ret, id_assignment.return_value.event)

    @patch.object(TaskNode, 'listed_snapshot', autospec=True)
    @patch.object(Annotation, 'ancestry', new_callable=PropertyMock)
    @patch.object(Annotation, 'nested', new_callable=PropertyMock)
    def test_payload(
        t,
        nested: PropertyMock,
        ancestry: PropertyMock,
        snapshot: MagicMock,
    ) -> None:
        nested.return_value = False
        ancestry.return_value = MagicMock(spec=['path'])
        ancestry.return_value.path = 'a path'
        snapshot.return_value = sentinel.snapshot

        with t.subTest('the state of the task and the attributes, no delta'):
            ret = t.an.payload

            snapshot.assert_called_once_with(t.parent, 'a-list')
            t.assertEqual(
                ret,
                {'snapshot': sentinel.snapshot, 'attrs': {'note': 'a note'}},
            )

        with t.subTest('a subtask records where it sits'):
            nested.return_value = True
            ret = t.an.payload
            t.assertEqual(
                ret,
                {
                    'snapshot': sentinel.snapshot,
                    'ancestry': 'a path',
                    'attrs': {'note': 'a note'},
                },
            )

    def test_nested(t) -> None:
        with t.subTest('a top-level task is not nested'):
            ret = t.an.nested
            t.assertFalse(ret)

        with t.subTest('a subtask is, at any depth'):
            t.task.ancestry = [t.parent, child_node(), grandchild_node()]
            ret = t.an.nested
            t.assertTrue(ret)

    @patch(f'{SRC}.Ancestry', autospec=True)
    def test_ancestry(t, ancestry: MagicMock) -> None:
        ret = t.an.ancestry
        ancestry.assert_called_once_with(t.task.ancestry)
        t.assertIs(ret, ancestry.return_value)


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
        t.path.read_text.return_value = 'the list as read'
        t.other = MagicMock(spec=Path)
        t.other.read_text.return_value = 'the other list as read'
        t.events = [
            Event('TaskUpdated', 'task/pp02cd', sentinel.stamp),
            Event('TaskAdded', 'task/cc03ef', sentinel.added),
        ]
        t.cs = Changeset(
            {
                t.path: 'the list as written',
                t.other: 'the other list as written',
            },
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
        t.other.write_text.side_effect = lambda text: steps.append('other')
        log = completed_log.return_value
        log.append.side_effect = lambda entries: steps.append('log')
        appended = journal.return_value.append
        appended.side_effect = lambda *args, **kwargs: steps.append('event')

        t.cs.write()

        with t.subTest('each list, then the log, then each event'):
            t.assertEqual(steps, ['list', 'other', 'log', 'event', 'event'])

        with t.subTest('each text goes to its list file'):
            t.path.read_text.assert_called_once_with()
            t.path.write_text.assert_called_once_with('the list as written')
            t.other.write_text.assert_called_once_with(
                'the other list as written'
            )

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

        with t.subTest('the text as read: the list file is left alone'):
            # A second write, to a file that holds the text already.
            steps.clear()
            t.path.read_text.return_value = 'the list as written'

            t.cs.write()

            t.assertEqual(steps, ['other', 'log', 'event', 'event'])


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


class SuppliedEditTests(TestCase):
    """Unit tests for battodo.mutate.SuppliedEdit."""

    def setUp(t) -> None:
        t.node = parent_node()
        t.se = SuppliedEdit({'P': '5'}, 'A new title', 'A line.', TODAY)

    @patch(f'{SRC}.next_due', autospec=True)
    def test_changed(t, next_due: MagicMock) -> None:
        with t.subTest('no clear: the fields, each value read'):
            ret = t.se.changed
            t.assertEqual(ret, {'P': '5'})

        with t.subTest('a repeat is read as add reads it'):
            t.se.fields = {'REPEAT': '14d'}

            ret = t.se.changed

            next_due.assert_called_once_with('14d', TODAY)
            t.assertEqual(ret, {'REPEAT': '14d'})

        with t.subTest('a repeat of None clears the field, unread'):
            next_due.reset_mock()
            t.se.fields = {'P': '3', 'REPEAT': 'None'}

            ret = t.se.changed

            next_due.assert_not_called()
            t.assertEqual(ret, {'P': '3', 'REPEAT': None})

        with t.subTest('an empty repeat is no clear: the read refuses it'):
            t.se.fields = {'REPEAT': ''}
            next_due.side_effect = ValueError("unrecognised REPEAT value: ''")

            with t.assertRaises(ValueError) as caught:
                _ = t.se.changed

            t.assertEqual(
                str(caught.exception), "unrecognised REPEAT value: ''"
            )

        with t.subTest('a due date and tags of None clear each field'):
            next_due.side_effect = None
            t.se.fields = {'P': '3', 'DUE': 'None', 'TAGS': 'None'}
            ret = t.se.changed
            t.assertEqual(ret, {'P': '3', 'DUE': None, 'TAGS': None})

    def test_cleared(t) -> None:
        with t.subTest('none, where no field names the clear token'):
            ret = t.se.cleared
            t.assertEqual(ret, [])

        with t.subTest('each due date, repeat and tags it names'):
            t.se.fields = {
                'P': '3',
                'DUE': 'None',
                'REPEAT': 'None',
                'TAGS': 'None',
            }

            ret = t.se.cleared

            t.assertEqual(ret, ['DUE', 'REPEAT', 'TAGS'])

        with t.subTest('not a priority, which reads the token as a value'):
            t.se.fields = {'P': 'None'}
            ret = t.se.cleared
            t.assertEqual(ret, [])

        with t.subTest('not an empty value'):
            t.se.fields = {'TAGS': ''}
            ret = t.se.cleared
            t.assertEqual(ret, [])

    @patch(f'{SRC}.SuppliedFields', autospec=True)
    def test_supplied(t, supplied_fields: MagicMock) -> None:
        with t.subTest('the named fields, against the day'):
            ret = t.se.supplied
            supplied_fields.assert_called_once_with({'P': '5'}, TODAY)
            t.assertIs(ret, supplied_fields.return_value)

        with t.subTest('a cleared field is left out, unread'):
            supplied_fields.reset_mock()
            t.se.fields = {'P': '5', 'DUE': 'None', 'TAGS': 'None'}

            _ = t.se.supplied

            supplied_fields.assert_called_once_with({'P': '5'}, TODAY)

    @patch(f'{SRC}.SuppliedTitle', autospec=True)
    def test_checked_title(t, supplied_title: MagicMock) -> None:
        with t.subTest('the named title, read'):
            ret = t.se.checked_title
            supplied_title.assert_called_once_with('A new title')
            t.assertIs(ret, supplied_title.return_value.checked)

        with t.subTest('none, where none is named'):
            supplied_title.reset_mock()
            t.se.title = None

            ret = t.se.checked_title

            supplied_title.assert_not_called()
            t.assertIsNone(ret)

    @patch(f'{SRC}.SuppliedDescription', autospec=True)
    def test_checked_description(t, supplied_description: MagicMock) -> None:
        supplied_description.return_value.lines = ['A line.']

        with t.subTest('the lines of the named description, read'):
            ret = t.se.checked_description
            supplied_description.assert_called_once_with('A line.')
            t.assertEqual(ret, ['A line.'])

        with t.subTest('a description of None clears, as an empty one'):
            supplied_description.reset_mock()
            t.se.description = 'None'

            _ = t.se.checked_description

            supplied_description.assert_called_once_with('')

        with t.subTest('none, where none is named'):
            supplied_description.reset_mock()
            t.se.description = None

            ret = t.se.checked_description

            supplied_description.assert_not_called()
            t.assertIsNone(ret)

    @patch.object(SuppliedEdit, 'changed', new_callable=PropertyMock)
    def test_changes(t, changed: PropertyMock) -> None:
        t.node.fields = {'P': '4', 'DUE': '2026-08-01', 'REPEAT': '7d'}
        cases = {
            'a new value is a change': ({'P': '5'}, {'P': '5'}),
            'the value the task holds is no change': ({'P': '4'}, {}),
            'a value read as the one it holds is no change': (
                {'P': '5', 'DUE': '2026-08-01'},
                {'P': '5'},
            ),
            'a clear of a field the task carries is a change': (
                {'REPEAT': None},
                {'REPEAT': None},
            ),
        }
        for name, (read, expected) in cases.items():
            with t.subTest(name):
                changed.return_value = read
                ret = t.se.changes(t.node)
                t.assertEqual(ret, expected)

        held = {
            'a clear of a field the task does not carry is no change': (
                {},
                {'REPEAT': None},
            ),
            'nor is a clear of a field it carries empty': (
                {'REPEAT': ''},
                {'REPEAT': None},
            ),
            'nor is an empty value the task holds': (
                {'TAGS': ''},
                {'TAGS': ''},
            ),
        }
        for name, (fields, read) in held.items():
            with t.subTest(name):
                t.node.fields = fields
                changed.return_value = read

                ret = t.se.changes(t.node)

                t.assertEqual(ret, {})

    @patch.object(SuppliedEdit, 'checked_title', new_callable=PropertyMock)
    def test_new_title(t, checked_title: PropertyMock) -> None:
        cases = {
            'a title that changes the task': ('A new title', 'A new title'),
            'none, where the task holds that title': ('A task', None),
            'none, where it holds the title spaces aside': (' A task ', None),
            'none, where none is named': (None, None),
        }
        for name, (title, expected) in cases.items():
            with t.subTest(name):
                checked_title.return_value = title
                ret = t.se.new_title(t.node)
                t.assertEqual(ret, expected)

    @patch.object(
        SuppliedEdit, 'checked_description', new_callable=PropertyMock
    )
    def test_new_description(t, checked_description: PropertyMock) -> None:
        t.node.description_lines = ['A line.']
        cases = {
            'lines that change the task': (['A new line.'], ['A new line.']),
            'a clear of the lines the task holds': ([], []),
            'none, where the task holds those lines': (['A line.'], None),
            'none, where none is named': (None, None),
        }
        for name, (lines, expected) in cases.items():
            with t.subTest(name):
                checked_description.return_value = lines
                ret = t.se.new_description(t.node)
                t.assertEqual(ret, expected)

        with t.subTest('none, where it clears a task with no description'):
            t.node.description_lines = []
            checked_description.return_value = []

            ret = t.se.new_description(t.node)

            t.assertIsNone(ret)

    @patch.object(SuppliedEdit, 'supplied', new_callable=PropertyMock)
    def test_refuse_root_fields(t, supplied: PropertyMock) -> None:
        supplied.return_value = MagicMock(spec=['refuse_root_fields'])
        t.se.refuse_root_fields()
        supplied.return_value.refuse_root_fields.assert_called_once_with()

    @patch.object(SuppliedEdit, 'new_description', autospec=True)
    @patch.object(SuppliedEdit, 'new_title', autospec=True)
    def test_delta(
        t,
        new_title: MagicMock,
        new_description: MagicMock,
    ) -> None:
        t.node.description_lines = ['A line.']
        new_title.return_value = 'A new title'
        new_description.return_value = ['A first line.', 'A second line.']

        with t.subTest('each written field, the title, the description'):
            ret = t.se.delta(t.node, {'P': '5', 'DUE': '2026-09-01'})

            new_title.assert_called_once_with(t.se, t.node)
            new_description.assert_called_once_with(t.se, t.node)
            t.assertEqual(
                ret,
                {
                    'P': ['4', '5'],
                    'DUE': [None, '2026-09-01'],
                    'title': ['A task', 'A new title'],
                    'description': [
                        'A line.',
                        'A first line.\nA second line.',
                    ],
                },
            )

        with t.subTest('a cleared description, against null'):
            new_title.return_value = None
            new_description.return_value = []
            ret = t.se.delta(t.node, {})
            t.assertEqual(ret, {'description': ['A line.', None]})

        with t.subTest('nothing that changes the task'):
            new_description.return_value = None
            ret = t.se.delta(t.node, {})
            t.assertEqual(ret, {})


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


class SuppliedDescriptionTests(TestCase):
    """Unit tests for battodo.mutate.SuppliedDescription."""

    def setUp(t) -> None:
        t.sd = SuppliedDescription('A line.\n  An indented line.  ')

    def test_lines(t) -> None:
        with t.subTest('each line, stripped of its indent'):
            ret = t.sd.lines
            t.assertEqual(ret, ['A line.', 'An indented line.'])

        with t.subTest('an empty text is no description'):
            t.sd.text = ''
            ret = t.sd.lines
            t.assertEqual(ret, [])

        refused = {
            'a blank line': (
                'A line.\n  \nAnother line.',
                "description line '  ' is blank",
            ),
            'a line that reads as a task': (
                'A line.\n  - [x] A done task',
                "description line '  - [x] A done task' reads as a task line",
            ),
            'a line that reads as a heading': (
                '## A heading',
                "description line '## A heading' reads as a heading",
            ),
            'a line that reads as a comment': (
                '  <!-- A comment -->',
                "description line '  <!-- A comment -->' reads as a comment",
            ),
            'a carriage return': (
                'A line.\r',
                "description line 'A line.\\r' holds a carriage return",
            ),
        }
        for name, (text, message) in refused.items():
            with t.subTest(name):
                t.sd.text = text

                with t.assertRaises(ValueError) as caught:
                    _ = t.sd.lines

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
        with t.subTest('the fields a subtask carries, a repeat among them'):
            # Nothing to refuse: the call returns.
            t.sf.fields = {
                'LOE': '2',
                'DUE': '2026-09-01',
                'REPEAT': '7d',
                'TAGS': 'a-tag',
            }
            t.sf.refuse_root_fields()

        refused = {
            'a priority, which the top-level task owns': (
                {'P': '3'},
                'P belongs to the top-level task, not to a subtask',
            ),
            'a priority beside a repeat': (
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


class SuppliedAttributesTests(TestCase):
    """Unit tests for battodo.mutate.SuppliedAttributes."""

    def setUp(t) -> None:
        t.sa = SuppliedAttributes('a_key=a value', 'a note')

    @patch.object(SuppliedAttributes, 'pairs', new_callable=PropertyMock)
    def test_checked(t, pairs: PropertyMock) -> None:
        with t.subTest('each key against its value, in the order given'):
            pairs.return_value = [('cost', '45.00'), ('note', 'a note')]
            ret = t.sa.checked
            t.assertEqual(list(ret.items()), pairs.return_value)

        with t.subTest('no pair: no attribute'):
            pairs.return_value = []
            ret = t.sa.checked
            t.assertEqual(ret, {})

        refused = {
            'a key with a capital': (
                [('Place', 'Main St')],
                "attribute key must be a lowercase identifier, not 'Place'",
            ),
            'a key that starts with a digit': (
                [('1st', 'Main St')],
                "attribute key must be a lowercase identifier, not '1st'",
            ),
            'a key with a line break': (
                [('cost\n', '45.00')],
                "attribute key must be a lowercase identifier, not 'cost\\n'",
            ),
            'an empty value': (
                [('cost', '')],
                "attribute 'cost' must hold a value",
            ),
            'a value with a line feed': (
                [('note', 'a\nnote')],
                "attribute 'note' must hold no line break, not 'a\\nnote'",
            ),
            'a value with a carriage return': (
                [('note', 'a\rnote')],
                "attribute 'note' must hold no line break, not 'a\\rnote'",
            ),
            'a key given twice': (
                [('note', 'a note'), ('cost', '45.00'), ('note', 'another')],
                "attribute 'note' is given twice",
            ),
        }
        for name, (given, message) in refused.items():
            with t.subTest(name):
                pairs.return_value = given

                with t.assertRaises(ValueError) as caught:
                    _ = t.sa.checked

                t.assertEqual(str(caught.exception), message)

    @patch.object(SuppliedAttributes, 'segments', new_callable=PropertyMock)
    def test_pairs(t, segments: PropertyMock) -> None:
        with t.subTest('each segment split at its first =, then the note'):
            segments.return_value = ['a_key=a value', 'sum=1+1=2']
            ret = t.sa.pairs
            t.assertEqual(
                ret,
                [('a_key', 'a value'), ('sum', '1+1=2'), ('note', 'a note')],
            )

        with t.subTest('the note enters whole, never split'):
            segments.return_value = []
            t.sa.note = 'a note, cost=45.00'

            ret = t.sa.pairs

            t.assertEqual(ret, [('note', 'a note, cost=45.00')])

        with t.subTest('no note: the segments alone'):
            segments.return_value = ['a_key=a value']
            t.sa.note = None

            ret = t.sa.pairs

            t.assertEqual(ret, [('a_key', 'a value')])

        with t.subTest('a segment with no = is refused'):
            segments.return_value = ['a value']

            with t.assertRaises(ValueError) as caught:
                _ = t.sa.pairs

            t.assertEqual(
                str(caught.exception),
                "attribute must read key=value, not 'a value'",
            )

    def test_segments(t) -> None:
        with t.subTest('the text the write was given'):
            ret = t.sa.segments
            t.assertEqual(ret, ['a_key=a value'])

        with t.subTest('no text: no segment'):
            t.sa.text = None
            ret = t.sa.segments
            t.assertEqual(ret, [])

        split = {
            'one segment': ('place=Main St', ['place=Main St']),
            'a value holds commas and =': (
                'place=Main St, Suite 4, sum=1+1=2',
                ['place=Main St, Suite 4', 'sum=1+1=2'],
            ),
            'the split takes every space after the comma': (
                'a_key=a value,  cost=45.00',
                ['a_key=a value', 'cost=45.00'],
            ),
            'and needs none': (
                'a_key=a value,cost=45.00',
                ['a_key=a value', 'cost=45.00'],
            ),
            'a line feed after the comma stays': (
                'a_key=a value,\ncost=45.00',
                ['a_key=a value,\ncost=45.00'],
            ),
            'a carriage return after the comma stays': (
                'a_key=a value,\r\ncost=45.00',
                ['a_key=a value,\r\ncost=45.00'],
            ),
            'a comma before a key outside the grammar stays': (
                'a_key=a value, Cost=45.00, 2nd=b',
                ['a_key=a value, Cost=45.00, 2nd=b'],
            ),
            'a comma before a word with no = stays': (
                'a_key=a value, cost',
                ['a_key=a value, cost'],
            ),
            'an empty text is one empty segment': ('', ['']),
        }
        for name, (text, expected) in split.items():
            with t.subTest(name):
                t.sa.text = text
                ret = t.sa.segments
                t.assertEqual(ret, expected)


class AddedLineTests(TestCase):
    """Unit tests for battodo.mutate.AddedLine."""

    def setUp(t) -> None:
        t.al = AddedLine(
            'the line as written',
            {'P': '3', 'ID': 'zz01ab'},
            'a-list',
        )

    @patch.object(AddedLine, 'node', new_callable=PropertyMock)
    def test_payload(t, node: PropertyMock) -> None:
        node.return_value = MagicMock(spec=['listed_snapshot'])
        listed_snapshot = node.return_value.listed_snapshot
        listed_snapshot.return_value = sentinel.snapshot

        with t.subTest('each field against nothing, the line and its list'):
            ret = t.al.payload

            listed_snapshot.assert_called_once_with('a-list')
            t.assertEqual(
                ret,
                {
                    'delta': {'P': [None, '3'], 'ID': [None, 'zz01ab']},
                    'snapshot': sentinel.snapshot,
                },
            )

        with t.subTest('the attributes, where any are given'):
            t.al.attrs = {'cost': '45.00'}
            ret = t.al.payload
            t.assertEqual(ret['attrs'], {'cost': '45.00'})

    @patch(f'{SRC}.TodoDocument', autospec=True)
    def test_node(t, todo_document: MagicMock) -> None:
        todo_document.return_value.tasks = [sentinel.node]

        ret = t.al.node

        # The line alone in an open section, as the parser reads it.
        todo_document.assert_called_once_with(
            f'{OPEN_HEADING}\nthe line as written'
        )
        t.assertIs(ret, sentinel.node)


class IdAssignmentTests(TestCase):
    """Unit tests for battodo.mutate.IdAssignment."""

    def setUp(t) -> None:
        t.ia = IdAssignment(bare_node(), 'pp02cd', 'a-list')

    @patch.object(TaskNode, 'listed_snapshot', autospec=True)
    def test_event(t, snapshot: MagicMock) -> None:
        snapshot.return_value = sentinel.snapshot

        ret = t.ia.event

        snapshot.assert_called_once_with(t.ia.node, 'a-list')
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


class CompletionLinesTests(TestCase):
    """Unit tests for battodo.mutate.CompletionLines."""

    def setUp(t) -> None:
        t.child = child_node()
        t.parent = parent_node()
        t.parent.children = [t.child, done_child_node()]
        t.cl = CompletionLines([t.parent, t.child], GIVEN_DAY)

    @patch.object(
        CompletionLines, 'recurrence_fields', new_callable=PropertyMock
    )
    @patch.object(CompletionLines, 'dropped', new_callable=PropertyMock)
    @patch.object(CompletionLines, 'recurrence', new_callable=PropertyMock)
    def test_stamps(
        t,
        recurrence: PropertyMock,
        dropped: PropertyMock,
        recurrence_fields: PropertyMock,
    ) -> None:
        t.cl.ids = {3: 'zz01ab', 1: '9o71lx'}
        dropped.return_value = set()

        with t.subTest('a block that stays: each stream gains its id'):
            recurrence.return_value = None
            ret = t.cl.stamps
            t.assertEqual(ret, {3: {'ID': 'zz01ab'}, 1: {'ID': '9o71lx'}})

        with t.subTest('a stream whose line goes: no id'):
            dropped.return_value = {3}
            ret = t.cl.stamps
            t.assertEqual(ret, {1: {'ID': '9o71lx'}})

        with t.subTest('a finished block that goes: nothing'):
            dropped.return_value = {1, 3}
            ret = t.cl.stamps
            t.assertEqual(ret, {})

        with t.subTest('a recurrence: the fields it gains, then its id'):
            recurrence.return_value = t.parent
            recurrence_fields.return_value = {
                'DUE': '2026-08-15',
                'ADDED': '2026-08-01',
            }

            ret = t.cl.stamps

            t.assertEqual(
                ret,
                {
                    1: {
                        'DUE': '2026-08-15',
                        'ADDED': '2026-08-01',
                        'ID': '9o71lx',
                    }
                },
            )

        with t.subTest('a repeating subtask: its fields on its own line'):
            recurrence.return_value = t.child
            recurrence_fields.return_value = {'DUE': '2026-08-15'}

            ret = t.cl.stamps

            t.assertEqual(ret, {3: {'DUE': '2026-08-15', 'ID': 'zz01ab'}})

    @patch.object(CompletionLines, 'root_done', new_callable=PropertyMock)
    @patch.object(CompletionLines, 'rescheduled', new_callable=PropertyMock)
    def test_recurrence_fields(
        t,
        rescheduled: PropertyMock,
        root_done: PropertyMock,
    ) -> None:
        rescheduled.return_value = date(2026, 8, 15)

        with t.subTest('a top-level recurrence: its next due date, its day'):
            root_done.return_value = True
            ret = t.cl.recurrence_fields
            t.assertEqual(ret, {'DUE': '2026-08-15', 'ADDED': '2026-08-01'})

        with t.subTest('a repeating subtask: its next due date alone'):
            root_done.return_value = False
            ret = t.cl.recurrence_fields
            t.assertEqual(ret, {'DUE': '2026-08-15'})

        with t.subTest('none without a recurrence'):
            rescheduled.return_value = None
            ret = t.cl.recurrence_fields
            t.assertEqual(ret, {})

    @patch.object(CompletionLines, 'recurrence', new_callable=PropertyMock)
    @patch.object(CompletionLines, 'ancestries', new_callable=PropertyMock)
    @patch.object(CompletionLines, 'root_done', new_callable=PropertyMock)
    def test_checked_off(
        t,
        root_done: PropertyMock,
        ancestries: PropertyMock,
        recurrence: PropertyMock,
    ) -> None:
        ancestries.return_value = [
            ancestry_of(t.parent, t.child),
            ancestry_of(t.parent),
        ]
        recurrence.return_value = None

        with t.subTest('a block that stays: each completed task'):
            root_done.return_value = False
            ret = t.cl.checked_off
            t.assertEqual(ret, [3, 1])

        with t.subTest('a recurrence: none, as it stays open'):
            ancestries.return_value = [ancestry_of(t.parent, t.child)]
            recurrence.return_value = t.child

            ret = t.cl.checked_off

            t.assertEqual(ret, [])

        with t.subTest('a finished block: none, as the block goes'):
            root_done.return_value = True
            ret = t.cl.checked_off
            t.assertEqual(ret, [])

        with t.subTest('a scratch: none, as its block goes'):
            root_done.return_value = False
            recurrence.return_value = None
            t.cl.scratched = True

            ret = t.cl.checked_off

            t.assertEqual(ret, [])

    @patch.object(CompletionLines, 'recurrence', new_callable=PropertyMock)
    @patch.object(CompletionLines, 'root_done', new_callable=PropertyMock)
    def test_dropped(
        t,
        root_done: PropertyMock,
        recurrence: PropertyMock,
    ) -> None:
        recurrence.return_value = None

        with t.subTest('a block that stays: nothing'):
            root_done.return_value = False
            ret = t.cl.dropped
            t.assertEqual(ret, set())

        with t.subTest('a finished block: every line of it'):
            root_done.return_value = True
            ret = t.cl.dropped
            t.assertEqual(ret, {1, 2, 3, 4})

        with t.subTest('a recurrence: its children, not it or its notes'):
            recurrence.return_value = t.parent
            ret = t.cl.dropped
            t.assertEqual(ret, {3, 4})

        with t.subTest('a repeating subtask: its children'):
            root_done.return_value = False
            step = child_node()
            step.children = [grandchild_node()]
            recurrence.return_value = step

            ret = t.cl.dropped

            t.assertEqual(ret, {5})

        with t.subTest('a scratch: the block of the named task'):
            recurrence.return_value = None
            t.cl.scratched = True

            ret = t.cl.dropped

            t.assertEqual(ret, {3})

    @patch.object(CompletionLines, 'ancestries', new_callable=PropertyMock)
    def test_root_done(t, ancestries: PropertyMock) -> None:
        with t.subTest('a cascade that ends below the top level'):
            ancestries.return_value = [ancestry_of(t.parent, t.child)]
            ret = t.cl.root_done
            t.assertFalse(ret)

        with t.subTest('one that reaches it'):
            ancestries.return_value = [
                ancestry_of(t.parent, t.child),
                ancestry_of(t.parent),
            ]

            ret = t.cl.root_done

            t.assertTrue(ret)

    @patch(f'{SRC}.new_task_id', autospec=True)
    @patch.object(CompletionLines, 'ancestries', new_callable=PropertyMock)
    def test_ids(t, ancestries: PropertyMock, new_task_id: MagicMock) -> None:
        new_task_id.return_value = 'zz01ab'

        with t.subTest('a stream keeps its id; one with none is given one'):
            # A checklist item lands on its parent's stream.
            ancestries.return_value = [
                ancestry_of(t.parent, checklist_node(), stream=t.parent),
                ancestry_of(t.parent, t.child),
            ]

            ret = t.cl.ids

            t.assertEqual(ret, {1: '9o71lx', 3: 'zz01ab'})

        with t.subTest('a new id is drawn once, however often it is read'):
            # Two reads: an id drawn at random must name one task.
            new_task_id.reset_mock()
            t.cl = CompletionLines([t.parent, t.child], GIVEN_DAY)
            bare = bare_node()
            ancestries.return_value = [
                ancestry_of(bare, checklist_node(), stream=bare),
                ancestry_of(bare),
            ]

            ret = t.cl.ids
            t.assertEqual(ret, {1: 'zz01ab'})

            again = t.cl.ids
            t.assertIs(again, ret)
            new_task_id.assert_called_once_with()

    @patch(f'{SRC}.next_due', autospec=True)
    @patch.object(CompletionLines, 'recurrence', new_callable=PropertyMock)
    def test_rescheduled(
        t,
        recurrence: PropertyMock,
        next_due: MagicMock,
    ) -> None:
        t.parent.fields = {'P': '3', 'REPEAT': '7d', 'ID': '9o71lx'}

        with t.subTest('a recurrence that repeats, against the day'):
            recurrence.return_value = t.parent

            ret = t.cl.rescheduled

            next_due.assert_called_once_with('7d', GIVEN_DAY)
            t.assertIs(ret, next_due.return_value)

        with t.subTest('none where there is no recurrence'):
            recurrence.return_value = None
            ret = t.cl.rescheduled
            t.assertIsNone(ret)

    @patch.object(CompletionLines, 'ancestries', new_callable=PropertyMock)
    def test_recurrence(t, ancestries: PropertyMock) -> None:
        with t.subTest('the last task finished, where it repeats'):
            t.child.fields = {'REPEAT': '7d'}
            ancestries.return_value = [ancestry_of(t.parent, t.child)]

            ret = t.cl.recurrence

            t.assertIs(ret, t.child)

        with t.subTest('the top-level task, where the cascade reaches it'):
            t.parent.fields = {'REPEAT': '7d'}
            ancestries.return_value = [
                ancestry_of(t.parent, t.child),
                ancestry_of(t.parent),
            ]

            ret = t.cl.recurrence

            t.assertIs(ret, t.parent)

        with t.subTest('none where the last task finished does not repeat'):
            t.parent.fields = {'P': '4'}
            ret = t.cl.recurrence
            t.assertIsNone(ret)

        with t.subTest('none for a scratch, which reschedules nothing'):
            ancestries.return_value = [ancestry_of(t.parent, t.child)]
            t.cl.scratched = True

            ret = t.cl.recurrence

            t.assertIsNone(ret)

    def test_root(t) -> None:
        ret = t.cl.root
        t.assertIs(ret, t.parent)

    @patch(f'{SRC}.Ancestry', autospec=True)
    @patch.object(CompletionLines, '_still_open', new_callable=PropertyMock)
    def test_ancestries(
        t,
        still_open: PropertyMock,
        ancestry: MagicMock,
    ) -> None:
        below = grandchild_node()
        t.cl.ancestry = [t.parent, t.child, below]
        # Each ancestry stands in as the tuple of the tasks it holds.
        ancestry.side_effect = tuple

        cases = {
            'each task above open: the named task alone': (
                2,
                [(t.parent, t.child, below)],
            ),
            'its parent finished too': (
                1,
                [(t.parent, t.child, below), (t.parent, t.child)],
            ),
            'every task finished, deepest first': (
                0,
                [(t.parent, t.child, below), (t.parent, t.child), (t.parent,)],
            ),
        }
        for name, (count, expected) in cases.items():
            with t.subTest(name):
                still_open.return_value = count
                ret = t.cl.ancestries
                t.assertEqual(ret, expected)

    @patch.object(CompletionLines, '_stops', new_callable=PropertyMock)
    def test_still_open(t, stops: PropertyMock) -> None:
        cases = {
            'no stop: every task above finishes': ([], 0),
            'a stop at the top task: it stays open': ([0], 1),
            'the deepest stop: it and each task above stay open': ([0, 1], 2),
        }
        for name, (found, expected) in cases.items():
            with t.subTest(name):
                stops.return_value = found
                ret = t.cl._still_open
                t.assertEqual(ret, expected)

        with t.subTest('a scratch: each task above stays open, unread'):
            stops.reset_mock()
            t.cl.scratched = True

            ret = t.cl._still_open

            stops.assert_not_called()
            t.assertEqual(ret, 1)

    def test_stops(t) -> None:
        below = grandchild_node()
        t.child.children = [below]
        t.cl.ancestry = [t.parent, t.child, below]

        with t.subTest('every parent finished: no stop'):
            ret = t.cl._stops
            t.assertEqual(ret, [])

        with t.subTest('an open sibling stops the cascade at its parent'):
            t.parent.children[1].done = False
            ret = t.cl._stops
            t.assertEqual(ret, [0])

        with t.subTest('a repeating task finishes no parent'):
            t.parent.children[1].done = True
            below.fields = {'REPEAT': '7d'}
            ret = t.cl._stops
            t.assertEqual(ret, [1])

        with t.subTest('and a cascade ends at a repeating parent'):
            below.fields = {'LOE': '1'}
            t.child.fields = {'REPEAT': '7d'}
            ret = t.cl._stops
            t.assertEqual(ret, [0])

        with t.subTest('two open siblings: a stop at each parent'):
            t.child.fields = {'LOE': '1'}
            t.child.children = [below, grandchild_node()]
            t.parent.children[1].done = False

            ret = t.cl._stops

            t.assertEqual(ret, [0, 1])


class TaskCompletionTests(TestCase):
    """Unit tests for battodo.mutate.TaskCompletion."""

    def setUp(t) -> None:
        t.node = parent_node()
        t.tc = TaskCompletion(
            ancestry_of(t.node, path='a path'),
            {},
            GIVEN_DAY,
            'a-list',
        )

    @patch.object(TaskNode, 'listed_snapshot', autospec=True)
    @patch.object(TaskCompletion, 'delta', new_callable=PropertyMock)
    def test_payload(t, delta: PropertyMock, snapshot: MagicMock) -> None:
        delta.return_value = sentinel.delta
        snapshot.return_value = sentinel.snapshot

        with t.subTest('the delta, the task as it was, its path, its day'):
            ret = t.tc.payload

            snapshot.assert_called_once_with(t.node, 'a-list')
            t.assertEqual(
                ret,
                {
                    'delta': sentinel.delta,
                    'snapshot': sentinel.snapshot,
                    'ancestry': 'a path',
                    'completed_on': '2026-08-01',
                },
            )

        with t.subTest('a checklist item is marked as one'):
            t.tc.ancestry = ancestry_of(
                t.node,
                checklist_node(),
                stream=t.node,
                path='a path',
            )

            ret = t.tc.payload

            t.assertIs(ret['checklist_item'], True)

        with t.subTest('the attributes of the named task'):
            t.tc.ancestry = ancestry_of(t.node, path='a path')
            t.tc.attrs = {'cost': '45.00'}

            ret = t.tc.payload

            t.assertEqual(
                ret,
                {
                    'delta': sentinel.delta,
                    'snapshot': sentinel.snapshot,
                    'ancestry': 'a path',
                    'attrs': {'cost': '45.00'},
                    'completed_on': '2026-08-01',
                },
            )

    def test_delta(t) -> None:
        with t.subTest('the done'):
            ret = t.tc.delta
            t.assertEqual(ret, {'done': [False, True]})

        with t.subTest('each field the task gains, against its own'):
            t.node.fields['DUE'] = '2026-08-05'
            t.node.fields['ADDED'] = '2026-07-06'
            t.tc.recurrence_fields = {
                'DUE': '2026-08-15',
                'ADDED': '2026-08-01',
            }

            ret = t.tc.delta

            t.assertEqual(
                ret,
                {
                    'done': [False, True],
                    'DUE': ['2026-08-05', '2026-08-15'],
                    'ADDED': ['2026-07-06', '2026-08-01'],
                },
            )

        with t.subTest('a field the task does not carry stands against None'):
            t.tc.ancestry = ancestry_of(t.node, child_node())
            t.tc.recurrence_fields = {'DUE': '2026-08-15'}

            ret = t.tc.delta

            t.assertEqual(
                ret,
                {
                    'done': [False, True],
                    'DUE': [None, '2026-08-15'],
                },
            )

        with t.subTest('a scratch records the removal instead'):
            t.tc.recurrence_fields = {}
            t.tc.scratched = True
            ret = t.tc.delta
            t.assertEqual(ret, {'removed': [False, True]})

    def test_status(t) -> None:
        with t.subTest('a completion: DONE'):
            ret = t.tc.status
            t.assertEqual(ret, 'DONE')

        with t.subTest('a scratch: SCRATCHED'):
            t.tc.scratched = True
            ret = t.tc.status
            t.assertEqual(ret, 'SCRATCHED')


class RecordedTaskTests(TestCase):
    """Unit tests for battodo.mutate.RecordedTask."""

    def setUp(t) -> None:
        t.snapshot: dict[str, Any] = {
            'title': 'A task',
            'done': False,
            'fields': {'P': '4', 'ID': '9o71lx'},
        }
        t.rt = RecordedTask(t.snapshot, 1)

    @patch.object(RecordedTask, 'children', new_callable=PropertyMock)
    @patch.object(RecordedTask, 'description_lines', new_callable=PropertyMock)
    @patch.object(RecordedTask, 'line', new_callable=PropertyMock)
    def test_lines(
        t,
        line: PropertyMock,
        description_lines: PropertyMock,
        children: PropertyMock,
    ) -> None:
        line.return_value = 'the task line'
        description_lines.return_value = ['a description line']
        children.return_value = [
            Mock(spec=['lines'], lines=['a child line', 'its child line']),
        ]

        ret = t.rt.lines

        t.assertEqual(
            ret,
            [
                'the task line',
                'a description line',
                'a child line',
                'its child line',
            ],
        )

    def test_line(t) -> None:
        ret = t.rt.line
        # Checked off, whatever the record says: the task is closed.
        t.assertEqual(ret, '  - [x] A task [P:4] [ID:9o71lx]')

    def test_indent(t) -> None:
        ret = t.rt.indent
        t.assertEqual(ret, '  ')

    def test_description_lines(t) -> None:
        with t.subTest('none without a description'):
            ret = t.rt.description_lines
            t.assertEqual(ret, [])

        with t.subTest('each line under the title'):
            t.snapshot['description'] = 'A line.\nAnother line.'
            ret = t.rt.description_lines
            t.assertEqual(
                ret,
                ['        A line.', '        Another line.'],
            )

    @patch(f'{SRC}.RecordedTask', autospec=True)
    def test_children(t, recorded_task: MagicMock) -> None:
        with t.subTest('none recorded'):
            ret = t.rt.children
            t.assertEqual(ret, [])

        with t.subTest('each one level deeper'):
            t.snapshot['children'] = [sentinel.child]
            ret = t.rt.children
            recorded_task.assert_called_once_with(sentinel.child, 2)
            t.assertEqual(ret, [recorded_task.return_value])

    @patch.object(RecordedTask, 'children', new_callable=PropertyMock)
    def test_ids(t, children: PropertyMock) -> None:
        children.return_value = [
            Mock(spec=['ids'], ids={'cc03ef', 'gc04gh'}),
            Mock(spec=['ids'], ids=set()),
        ]

        with t.subTest('its own id and each below it'):
            ret = t.rt.ids
            t.assertEqual(ret, {'9o71lx', 'cc03ef', 'gc04gh'})

        with t.subTest('a task with no id adds none'):
            t.snapshot['fields'] = {'P': '4'}
            ret = t.rt.ids
            t.assertEqual(ret, {'cc03ef', 'gc04gh'})


class OpenedTaskTests(TestCase):
    """Unit tests for battodo.mutate.OpenedTask."""

    def setUp(t) -> None:
        t.node = parent_node()
        t.node.done = True
        t.ot = OpenedTask(
            ancestry_of(t.node, path='a path'), 'pp02cd', 'a-list'
        )

    @patch.object(OpenedTask, 'payload', new_callable=PropertyMock)
    def test_event(t, payload: PropertyMock) -> None:
        payload.return_value = sentinel.payload

        ret = t.ot.event

        t.assertEqual(
            ret,
            Event('TaskUpdated', 'task/pp02cd', sentinel.payload),
        )

    @patch.object(TaskNode, 'listed_snapshot', autospec=True)
    def test_payload(t, listed_snapshot: MagicMock) -> None:
        listed_snapshot.return_value = sentinel.snapshot

        with t.subTest('the opening and the task as it was, in its list'):
            ret = t.ot.payload

            listed_snapshot.assert_called_once_with(t.node, 'a-list')
            t.assertEqual(
                ret,
                {
                    'delta': {'done': [True, False]},
                    'snapshot': sentinel.snapshot,
                },
            )

        with t.subTest('a task with no id takes one on the same event'):
            t.node.fields = {'LOE': '2'}
            ret = t.ot.payload
            t.assertEqual(
                ret['delta'],
                {'ID': [None, 'pp02cd'], 'done': [True, False]},
            )

        with t.subTest('a subtask records where it sits'):
            t.ot.ancestry = ancestry_of(parent_node(), t.node, path='a path')
            ret = t.ot.payload
            t.assertEqual(ret['ancestry'], 'a path')

        with t.subTest('the named task: its changes and its attributes'):
            t.ot.ancestry = ancestry_of(t.node, path='a path')
            t.node.fields = {'LOE': '2', 'ID': 'pp02cd'}
            t.ot.delta = {'P': ['4', '5']}
            t.ot.attrs = {'cost': '45.00'}

            ret = t.ot.payload

            t.assertEqual(
                ret,
                {
                    'delta': {'P': ['4', '5'], 'done': [True, False]},
                    'snapshot': sentinel.snapshot,
                    'attrs': {'cost': '45.00'},
                },
            )


class LogEntryTests(TestCase):
    """Unit tests for battodo.mutate.LogEntry."""

    def setUp(t) -> None:
        t.logged = MagicMock(spec=['ancestry', 'day', 'status', 'attrs'])
        t.logged.ancestry = MagicMock(spec=['path', 'node'])
        t.logged.ancestry.path = 'A task > A subtask of it'
        t.logged.ancestry.node = MagicMock(spec=['schema_fields'])
        t.logged.ancestry.node.schema_fields = {
            'LOE': '2',
            'DUE': '2026-08-20',
        }
        t.logged.day = TODAY
        t.logged.status = 'DONE'
        t.logged.attrs = None
        t.le = LogEntry(LIST_PATH, t.logged)

    @patch.object(LogEntry, 'attributes', new_callable=PropertyMock)
    @patch.object(LogEntry, 'fields', new_callable=PropertyMock)
    def test_text(
        t,
        fields: PropertyMock,
        attributes: PropertyMock,
    ) -> None:
        attributes.return_value = ''

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

        with t.subTest('the attributes come last'):
            attributes.return_value = '[attrs:{}]'

            ret = t.le.text

            t.assertEqual(
                ret,
                '2026-08-08 | a-list | DONE | A task > A subtask of it '
                '[attrs:{}]',
            )

    def test_day(t) -> None:
        ret = t.le.day
        t.assertEqual(ret, TODAY)

    def test_category(t) -> None:
        ret = t.le.category
        t.assertEqual(ret, 'a-list')

    def test_status(t) -> None:
        ret = t.le.status
        t.assertEqual(ret, 'DONE')

    def test_title(t) -> None:
        ret = t.le.title
        t.assertEqual(ret, 'A task > A subtask of it')

    def test_fields(t) -> None:
        ret = t.le.fields
        t.assertEqual(ret, '[LOE:2] [DUE:2026-08-20]')

    def test_attributes(t) -> None:
        with t.subTest('a JSON object in a block of its own'):
            t.logged.attrs = {'cost': '45.00', 'note': 'Paid] "cash", cost=5'}

            ret = t.le.attributes

            t.assertEqual(
                ret,
                '[attrs:{"cost": "45.00", "note": "Paid] \\"cash\\", cost=5"}]',
            )

        with t.subTest('in ASCII, so no character can break the line'):
            t.logged.attrs = {'note': 'caf\u00e9\u2028'}
            ret = t.le.attributes
            t.assertEqual(ret, '[attrs:{"note": "caf\\u00e9\\u2028"}]')

        cases: dict[str, dict[str, str] | None] = {
            'no attributes': None,
            'an empty map': {},
        }
        for name, attrs in cases.items():
            with t.subTest(f'{name} write no block'):
                t.logged.attrs = attrs
                ret = t.le.attributes
                t.assertEqual(ret, '')


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
                {t.path: sentinel.text},
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

    @patch.object(ListBackfill, '_snapshots', new_callable=PropertyMock)
    @patch.object(ListBackfill, '_streams', new_callable=PropertyMock)
    def test_events(t, streams: PropertyMock, snapshots: PropertyMock) -> None:
        streams.return_value = ['task/zz01ab']
        snapshots.return_value = [sentinel.snapshot]

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

    def test_delta(t) -> None:
        ret = t.lb._delta
        # No add date before, the migration's after.
        t.assertEqual(ret, {'ADDED': [None, '2026-08-08']})

    @patch.object(ListBackfill, 'tasks', new_callable=PropertyMock)
    def test_streams(t, tasks: PropertyMock) -> None:
        tasks.return_value = [bare_node(), undated_due_node()]
        t.lb.ids = {1: 'zz01ab', 6: 'ud05ef'}

        ret = t.lb._streams

        t.assertEqual(ret, ['task/zz01ab', 'task/ud05ef'])

    @patch.object(TaskNode, 'listed_snapshot', autospec=True)
    @patch.object(ListBackfill, 'tasks', new_callable=PropertyMock)
    def test_snapshots(t, tasks: PropertyMock, snapshot: MagicMock) -> None:
        tasks.return_value = [bare_node()]
        snapshot.return_value = sentinel.snapshot
        t.path.stem = 'a-list'

        ret = t.lb._snapshots

        snapshot.assert_called_once_with(tasks.return_value[0], 'a-list')
        t.assertEqual(ret, [sentinel.snapshot])


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
    ancestry = MagicMock(spec=['tasks', 'node', 'nested', 'path', 'stream'])
    ancestry.tasks = list(tasks)
    ancestry.node = tasks[-1]
    ancestry.nested = len(tasks) > 1
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
