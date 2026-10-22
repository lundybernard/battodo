from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, Mock, PropertyMock, call, patch, sentinel

from ..selection import (
    TOP_N,
    Category,
    CategoryJsonView,
    Row,
    RowJsonView,
    Selection,
    SelectionJsonView,
    SourceError,
    TodoList,
    Window,
    parse_window,
    parse_windows,
)

SRC = 'battodo.view.selection'
TODAY = date(2026, 8, 5)
# A Monday, so a weekday number added to it names that day.
WEEK_START = date(2026, 8, 3)
# A schedule as a config file writes it, and the names it keeps open.
SCHEDULE = 'a-list=mon-fri 9-17; another-list=mon-fri 17-21, sat-sun 10-20'
ALWAYS = 'a-third-list, a-fourth-list'
# The windows of SCHEDULE as a table: the category, the weekday numbers
# it opens on, and the hours it stays open on them.
WINDOWS = (
    ('a-list', range(5), range(9, 17)),
    ('another-list', range(5), range(17, 21)),
    ('another-list', range(5, 7), range(10, 20)),
)
# Every hour of one week. A sweep over it names the day and the hour.
HOURS = [
    (day, hour)
    for day in range(7)
    for hour in range(24)
]  # fmt: skip


class SelectionTests(TestCase):
    """Unit tests for battodo.view.selection.Selection."""

    discover_lists: MagicMock

    def setUp(t) -> None:
        patches = ['discover_lists']
        for target in patches:
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)

        t.resolved = Mock(spec=Path)
        t.resolved.is_dir.return_value = True
        t.directory = Mock(spec=Path)
        t.directory.expanduser.return_value.resolve.return_value = t.resolved

        t.s = Selection(
            t.directory,
            at('2026-08-05T10:30'),
            show_all=False,
            # Default: top_n=TOP_N,
        )

    def todo(t, category: str, *, parked: bool = False, rows=('a',)) -> Mock:
        """A stand-in list, holding only what a selection reads off one."""
        found = Mock(spec=['category', 'parked', 'rows', 'order'])
        found.category = category
        found.parked = parked
        found.rows = list(rows)
        found.order = (0, category)
        return found

    def test_today(t) -> None:
        ret = t.s.today
        t.assertEqual(ret, TODAY)

    def test_limit(t) -> None:
        with t.subTest('an abridged view stops at the top few'):
            ret = t.s.limit
            t.assertEqual(ret, TOP_N)

        with t.subTest('an explicit count replaces the default'):
            t.s.top_n = 2
            ret = t.s.limit
            t.assertEqual(ret, 2)

        with t.subTest('asking for everything lifts the limit'):
            t.s.show_all = True
            ret = t.s.limit
            t.assertIsNone(ret)

    def test_source(t) -> None:
        with t.subTest('the path is expanded and resolved'):
            ret = t.s.source
            t.assertEqual(ret, t.resolved)
            t.directory.expanduser.assert_called_once_with()

        with t.subTest('a directory that is not there is an error'):
            t.s.__dict__.pop('source')
            t.resolved.is_dir.return_value = False

            with t.assertRaises(SourceError) as caught:
                _ = t.s.source

            t.assertIn(str(t.resolved), str(caught.exception))

    def test_active(t) -> None:
        with t.subTest('with no schedule, no category is active'):
            ret = t.s.active
            t.assertEqual(ret, set())

        for day, hour in HOURS:
            with t.subTest(day=day, hour=hour):
                ret = Selection(
                    t.directory,
                    at_hour(day, hour),
                    show_all=False,
                    windows=SCHEDULE,
                    always_active=ALWAYS,
                ).active

                t.assertEqual(ret, opens(day, hour))

    def test_always_open(t) -> None:
        with t.subTest('no name is always open by default'):
            ret = t.s.always_open
            t.assertEqual(ret, frozenset())

        with t.subTest('each name of the list, spaces and empties aside'):
            t.s.always_active = ' a-list,another-list , '
            ret = t.s.always_open
            t.assertEqual(ret, frozenset({'a-list', 'another-list'}))

    def test_schedule(t) -> None:
        with t.subTest('no category is scheduled by default'):
            ret = t.s.schedule
            t.assertEqual(ret, {})

        with t.subTest('the configured windows, read'):
            t.s.windows = 'a-list=mon 9-10'
            ret = t.s.schedule
            t.assertEqual(ret, {'a-list': [Window(0, 0, 9, 10)]})

    def test_day(t) -> None:
        # 2026-08-05 is a Wednesday, the third day of the week.
        ret = t.s.day
        t.assertEqual(ret, 2)

    def test_hour(t) -> None:
        ret = t.s.hour
        t.assertEqual(ret, 10)

    @patch(f'{SRC}.parse_curve', autospec=True)
    def test_curve(t, parse_curve: MagicMock) -> None:
        ret = t.s.curve

        # Decoded from the default, since the fixture names no curve.
        t.assertIs(ret, parse_curve.return_value)
        parse_curve.assert_called_once_with('-30:0.5, -7:1.0, 0:2.0, 14:4.0')

    @patch(f'{SRC}.TodoList', autospec=True)
    def test_lists(t, todo_list: MagicMock) -> None:
        with t.subTest('a source holding no lists at all is an error'):
            t.discover_lists.return_value = []

            with t.assertRaises(SourceError) as caught:
                _ = t.s.lists

            t.assertIn(str(t.resolved), str(caught.exception))
            t.assertIn('## Open', str(caught.exception))

        with t.subTest('every discovered list is read, in display order'):
            # The error above left nothing cached to clear.
            t.s.__dict__.pop('lists', None)
            paths = [Path('later.md'), Path('earlier.md')]
            t.discover_lists.return_value = paths
            later, earlier = t.todo('study'), t.todo('work')
            later.order, earlier.order = (2, 'study'), (0, 'work')
            todo_list.side_effect = [later, earlier]
            t.s.curve = sentinel.curve

            ret = t.s.lists

            t.assertEqual(ret, [earlier, later])
            t.discover_lists.assert_called_with(t.resolved)
            # Each list ranks its tasks on the selection's day and curve.
            t.assertEqual(
                todo_list.call_args_list,
                [
                    call(Path('later.md'), TODAY, sentinel.curve),
                    call(Path('earlier.md'), TODAY, sentinel.curve),
                ],
            )

    def test_shows(t) -> None:
        t.s.windows = 'a-list=mon 9-10; another-list=tue 9-10'
        t.s.active = {'a-list'}

        cases = {
            'a scheduled category that is active shows': (
                t.todo('a-list'),
                True,
            ),
            'a scheduled category that is not active does not': (
                t.todo('another-list'),
                False,
            ),
            'a category with no window has no window to be outside': (
                t.todo('a-third-list'),
                True,
            ),
            'and neither does a named one': (
                t.todo('career'),
                True,
            ),
            'a list that opted out never shows': (
                t.todo('a-list', parked=True),
                False,
            ),
            'and opting out beats having no window': (
                t.todo('a-third-list', parked=True),
                False,
            ),
        }
        for name, (found, expected) in cases.items():
            with t.subTest(name):
                ret = t.s.shows(found)
                t.assertEqual(ret, expected)

        t.s.show_all = True
        everything = {
            'asking for everything reaches past a shut window': (
                t.todo('another-list'),
                True,
            ),
            'an open one is unaffected by the asking': (
                t.todo('a-list'),
                True,
            ),
            'and a list that opted out is still not shown': (
                t.todo('backlog', parked=True),
                False,
            ),
        }
        for name, (found, expected) in everything.items():
            with t.subTest(name):
                ret = t.s.shows(found)
                t.assertEqual(ret, expected)

    def test_categories(t) -> None:
        t.s.windows = 'chores=sun 9-10'
        t.s.active = {'work', 'study'}
        shown, shut, empty = (
            t.todo('work'),
            t.todo('chores'),
            t.todo('study', rows=()),
        )
        t.s.lists = [shown, shut, empty]

        categories = t.s.categories

        with t.subTest('only the lists this view shows become categories'):
            t.assertEqual([c.name for c in categories], ['work'])

        with t.subTest("each carries that list's rows"):
            t.assertEqual(categories[0].rows, shown.rows)

        with t.subTest('and the limit the view was asked for'):
            t.assertEqual(categories[0].limit, TOP_N)

        with t.subTest('a list with nothing open contributes no category'):
            t.assertNotIn('study', [c.name for c in categories])


class SelectionFromConfigTests(TestCase):
    """Unit tests for battodo.view.selection.Selection.from_config.

    The decode from configuration strings to what a selection takes.
    """

    def setUp(t) -> None:
        t.now = at('2026-08-05T10:30')
        t.conf = Mock(spec=['view'])
        t.conf.view = Mock(
            spec=[
                'source_dir',
                'top',
                'rank_due_curve',
                'windows',
                'always_active',
            ]
        )
        t.conf.view.source_dir = '~/a-source-dir'
        t.conf.view.top = '2'
        t.conf.view.rank_due_curve = 'a-curve'
        t.conf.view.windows = 'some-windows'
        t.conf.view.always_active = 'some-names'

    def test_from_config(t) -> None:
        selection = Selection.from_config(t.conf, t.now, show_all=True)

        with t.subTest('the source directory is left unexpanded'):
            t.assertEqual(selection.directory, Path('~/a-source-dir'))

        with t.subTest('the clock is the one it was given'):
            t.assertEqual(selection.now, t.now)

        with t.subTest('the count is read as a number'):
            t.assertEqual(selection.top_n, 2)

        with t.subTest('the flag is the one given'):
            t.assertTrue(selection.show_all)

        with t.subTest('the curve is carried as written'):
            t.assertEqual(selection.rank_due_curve, 'a-curve')

        with t.subTest('and so are the schedule fields'):
            t.assertEqual(selection.windows, 'some-windows')
            t.assertEqual(selection.always_active, 'some-names')

        with t.subTest('a schedule field the lookup cannot find is empty'):
            t.conf.view = Mock(spec=['source_dir', 'top', 'rank_due_curve'])
            t.conf.view.source_dir = '~/a-source-dir'
            t.conf.view.top = '2'
            t.conf.view.rank_due_curve = 'a-curve'

            unset = Selection.from_config(t.conf, t.now, show_all=True)

            t.assertEqual(unset.windows, '')
            t.assertEqual(unset.always_active, '')

        with t.subTest('a count below one is refused'):
            t.conf.view.top = '0'
            with t.assertRaises(ValueError):
                Selection.from_config(t.conf, t.now, show_all=False)


class TodoListTests(TestCase):
    """Unit tests for battodo.view.selection.TodoList."""

    def setUp(t) -> None:
        t.path = Mock(spec=Path)
        t.path.stem = 'work'
        t.path.read_text.return_value = '## Open\n\n- [ ] A task [P:3]\n'
        t.tl = TodoList(t.path, TODAY, sentinel.curve)

    def test_category(t) -> None:
        ret = t.tl.category
        t.assertEqual(ret, 'work')

    def test_text(t) -> None:
        with t.subTest('the file is read through'):
            ret = t.tl.text
            t.assertEqual(ret, '## Open\n\n- [ ] A task [P:3]\n')

        with t.subTest('and read only the once'):
            again = t.tl.text
            t.assertEqual(again, t.tl.text)
            t.path.read_text.assert_called_once_with()

    @patch(f'{SRC}.TodoDocument', autospec=True)
    def test_document(t, parsed: MagicMock) -> None:
        t.tl.text = 'a list file'

        ret = t.tl.document

        t.assertEqual(ret, parsed.return_value)
        parsed.assert_called_once_with('a list file')

    def test_open_rows(t) -> None:
        t.tl.document = Mock(spec=['tasks'])
        t.tl.document.tasks = [
            stored('An open task'),
            stored('A finished task', done=True),
            stored('A later recurrence', due='2026-08-20', repeat='7d'),
        ]

        ret = t.tl.open_rows

        # Every open task is shown, a recurrence due later included:
        # its due date lowers its rank instead of hiding it.
        t.assertEqual(
            [row.task.title for row in ret],
            ['An open task', 'A later recurrence'],
        )
        t.assertEqual([row.curve for row in ret], [sentinel.curve] * 2)

    def test_parked(t) -> None:
        with t.subTest('a list with no marker is not parked'):
            ret = t.tl.parked
            t.assertFalse(ret)

        with t.subTest('the marker anywhere in the file parks it'):
            t.tl.__dict__.pop('parked')
            t.tl.text = '<!-- battodo:parked -->\n## Open\n\n- [ ] A [P:1]\n'

            ret = t.tl.parked

            t.assertTrue(ret)

    def test_rows(t) -> None:
        with t.subTest('the rows come back in the order their keys give'):
            low, high = Mock(spec=['key']), Mock(spec=['key'])
            low.key = (-1.0, 'zzzz', 'Low')
            high.key = (-5.0, 'zzzz', 'High')
            t.tl.open_rows = [low, high]

            ret = t.tl.rows

            t.assertEqual(ret, [high, low])

        with t.subTest('a list with nothing open comes back empty'):
            t.tl.__dict__.pop('rows')
            t.tl.open_rows = []

            ret = t.tl.rows

            t.assertEqual(ret, [])

    def test_order(t) -> None:
        with t.subTest('a named category sorts by its place in the order'):
            ret = t.tl.order
            t.assertEqual(ret, (0, 'work'))

        with t.subTest('an unknown name sorts after every named one'):
            t.tl.category = 'side-quests'
            ret = t.tl.order
            t.assertEqual(ret, (5, 'side-quests'))

        with t.subTest('and unknown names sort among themselves by name'):
            t.tl.category = 'backlog'
            first = t.tl.order
            t.tl.category = 'side-quests'

            ret = t.tl.order

            t.assertLess(first, ret)


class CategoryTests(TestCase):
    """Unit tests for battodo.view.selection.Category."""

    def setUp(t) -> None:
        t.rows = [getattr(sentinel, f'row_{n}') for n in range(6)]
        t.c = Category('work', t.rows, 2)

    def test_shown(t) -> None:
        with t.subTest('a limit takes the top of the list'):
            ret = t.c.shown
            t.assertEqual(ret, t.rows[:2])

        with t.subTest('no limit shows every one'):
            t.c.limit = None
            ret = t.c.shown
            t.assertEqual(ret, t.rows)

        with t.subTest('a limit past the end shows every one too'):
            t.c.limit = 99
            ret = t.c.shown
            t.assertEqual(ret, t.rows)

    def test_hidden(t) -> None:
        with t.subTest('what the limit held back is counted'):
            ret = t.c.hidden
            t.assertEqual(ret, 4)

        with t.subTest('nothing is held back without a limit'):
            t.c.limit = None
            ret = t.c.hidden
            t.assertEqual(ret, 0)

    def test_name(t) -> None:
        ret = t.c.name
        t.assertEqual(ret, 'work')

    def test_rows(t) -> None:
        ret = t.c.rows
        t.assertEqual(ret, t.rows)


class RowTests(TestCase):
    """Unit tests for battodo.view.selection.Row."""

    rank: MagicMock
    multiplier: MagicMock
    parse_date: MagicMock

    def setUp(t) -> None:
        patches = ['rank', 'multiplier', 'parse_date']
        for target in patches:
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)

        t.rank.return_value = 4.25
        t.multiplier.return_value = 3.0
        t.parse_date.return_value = None

        t.task = Mock(spec=['title', 'due', 'children'])
        t.task.title = 'A task'
        t.task.due = None
        t.task.children = []

        t.r = Row(t.task, TODAY, sentinel.curve)

    def test_key(t) -> None:
        with t.subTest('an undated task sorts behind every dated one'):
            ret = t.r.key
            t.assertEqual(ret, (-4.25, 'zzzz', 'A task'))

        with t.subTest('a stored date takes the place the marker held'):
            t.r.__dict__.pop('key', None)
            t.task.due = '2026-08-20'

            ret = t.r.key

            t.assertEqual(ret, (-4.25, '2026-08-20', 'A task'))

    def test_rank(t) -> None:
        ret = t.r.rank

        t.assertEqual(ret, 4.25)
        t.rank.assert_called_once_with(t.task, TODAY, sentinel.curve)

    def test_priority(t) -> None:
        ret = t.r.priority

        t.assertEqual(ret, 3.0)
        t.multiplier.assert_called_once_with(t.task)

    def test_subtasks(t) -> None:
        with t.subTest('a task with nothing open under it counts none'):
            ret = t.r.subtasks
            t.assertEqual(ret, 0)

        with t.subTest('otherwise the open children are counted'):
            t.r.__dict__.pop('subtasks', None)
            t.r.children = [sentinel.child, sentinel.child]

            ret = t.r.subtasks

            t.assertEqual(ret, 2)

    def test_children(t) -> None:
        finished, open_child = Mock(spec=['done']), Mock(spec=['done'])
        finished.done = True
        open_child.done = False
        t.task.children = [finished, open_child]

        ret = t.r.children

        # Subtasks and checklist items both count; a finished child
        # does not.
        t.assertEqual(ret, [open_child])

    def test_parsed_due(t) -> None:
        with t.subTest('a stored date is read through the parser'):
            t.parse_date.return_value = date(2026, 8, 20)
            t.task.due = '2026-08-20'

            ret = t.r.parsed_due

            t.assertEqual(ret, date(2026, 8, 20))
            t.parse_date.assert_called_once_with('2026-08-20')

        with t.subTest('and one the parser cannot read comes back empty'):
            t.r.__dict__.pop('parsed_due', None)
            t.parse_date.return_value = None

            ret = t.r.parsed_due

            t.assertIsNone(ret)


class SelectionJsonViewTests(TestCase):
    """Unit tests for battodo.view.selection.SelectionJsonView."""

    def setUp(t) -> None:
        t.selection = Mock(spec=Selection)
        t.selection.today = TODAY
        t.selection.active = {'work', 'career'}
        t.sjv = SelectionJsonView(t.selection)

    @patch(f'{SRC}.dumps', autospec=True)
    @patch.object(SelectionJsonView, 'data', new_callable=PropertyMock)
    def test_json(t, data: PropertyMock, dumps: MagicMock) -> None:
        ret = t.sjv.json
        # Serialized, indented for a person to read too.
        dumps.assert_called_once_with(data.return_value, indent=2)
        t.assertIs(ret, dumps.return_value)

    @patch.object(SelectionJsonView, 'categories', new_callable=PropertyMock)
    def test_data(t, categories: PropertyMock) -> None:
        category = Mock(spec=CategoryJsonView)
        category.data = {'name': 'work'}
        categories.return_value = [category]

        ret = t.sjv.data

        with t.subTest('the day is recorded in its stored form'):
            t.assertEqual(ret['date'], '2026-08-05')

        with t.subTest('the active set reads in a settled order'):
            t.assertEqual(ret['active'], ['career', 'work'])

        with t.subTest('each category as its own view records it'):
            t.assertEqual(ret['categories'], [{'name': 'work'}])

        with t.subTest('the keys are the documented ones, in order'):
            t.assertEqual(list(ret), ['date', 'active', 'categories'])

    @patch(f'{SRC}.CategoryJsonView', autospec=True)
    def test_categories(t, category_json_view: MagicMock) -> None:
        first = Mock(spec=Category)
        second = Mock(spec=Category)
        t.selection.categories = [first, second]

        ret = t.sjv.categories

        # One per category, in the selection's order.
        t.assertEqual(ret, [category_json_view.return_value] * 2)
        t.assertEqual(
            category_json_view.call_args_list,
            [call(first), call(second)],
        )


class CategoryJsonViewTests(TestCase):
    """Unit tests for battodo.view.selection.CategoryJsonView."""

    def setUp(t) -> None:
        t.category = Mock(spec=Category)
        t.category.name = 'work'
        t.category.hidden = 0
        t.cjv = CategoryJsonView(t.category)

    @patch.object(CategoryJsonView, 'rows', new_callable=PropertyMock)
    def test_data(t, rows: PropertyMock) -> None:
        row = Mock(spec=RowJsonView)
        row.data = {'title': 'task'}
        rows.return_value = [row]

        with t.subTest('a category carries its name and its tasks'):
            ret = t.cjv.data
            t.assertEqual(
                ret,
                {'name': 'work', 'hidden': 0, 'tasks': [{'title': 'task'}]},
            )

        with t.subTest('and it says how many it is holding back'):
            # Without the count, an abridged document reads exactly like
            # a complete one, and a reader cannot tell it should ask for
            # the rest.
            t.category.hidden = 4

            ret = t.cjv.data

            t.assertEqual(
                ret,
                {'name': 'work', 'hidden': 4, 'tasks': [{'title': 'task'}]},
            )

    @patch(f'{SRC}.RowJsonView', autospec=True)
    def test_rows(t, row_json_view: MagicMock) -> None:
        first = Mock(spec=Row)
        second = Mock(spec=Row)
        t.category.shown = [first, second]

        ret = t.cjv.rows

        # One per row the category shows, in its order.
        t.assertEqual(ret, [row_json_view.return_value] * 2)
        t.assertEqual(
            row_json_view.call_args_list,
            [call(first, 'work'), call(second, 'work')],
        )


class RowJsonViewTests(TestCase):
    """Unit tests for battodo.view.selection.RowJsonView."""

    def setUp(t) -> None:
        t.task = Mock(
            spec=[
                'task_id',
                'title',
                'loe',
                'due',
                'added',
                'repeat',
                'tags',
            ]
        )
        t.task.task_id = 'ab12cd'
        t.task.title = 'A task'
        t.task.loe = 2
        t.task.due = None
        t.task.added = '2026-07-29'
        t.task.repeat = None
        t.task.tags = ['home']

        t.row = Mock(spec=Row)
        t.row.task = t.task
        t.row.rank = 4.25
        t.row.priority = 3.0
        t.row.subtasks = 0
        t.rjv = RowJsonView(t.row, 'work')

    def test_data(t) -> None:
        with t.subTest('every stored field is carried through verbatim'):
            ret = t.rjv.data
            t.assertEqual(
                ret,
                {
                    'list': 'work',
                    'id': 'ab12cd',
                    'title': 'A task',
                    'rank': 4.25,
                    'priority': 3.0,
                    'loe': 2,
                    'due': None,
                    'added': '2026-07-29',
                    'repeat': None,
                    'tags': ['home'],
                    'subtasks': 0,
                },
            )

        with t.subTest('a rank is published to two decimal places'):
            t.row.rank = 1 + 7 / 30

            ret = t.rjv.data

            t.assertEqual(ret['rank'], 1.23)

        with t.subTest('the due date keeps its stored form, unlabelled'):
            t.task.due = '2026-08-04'
            ret = t.rjv.data
            t.assertEqual(ret['due'], '2026-08-04')

        with t.subTest('and open children are counted, not nested'):
            t.row.subtasks = 2

            ret = t.rjv.data

            t.assertEqual(ret['subtasks'], 2)


class ParseWindowsTests(TestCase):
    """Unit tests for battodo.view.selection.parse_windows."""

    def test_schedule(t) -> None:
        cases = {
            'an empty text schedules nothing': ('', {}),
            'and so does one of spaces alone': ('  ', {}),
            'one category, one window': (
                'a-list=mon-fri 9-17',
                {'a-list': [Window(0, 4, 9, 17)]},
            ),
            'spaces around the separators are read past': (
                ' a-list = mon 9-10 , tue 11-12 ; another-list=sat-sun 10-20',
                {
                    'a-list': [Window(0, 0, 9, 10), Window(1, 1, 11, 12)],
                    'another-list': [Window(5, 6, 10, 20)],
                },
            ),
        }

        for name, (text, expected) in cases.items():
            with t.subTest(name):
                ret = parse_windows(text)
                t.assertEqual(ret, expected)

    def test_refused(t) -> None:
        cases = {
            'an entry with no window': (
                'a-list',
                (
                    'a view.windows entry must read <category>=<window>: '
                    "'a-list'"
                ),
            ),
            'an entry with no category': (
                '=mon 9-10',
                (
                    'a view.windows entry must read <category>=<window>: '
                    "'=mon 9-10'"
                ),
            ),
            'an entry with nothing after the mark': (
                'a-list=',
                (
                    'a view.windows entry must read <category>=<window>: '
                    "'a-list='"
                ),
            ),
            'an empty entry after the last separator': (
                'a-list=mon 9-10;',
                "a view.windows entry must read <category>=<window>: ''",
            ),
            'a category named twice': (
                'a-list=mon 9-10; a-list=tue 9-10',
                "view.windows names a category twice: 'a-list'",
            ),
            'a second mark belongs to the windows': (
                'a-list=mon 9-10=x',
                (
                    'a view.windows window must read <days> <start>-<end>: '
                    "'mon 9-10=x'"
                ),
            ),
            'a window that does not read': (
                'a-list=someday 9-10',
                (
                    'a view.windows window must read <days> <start>-<end>: '
                    "'someday 9-10'"
                ),
            ),
        }

        for name, (text, message) in cases.items():
            with t.subTest(name):
                with t.assertRaises(ValueError) as caught:
                    parse_windows(text)

                t.assertEqual(str(caught.exception), message)


class ParseWindowTests(TestCase):
    """Unit tests for battodo.view.selection.parse_window."""

    def test_window(t) -> None:
        cases = {
            'one day': ('mon 9-17', Window(0, 0, 9, 17)),
            'a run of days, in any case': (
                'MON-Fri 9-17',
                Window(0, 4, 9, 17),
            ),
            'spaces around the separators': (
                ' sat - sun  10 - 20 ',
                Window(5, 6, 10, 20),
            ),
            'the whole of one day': ('sun 0-24', Window(6, 6, 0, 24)),
        }

        for name, (text, expected) in cases.items():
            with t.subTest(name):
                ret = parse_window(text)
                t.assertEqual(ret, expected)

    def test_refused(t) -> None:
        cases = {
            'a day the week does not have': 'someday 9-10',
            'no hours': 'mon',
            'no end hour': 'mon 9',
            'text after the hours': 'mon 9-10 later',
            'no space between the days and the hours': 'mon9-10',
            'days that run backwards': 'fri-mon 9-17',
            'hours that run past midnight': 'mon 22-2',
            'an empty span of hours': 'mon 9-9',
            'an hour past the end of the day': 'mon 0-25',
        }

        for name, text in cases.items():
            with t.subTest(name):
                with t.assertRaises(ValueError) as caught:
                    parse_window(text)

                t.assertEqual(
                    str(caught.exception),
                    'a view.windows window must read <days> <start>-<end>: '
                    f'{text!r}',
                )


class WindowTests(TestCase):
    """Unit tests for battodo.view.selection.Window."""

    def setUp(t) -> None:
        t.w = Window(0, 4, 9, 17)

    def test_holds(t) -> None:
        cases = {
            'its first day at its first hour': (0, 9, True),
            'its last day at its last hour': (4, 16, True),
            'the end hour is past the window': (0, 17, False),
            'an hour before it opens': (0, 8, False),
            'a day after its last': (5, 10, False),
        }

        for name, (day, hour, expected) in cases.items():
            with t.subTest(name):
                ret = t.w.holds(day, hour)
                t.assertEqual(ret, expected)


def at(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def at_hour(day: int, hour: int) -> datetime:
    """The instant `hour` o'clock falls on, `day` days into the week."""
    return datetime.combine(WEEK_START + timedelta(days=day), time(hour))


def opens(day: int, hour: int) -> set[str]:
    """The categories open on `day` at `hour`.

    The names of ALWAYS stay open at every hour. The window table adds
    the rest.
    """
    names = {'a-third-list', 'a-fourth-list'}
    for name, days, hours in WINDOWS:
        if day in days and hour in hours:
            names.add(name)
    return names


def stored(
    title: str,
    *,
    done: bool = False,
    due: str | None = None,
    repeat: str | None = None,
) -> Mock:
    """A stand-in task, holding what a list reads off one."""
    found = Mock(spec=['title', 'done', 'due', 'repeat'])
    found.title = title
    found.done = done
    found.due = due
    found.repeat = repeat
    return found
