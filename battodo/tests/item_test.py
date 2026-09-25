from datetime import date, datetime, timezone
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, Mock, PropertyMock, call, patch

from ..item import (
    Item,
    ItemView,
    Subtask,
    TaskNode,
    build_item,
    build_item_json,
    item_data,
    render_item,
    subtask_entry,
)

SRC = 'battodo.item'
TODAY = date(2026, 8, 5)


def stand_in(t: TestCase, *targets: str) -> None:
    """Patch each `battodo.item` target and set its mock on `t`."""
    for target in targets:
        patcher = patch(f'{SRC}.{target}', autospec=True)
        setattr(t, target, patcher.start())
        t.addCleanup(patcher.stop)


class SubtaskEntryTests(TestCase):
    """Unit tests for battodo.item.subtask_entry."""

    def test_fields(t) -> None:
        deep = TaskNode(
            raw_index=3,
            indent=4,
            done=True,
            title='Buy the lumber',
            fields={'DUE': '2026-09-01'},
        )
        child = TaskNode(
            raw_index=2,
            indent=2,
            done=False,
            title='Chip the brush',
            fields={'LOE': '2', 'TAGS': 'yard,summer', 'ID': 'abc123'},
            children=[deep],
        )

        ret = subtask_entry(child)

        # The stored fields, and the children below it.
        t.assertEqual(
            ret,
            {
                'id': 'abc123',
                'title': 'Chip the brush',
                'done': False,
                'loe': 2,
                'due': None,
                'tags': ['yard', 'summer'],
                'subtasks': [
                    {
                        'id': None,
                        'title': 'Buy the lumber',
                        'done': True,
                        'loe': None,
                        'due': '2026-09-01',
                        'tags': [],
                        'subtasks': [],
                    }
                ],
            },
        )

    def test_checklist_item(t) -> None:
        # A checklist item carries no field at all.
        plain = TaskNode(
            raw_index=1,
            indent=2,
            done=False,
            title='Sweep',
            fields={},
        )

        ret = subtask_entry(plain)

        t.assertEqual(
            ret,
            {
                'id': None,
                'title': 'Sweep',
                'done': False,
                'loe': None,
                'due': None,
                'tags': [],
                'subtasks': [],
            },
        )


class ItemDataTests(TestCase):
    """Unit tests for battodo.item.item_data."""

    rank: MagicMock
    multiplier: MagicMock

    def setUp(t) -> None:
        stand_in(t, 'rank', 'multiplier')
        t.rank.return_value = 10.006
        t.multiplier.return_value = 4.0

    def test_rank(t) -> None:
        subject = TaskNode(
            raw_index=0,
            indent=0,
            done=False,
            title='Deck rebuild',
            fields={'P': '4'},
        )

        item_data(Path('/source-dir/a-list.md'), subject, TODAY)

        # Asked for against the given day, and asked for once.
        t.rank.assert_called_once_with(subject, TODAY)
        t.multiplier.assert_called_once_with(subject)

    def test_fields(t) -> None:
        # The list, the stored fields, and the children.
        subject = TaskNode(
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
            children=[
                TaskNode(
                    raw_index=1,
                    indent=2,
                    done=False,
                    title='Sweep',
                    fields={},
                )
            ],
        )

        ret = item_data(Path('/source-dir/a-list.md'), subject, TODAY)

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
                'subtasks': [
                    {
                        'id': None,
                        'title': 'Sweep',
                        'done': False,
                        'loe': None,
                        'due': None,
                        'tags': [],
                        'subtasks': [],
                    }
                ],
            },
        )

    def test_absent(t) -> None:
        bare = TaskNode(
            raw_index=0,
            indent=0,
            done=False,
            title='Bare',
            fields={},
        )

        ret = item_data(Path('/source-dir/a-list.md'), bare, TODAY)

        # An unfielded task reads as absent, not as zero.
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


class RenderItemTests(TestCase):
    """Unit tests for battodo.item.render_item."""

    maxDiff = None

    def setUp(t) -> None:
        t.data: dict[str, object] = {
            'list': 'a-list',
            'id': '9o71lx',
            'title': 'Deck rebuild',
            'done': False,
            'rank': 10.0,
            'priority': 4.0,
            'loe': 8,
            'due': '2026-08-12',
            'added': '2026-07-06',
            'repeat': '30d',
            'tags': ['yard', 'summer'],
            'subtasks': [],
        }

    def test_rows(t) -> None:
        ret = render_item(t.data)

        # One labelled row per value, aligned.
        t.assertEqual(
            ret,
            'Deck rebuild\n'
            '  list    a-list\n'
            '  id      9o71lx\n'
            '  rank    10.0\n'
            '  P       4.0\n'
            '  LOE     8\n'
            '  DUE     2026-08-12\n'
            '  REPEAT  30d\n'
            '  TAGS    yard, summer\n'
            '  ADDED   2026-07-06',
        )

    def test_absent(t) -> None:
        # An absent field has no row, an absent id a dash.
        t.data.update(
            id=None,
            loe=None,
            due=None,
            repeat=None,
            tags=[],
            added=None,
        )

        ret = render_item(t.data)

        t.assertEqual(
            ret,
            'Deck rebuild\n  list  a-list\n  id    -\n  rank  10.0\n  P     4.0',
        )

    def test_subtasks(t) -> None:
        # Children follow, indented, in SCHEMA.md markup.
        t.data['subtasks'] = [
            {
                'id': 'abc123',
                'title': 'Chip the brush',
                'done': False,
                'loe': 2,
                'due': '2026-09-01',
                'tags': ['yard'],
                'subtasks': [
                    {
                        'id': None,
                        'title': 'Buy the lumber',
                        'done': True,
                        'loe': None,
                        'due': None,
                        'tags': [],
                        'subtasks': [],
                    }
                ],
            }
        ]

        ret = render_item(t.data)

        t.assertEqual(
            ret.splitlines()[-3:],
            [
                '  subtasks',
                (
                    '    [ ] Chip the brush [LOE:2] [DUE:2026-09-01] '
                    '[TAGS:yard] [ID:abc123]'
                ),
                '      [x] Buy the lumber',
            ],
        )


class BuildItemTests(TestCase):
    """Unit tests for battodo.item.build_item."""

    TaskSelection: MagicMock
    item_data: MagicMock
    render_item: MagicMock

    def setUp(t) -> None:
        stand_in(t, 'TaskSelection', 'item_data', 'render_item')
        t.directory = Path('/source-dir')
        t.now = datetime(2026, 8, 5, 10, 30, tzinfo=timezone.utc)
        # An autospec instance specs `record` from the descriptor, not
        # from the value it yields.
        t.record = MagicMock(spec=['path', 'task'])
        t.TaskSelection.return_value.record = t.record

    def test_selection(t) -> None:
        build_item(t.directory, 'deck', t.now)
        t.TaskSelection.assert_called_with(t.directory, 'deck')

    def test_data(t) -> None:
        build_item(t.directory, 'deck', t.now)
        # The local day of the clock decides the rank.
        t.item_data.assert_called_with(t.record.path, t.record.task, TODAY)

    def test_text(t) -> None:
        result = build_item(t.directory, 'deck', t.now)
        t.render_item.assert_called_with(t.item_data.return_value)
        t.assertEqual(result, t.render_item.return_value)


class BuildItemJsonTests(TestCase):
    """Unit tests for battodo.item.build_item_json."""

    TaskSelection: MagicMock
    item_data: MagicMock
    dumps: MagicMock

    def setUp(t) -> None:
        stand_in(t, 'TaskSelection', 'item_data', 'dumps')
        t.directory = Path('/source-dir')
        t.now = datetime(2026, 8, 5, 10, 30, tzinfo=timezone.utc)
        # An autospec instance specs `record` from the descriptor, not
        # from the value it yields.
        t.record = MagicMock(spec=['path', 'task'])
        t.TaskSelection.return_value.record = t.record

    def test_selection(t) -> None:
        build_item_json(t.directory, 'deck', t.now)

        # The same selection the text form describes.
        t.TaskSelection.assert_called_with(t.directory, 'deck')
        t.item_data.assert_called_with(t.record.path, t.record.task, TODAY)

    def test_json(t) -> None:
        result = build_item_json(t.directory, 'deck', t.now)

        # Serialized, indented for a person to read too.
        t.dumps.assert_called_with(t.item_data.return_value, indent=2)
        t.assertEqual(result, t.dumps.return_value)


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

    @patch(f'{SRC}.dumps', autospec=True)
    @patch.object(Item, 'data', new_callable=PropertyMock)
    def test_json(t, data: PropertyMock, dumps: MagicMock) -> None:
        ret = t.it.json
        # Serialized, indented for a person to read too.
        dumps.assert_called_once_with(data.return_value, indent=2)
        t.assertIs(ret, dumps.return_value)

    @patch.object(Item, 'subtasks', new_callable=PropertyMock)
    def test_data(t, subtasks: PropertyMock) -> None:
        child = Mock(spec=Subtask)
        child.data = {'title': 'Sweep'}
        subtasks.return_value = [child]

        with t.subTest('the list, the stored fields, the rank, the children'):
            ret = t.it.data
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
            t.task.node = bare_node()
            subtasks.return_value = []

            ret = t.it.data

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

    @patch(f'{SRC}.Subtask', autospec=True)
    def test_subtasks(t, subtask: MagicMock) -> None:
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

        # One per child, done ones included, in file order.
        t.assertEqual(ret, [subtask.return_value, subtask.return_value])
        t.assertEqual(subtask.call_args_list, [call(first), call(second)])


class SubtaskTests(TestCase):
    """Unit tests for battodo.item.Subtask."""

    def setUp(t) -> None:
        t.node = TaskNode(
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
        t.st = Subtask(t.node)

    @patch.object(Subtask, 'subtasks', new_callable=PropertyMock)
    def test_data(t, subtasks: PropertyMock) -> None:
        child = Mock(spec=Subtask)
        child.data = {'title': 'Buy the lumber'}
        subtasks.return_value = [child]

        with t.subTest('the stored fields, and the children below it'):
            ret = t.st.data
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
            t.st.node = TaskNode(
                raw_index=1,
                indent=2,
                done=True,
                title='Sweep',
                fields={},
            )
            subtasks.return_value = []

            ret = t.st.data

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
        deeper = TaskNode(
            raw_index=3,
            indent=4,
            done=True,
            title='Buy the lumber',
            fields={},
        )
        t.node.children = [deeper]

        ret = t.st.subtasks

        t.assertEqual([subtask.node for subtask in ret], [deeper])

    @patch.object(Subtask, 'subtasks', new_callable=PropertyMock)
    @patch.object(Subtask, 'line', new_callable=PropertyMock)
    def test_lines(t, line: PropertyMock, subtasks: PropertyMock) -> None:
        line.return_value = '[ ] Chip the brush'
        child = Mock(spec=Subtask)
        child.lines = ['[x] Buy the lumber', '  [ ] Sand the boards']
        subtasks.return_value = [child]

        ret = t.st.lines

        # Each level below indents one more time.
        t.assertEqual(
            ret,
            [
                '[ ] Chip the brush',
                '  [x] Buy the lumber',
                '    [ ] Sand the boards',
            ],
        )

    @patch.object(Subtask, 'fields', new_callable=PropertyMock)
    @patch.object(Subtask, 'mark', new_callable=PropertyMock)
    def test_line(t, mark: PropertyMock, fields: PropertyMock) -> None:
        mark.return_value = 'x'
        fields.return_value = ' [LOE:2]'

        ret = t.st.line

        t.assertEqual(ret, '[x] Chip the brush [LOE:2]')

    def test_mark(t) -> None:
        with t.subTest('an open child leaves the box empty'):
            ret = t.st.mark
            t.assertEqual(ret, ' ')

        with t.subTest('a done child is checked'):
            t.node.done = True
            ret = t.st.mark
            t.assertEqual(ret, 'x')

    def test_fields(t) -> None:
        with t.subTest('every field, in SCHEMA.md order'):
            ret = t.st.fields
            t.assertEqual(
                ret,
                ' [LOE:2] [DUE:2026-09-01] [TAGS:yard,summer] [ID:abc123]',
            )

        with t.subTest('an absent field is left out'):
            t.node.fields = {'DUE': '2026-09-01'}
            ret = t.st.fields
            t.assertEqual(ret, ' [DUE:2026-09-01]')

        with t.subTest('a TAGS field holding no tag is left out'):
            t.node.fields = {'TAGS': ','}
            ret = t.st.fields
            t.assertEqual(ret, '')


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
            t.item.subtasks = [Mock(spec=Subtask)]

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

    def test_outline(t) -> None:
        subtask = Mock(spec=Subtask)
        subtask.lines = ['[ ] Chip the brush', '  [x] Buy the lumber']
        t.item.subtasks = [subtask]

        ret = t.iv.outline

        # Two indents in: one below the label, which sits one in.
        t.assertEqual(
            ret,
            ['    [ ] Chip the brush', '      [x] Buy the lumber'],
        )


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
