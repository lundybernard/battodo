from datetime import date, datetime, timezone
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, Mock, PropertyMock, call, patch

from ..item import (
    Item,
    ItemJsonView,
    ItemView,
    SubtaskJsonView,
    SubtaskView,
    TaskNode,
)

SRC = 'battodo.item'
TODAY = date(2026, 8, 5)


class ItemTests(TestCase):
    """Unit tests for battodo.item.Item."""

    rank: MagicMock
    multiplier: MagicMock

    def setUp(t) -> None:
        patches = ['rank', 'multiplier']
        for target in patches:
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)

        t.rank.return_value = 10.006
        t.multiplier.return_value = 4.0
        t.node = deck_node()
        t.task = Mock(spec=['path', 'node', 'today'])
        t.task.path = Path('/source-dir/a-list.md')
        t.task.node = t.node
        t.task.today = TODAY
        t.it = Item(t.task)

    @patch(f'{SRC}.Task', autospec=True)
    def test_from_config(t, task: MagicMock) -> None:
        # spec models batconf: an option the user did not supply is
        # absent from the Configuration, not None.
        conf = Mock(spec=['view', 'selector'])
        conf.view = Mock(spec=['source_dir'])
        conf.view.source_dir = '~/a-source-dir'
        conf.selector = 'a selector'

        ret = Item.from_config(
            conf,
            datetime(2026, 8, 5, 10, 30, tzinfo=timezone.utc),
        )

        # The task expands the directory. The clock's day ranks it.
        task.assert_called_once_with(
            Path('~/a-source-dir'),
            'a selector',
            TODAY,
        )
        t.assertIs(ret.task, task.return_value)

    def test_category(t) -> None:
        ret = t.it.category
        t.assertEqual(ret, 'a-list')

    def test_node(t) -> None:
        ret = t.it.node
        t.assertIs(ret, t.node)

    def test_rank(t) -> None:
        ret = t.it.rank
        # Asked for against the day the task carries.
        t.assertEqual(ret, 10.006)
        t.rank.assert_called_once_with(t.node, TODAY)

    def test_priority(t) -> None:
        ret = t.it.priority
        t.assertEqual(ret, 4.0)
        t.multiplier.assert_called_once_with(t.node)

    def test_subtasks(t) -> None:
        first = TaskNode(
            raw_index=1,
            indent=2,
            done=False,
            title='Sweep',
            fields={},
        )
        second = TaskNode(
            raw_index=2,
            indent=2,
            done=True,
            title='Buy the lumber',
            fields={},
        )
        t.node.children = [first, second]

        ret = t.it.subtasks

        # The parser's children, done ones included, in file order.
        t.assertEqual(ret, [first, second])


class ItemViewTests(TestCase):
    """Unit tests for battodo.item.ItemView."""

    def setUp(t) -> None:
        t.item = Mock(spec=Item)
        t.item.node = deck_node()
        t.item.category = 'a-list'
        t.item.rank = 10.0
        t.item.priority = 4.0
        t.item.subtasks = []
        t.iv = ItemView(t.item)

    @patch.object(ItemView, 'outline', new_callable=PropertyMock)
    @patch.object(ItemView, 'rows', new_callable=PropertyMock)
    def test_text(t, rows: PropertyMock, outline: PropertyMock) -> None:
        rows.return_value = [('list', 'a-list'), ('REPEAT', '30d')]
        outline.return_value = ['    [ ] Sweep']

        with t.subTest('the title, then one row per value, aligned'):
            ret = t.iv.text
            t.assertEqual(ret, 'Deck rebuild\n  list    a-list\n  REPEAT  30d')

        with t.subTest('the subtasks follow under their own label'):
            t.item.subtasks = [brush_node()]

            ret = t.iv.text

            t.assertEqual(
                ret,
                'Deck rebuild\n'
                '  list    a-list\n'
                '  REPEAT  30d\n'
                '  subtasks\n'
                '    [ ] Sweep',
            )

    def test_rows(t) -> None:
        with t.subTest('the list, the id, the rank, P, then each field'):
            ret = t.iv.rows
            t.assertEqual(
                ret,
                [
                    ('list', 'a-list'),
                    ('id', '9o71lx'),
                    ('rank', '10.0'),
                    ('P', '4.0'),
                    ('LOE', '8'),
                    ('DUE', '2026-08-12'),
                    ('REPEAT', '30d'),
                    ('TAGS', 'yard, summer'),
                    ('ADDED', '2026-07-06'),
                ],
            )

        with t.subTest('an absent field has no row, an absent id a dash'):
            t.item.node = bare_node()

            ret = t.iv.rows

            t.assertEqual(
                ret,
                [
                    ('list', 'a-list'),
                    ('id', '-'),
                    ('rank', '10.0'),
                    ('P', '4.0'),
                ],
            )

        with t.subTest('the rank and P show to one decimal place'):
            t.item.rank = 10.006
            t.item.priority = 2.04

            ret = t.iv.rows

            t.assertEqual(ret[2:4], [('rank', '10.0'), ('P', '2.0')])

    @patch.object(ItemView, 'rows', new_callable=PropertyMock)
    def test_width(t, rows: PropertyMock) -> None:
        rows.return_value = [('list', 'a-list'), ('REPEAT', '30d')]
        ret = t.iv.width
        t.assertEqual(ret, len('REPEAT'))

    @patch.object(ItemView, 'subtasks', new_callable=PropertyMock)
    def test_outline(t, subtasks: PropertyMock) -> None:
        subtask = Mock(spec=SubtaskView)
        subtask.lines = ['[ ] Chip the brush', '  [x] Buy the lumber']
        subtasks.return_value = [subtask]

        ret = t.iv.outline

        # Two indents in: one below the label, which sits one in.
        t.assertEqual(
            ret,
            ['    [ ] Chip the brush', '      [x] Buy the lumber'],
        )

    @patch(f'{SRC}.SubtaskView', autospec=True)
    def test_subtasks(t, subtask_view: MagicMock) -> None:
        first = Mock(spec=TaskNode)
        second = Mock(spec=TaskNode)
        t.item.subtasks = [first, second]

        ret = t.iv.subtasks

        # One per child, in the item's order.
        t.assertEqual(
            ret,
            [subtask_view.return_value, subtask_view.return_value],
        )
        t.assertEqual(
            subtask_view.call_args_list,
            [call(first), call(second)],
        )


class SubtaskViewTests(TestCase):
    """Unit tests for battodo.item.SubtaskView."""

    def setUp(t) -> None:
        t.node = brush_node()
        t.sv = SubtaskView(t.node)

    @patch.object(SubtaskView, 'subtasks', new_callable=PropertyMock)
    @patch.object(SubtaskView, 'line', new_callable=PropertyMock)
    def test_lines(t, line: PropertyMock, subtasks: PropertyMock) -> None:
        line.return_value = '[ ] Chip the brush'
        child = Mock(spec=SubtaskView)
        child.lines = ['[x] Buy the lumber', '  [ ] Sand the boards']
        subtasks.return_value = [child]

        ret = t.sv.lines

        # Each level below indents one more time.
        t.assertEqual(
            ret,
            [
                '[ ] Chip the brush',
                '  [x] Buy the lumber',
                '    [ ] Sand the boards',
            ],
        )

    @patch.object(SubtaskView, 'fields', new_callable=PropertyMock)
    @patch.object(SubtaskView, 'mark', new_callable=PropertyMock)
    def test_line(t, mark: PropertyMock, fields: PropertyMock) -> None:
        mark.return_value = 'x'
        fields.return_value = ' [LOE:2]'

        ret = t.sv.line

        t.assertEqual(ret, '[x] Chip the brush [LOE:2]')

    def test_subtasks(t) -> None:
        deeper = Mock(spec=TaskNode)
        t.node.children = [deeper]

        ret = t.sv.subtasks

        t.assertEqual([view.node for view in ret], [deeper])

    def test_mark(t) -> None:
        with t.subTest('an open child leaves the box empty'):
            ret = t.sv.mark
            t.assertEqual(ret, ' ')

        with t.subTest('a done child is checked'):
            t.node.done = True
            ret = t.sv.mark
            t.assertEqual(ret, 'x')

    def test_fields(t) -> None:
        with t.subTest('every field, in SCHEMA.md order'):
            ret = t.sv.fields
            t.assertEqual(
                ret,
                ' [LOE:2] [DUE:2026-09-01] [TAGS:yard,summer] [ID:abc123]',
            )

        with t.subTest('an absent field is left out'):
            t.node.fields = {'DUE': '2026-09-01'}
            ret = t.sv.fields
            t.assertEqual(ret, ' [DUE:2026-09-01]')

        with t.subTest('a TAGS field holding no tag is left out'):
            t.node.fields = {'TAGS': ','}
            ret = t.sv.fields
            t.assertEqual(ret, '')


class ItemJsonViewTests(TestCase):
    """Unit tests for battodo.item.ItemJsonView."""

    def setUp(t) -> None:
        t.item = Mock(spec=Item)
        t.item.node = deck_node()
        t.item.category = 'a-list'
        t.item.rank = 10.006
        t.item.priority = 4.0
        t.ijv = ItemJsonView(t.item)

    @patch(f'{SRC}.dumps', autospec=True)
    @patch.object(ItemJsonView, 'data', new_callable=PropertyMock)
    def test_json(t, data: PropertyMock, dumps: MagicMock) -> None:
        ret = t.ijv.json
        # Serialized, indented for a person to read too.
        dumps.assert_called_once_with(data.return_value, indent=2)
        t.assertIs(ret, dumps.return_value)

    @patch.object(ItemJsonView, 'subtasks', new_callable=PropertyMock)
    def test_data(t, subtasks: PropertyMock) -> None:
        child = Mock(spec=SubtaskJsonView)
        child.data = {'title': 'Sweep'}
        subtasks.return_value = [child]

        with t.subTest('the list, the stored fields, the rank, the children'):
            ret = t.ijv.data
            t.assertEqual(
                ret,
                {
                    'list': 'a-list',
                    'id': '9o71lx',
                    'title': 'Deck rebuild',
                    'done': False,
                    # Rounded to the places the document publishes.
                    'rank': 10.01,
                    'priority': 4.0,
                    'loe': 8,
                    'due': '2026-08-12',
                    'added': '2026-07-06',
                    'repeat': '30d',
                    'tags': ['yard', 'summer'],
                    'subtasks': [{'title': 'Sweep'}],
                },
            )

        with t.subTest('an unfielded task reads as absent, not as zero'):
            t.item.node = bare_node()
            subtasks.return_value = []

            ret = t.ijv.data

            t.assertEqual(
                ret,
                {
                    'list': 'a-list',
                    'id': None,
                    'title': 'Bare',
                    'done': False,
                    'rank': 10.01,
                    'priority': 4.0,
                    'loe': None,
                    'due': None,
                    'added': None,
                    'repeat': None,
                    'tags': [],
                    'subtasks': [],
                },
            )

    @patch(f'{SRC}.SubtaskJsonView', autospec=True)
    def test_subtasks(t, subtask_json_view: MagicMock) -> None:
        first = Mock(spec=TaskNode)
        second = Mock(spec=TaskNode)
        t.item.subtasks = [first, second]

        ret = t.ijv.subtasks

        # One per child, in the item's order.
        t.assertEqual(
            ret,
            [subtask_json_view.return_value, subtask_json_view.return_value],
        )
        t.assertEqual(
            subtask_json_view.call_args_list,
            [call(first), call(second)],
        )


class SubtaskJsonViewTests(TestCase):
    """Unit tests for battodo.item.SubtaskJsonView."""

    def setUp(t) -> None:
        t.node = brush_node()
        t.sjv = SubtaskJsonView(t.node)

    @patch.object(SubtaskJsonView, 'subtasks', new_callable=PropertyMock)
    def test_data(t, subtasks: PropertyMock) -> None:
        child = Mock(spec=SubtaskJsonView)
        child.data = {'title': 'Buy the lumber'}
        subtasks.return_value = [child]

        with t.subTest('the stored fields, and the children below it'):
            ret = t.sjv.data
            t.assertEqual(
                ret,
                {
                    'id': 'abc123',
                    'title': 'Chip the brush',
                    'done': False,
                    'loe': 2,
                    'due': '2026-09-01',
                    'tags': ['yard', 'summer'],
                    'subtasks': [{'title': 'Buy the lumber'}],
                },
            )

        with t.subTest('a checklist item carries no field at all'):
            t.sjv.node = TaskNode(
                raw_index=1,
                indent=2,
                done=True,
                title='Sweep',
                fields={},
            )
            subtasks.return_value = []

            ret = t.sjv.data

            t.assertEqual(
                ret,
                {
                    'id': None,
                    'title': 'Sweep',
                    'done': True,
                    'loe': None,
                    'due': None,
                    'tags': [],
                    'subtasks': [],
                },
            )

    def test_subtasks(t) -> None:
        deeper = Mock(spec=TaskNode)
        t.node.children = [deeper]

        ret = t.sjv.subtasks

        t.assertEqual([view.node for view in ret], [deeper])


def deck_node() -> TaskNode:
    """A top-level task carrying every field an item shows."""
    return TaskNode(
        raw_index=0,
        indent=0,
        done=False,
        title='Deck rebuild',
        fields={
            'P': '4',
            'LOE': '8',
            'DUE': '2026-08-12',
            'REPEAT': '30d',
            'TAGS': 'yard,summer',
            'ADDED': '2026-07-06',
            'ID': '9o71lx',
        },
    )


def bare_node() -> TaskNode:
    """A top-level task carrying no field at all."""
    return TaskNode(
        raw_index=0,
        indent=0,
        done=False,
        title='Bare',
        fields={},
    )


def brush_node() -> TaskNode:
    """A child carrying every field a child line shows."""
    return TaskNode(
        raw_index=2,
        indent=2,
        done=False,
        title='Chip the brush',
        fields={
            'LOE': '2',
            'DUE': '2026-09-01',
            'TAGS': 'yard,summer',
            'ID': 'abc123',
        },
    )
