from datetime import date, datetime, time, timedelta
from json import loads
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, Mock, patch, sentinel

from ..selection import (
    CATEGORY_ORDER,
    TOP_N,
    Category,
    Row,
    Selection,
    SourceError,
    TodoList,
)

SRC = 'battodo.view.selection'
TODAY = date(2026, 8, 5)
# What the parser reads back from each stored due date the cases use.
PARSED_DUE = {
    'a-later-date': date(2026, 8, 20),
    'an-earlier-date': date(2026, 8, 4),
    'an-unreadable-date': None,
}
# A Monday, so a weekday number added to it names that day.
WEEK_START = date(2026, 8, 3)
# The windows the clock opens, as a table: the category, the weekday
# numbers it opens on, and the hours it stays open on them.
WINDOWS = (
    ('work', range(5), range(9, 17)),
    ('chores', range(5), range(17, 21)),
    ('chores', range(5, 7), range(10, 20)),
)
# Every hour of one week. A sweep over it names the day and the hour.
HOURS = [(day, hour) for day in range(7) for hour in range(24)]


def autopatch(case: TestCase, target: str) -> Mock:
    """Stand in for `target`, put back when `case` finishes."""
    patcher = patch(f'{SRC}.{target}', autospec=True)
    double = patcher.start()
    case.addCleanup(patcher.stop)
    return double


def at(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def published(title: str) -> Mock:
    """A stand-in row, holding only the record a document reads off it."""
    found = Mock(spec=['data'])
    found.data = {'title': title}
    return found


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


def at_hour(day: int, hour: int) -> datetime:
    """The instant `hour` o'clock falls on, `day` days into the week."""
    return datetime.combine(WEEK_START + timedelta(days=day), time(hour))


def opens(day: int, hour: int) -> set[str]:
    """The categories open on `day` at `hour`.

    Three categories stay open at every hour. The window table adds
    the rest.
    """
    names = {'study', 'career', 'events'}
    for name, days, hours in WINDOWS:
        if day in days and hour in hours:
            names.add(name)
    return names


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

        t.task = Mock(
            spec=[
                'task_id',
                'title',
                'loe',
                'due',
                'added',
                'repeat',
                'tags',
                'children',
            ]
        )
        t.task.task_id = 'ab12cd'
        t.task.title = 'A task'
        t.task.loe = 2
        t.task.due = None
        t.task.added = '2026-07-29'
        t.task.repeat = None
        t.task.tags = ['home']
        t.task.children = []

        t.r = Row(t.task, TODAY)

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
        t.rank.assert_called_once_with(t.task, TODAY)

    def test_data(t) -> None:
        with t.subTest('every stored field is carried through verbatim'):
            ret = t.r.data

            t.assertEqual(
                ret,
                {
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
            t.r.__dict__.pop('data', None)
            t.r.rank = 1 + 7 / 30

            ret = t.r.data

            t.assertEqual(ret['rank'], 1.23)

        with t.subTest('the due date keeps its stored form, unlabelled'):
            t.r.__dict__.pop('data', None)
            t.r.due_label = 'OVERDUE'
            t.task.due = '2026-08-04'

            ret = t.r.data

            t.assertEqual(ret['due'], '2026-08-04')

        with t.subTest('and open children are counted, not nested'):
            t.r.__dict__.pop('data', None)
            t.r.subtasks = 2

            ret = t.r.data

            t.assertEqual(ret['subtasks'], 2)

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

    def test_cells(t) -> None:
        with t.subTest('rank and priority are shown to one decimal'):
            ret = t.r.cells
            t.assertEqual(ret[:2], ('4.2', '3.0'))

        with t.subTest('an unestimated task leaves its column empty'):
            t.r.__dict__.pop('cells', None)
            t.task.loe = None

            ret = t.r.cells

            t.assertEqual(ret[2], '')

        with t.subTest('a level of effort is shown when there is one'):
            t.r.__dict__.pop('cells', None)
            t.task.loe = 2

            ret = t.r.cells

            t.assertEqual(ret[2], '2')

        with t.subTest('the title carries its badge'):
            t.r.__dict__.pop('cells', None)
            t.r.badge = ' (+1)'

            ret = t.r.cells

            t.assertEqual(ret[3], 'A task (+1)')

        with t.subTest('and the due column carries its label'):
            t.r.__dict__.pop('cells', None)
            t.r.due_label = 'OVERDUE'

            ret = t.r.cells

            t.assertEqual(ret[4], 'OVERDUE')

        with t.subTest('there is one cell for each of the five columns'):
            ret = t.r.cells
            t.assertEqual(len(ret), 5)

    def test_badge(t) -> None:
        with t.subTest('a task with nothing outstanding wears no badge'):
            ret = t.r.badge
            t.assertEqual(ret, '')

        with t.subTest('otherwise the badge carries the count'):
            t.r.__dict__.pop('badge', None)
            t.r.subtasks = 2

            ret = t.r.badge

            t.assertEqual(ret, ' (+2)')

    def test_due_label(t) -> None:
        cases = {
            'no due date reads as nothing at all': (None, None, ''),
            'a date already past is called out': (
                '2026-08-04',
                date(2026, 8, 4),
                'OVERDUE',
            ),
            'so is the day itself': ('2026-08-05', TODAY, 'TODAY'),
            'a date still ahead shows as written': (
                '2026-08-20',
                date(2026, 8, 20),
                '2026-08-20',
            ),
            'and a date the parser cannot read shows verbatim': (
                'YYYY-MM-DD',
                None,
                'YYYY-MM-DD',
            ),
        }

        for name, (due, parsed, expected) in cases.items():
            with t.subTest(name):
                t.r.__dict__.pop('due_label', None)
                t.task.due = due
                t.r.parsed_due = parsed

                ret = t.r.due_label

                t.assertEqual(ret, expected)

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


class TodoListTests(TestCase):
    """Unit tests for battodo.view.selection.TodoList."""

    def setUp(t) -> None:
        t.path = Mock(spec=Path)
        t.path.stem = 'work'
        t.path.read_text.return_value = '## Open\n\n- [ ] A task [P:3]\n'
        t.tl = TodoList(t.path, TODAY)

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

    @patch(f'{SRC}.parse_date', autospec=True)
    def test_visible(t, parse_date: MagicMock) -> None:
        parse_date.side_effect = lambda value: PARSED_DUE.get(value)
        t.tl.document = Mock(spec=['tasks'])
        t.tl.document.tasks = [
            stored('An open task'),
            stored('A finished task', done=True),
            stored(
                'A later recurrence',
                due='a-later-date',
                repeat='7d',
            ),
            stored('A later one-off', due='a-later-date'),
            stored(
                'A late recurrence',
                due='an-earlier-date',
                repeat='7d',
            ),
            stored(
                'A placeholder due date',
                due='an-unreadable-date',
                repeat='7d',
            ),
        ]

        ret = t.tl.visible

        # Only a recurrence still ahead of today is suppressed. A
        # one-off keeps its place however far off it is, and a date the
        # parser cannot read is no reason to drop an item.
        t.assertEqual(
            [row.task.title for row in ret],
            [
                'An open task',
                'A later one-off',
                'A late recurrence',
                'A placeholder due date',
            ],
        )

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
            t.tl.visible = [low, high]

            ret = t.tl.rows

            t.assertEqual(ret, [high, low])

        with t.subTest('a list with nothing open comes back empty'):
            t.tl.__dict__.pop('rows')
            t.tl.visible = []

            ret = t.tl.rows

            t.assertEqual(ret, [])

    def test_order(t) -> None:
        with t.subTest('a named category sorts by its place in the order'):
            ret = t.tl.order
            t.assertEqual(ret, (CATEGORY_ORDER.index('work'), 'work'))

        with t.subTest('an unknown name sorts after every named one'):
            t.tl.category = 'side-quests'
            ret = t.tl.order
            t.assertEqual(ret, (len(CATEGORY_ORDER), 'side-quests'))

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


class SelectionTests(TestCase):
    """Unit tests for battodo.view.selection.Selection."""

    def setUp(t) -> None:
        t.discover_lists = autopatch(t, 'discover_lists')

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
        for day, hour in HOURS:
            with t.subTest(day=day, hour=hour):
                ret = Selection(
                    t.directory, at_hour(day, hour), show_all=False
                ).active

                t.assertEqual(ret, opens(day, hour))

    def test_weekday(t) -> None:
        with t.subTest('a day the working week covers'):
            ret = t.s.weekday
            t.assertTrue(ret)

        with t.subTest('and one it does not'):
            t.s.__dict__.pop('weekday', None)
            t.s.day = 5

            ret = t.s.weekday

            t.assertFalse(ret)

    def test_day(t) -> None:
        # 2026-08-05 is a Wednesday, the third day of the week.
        ret = t.s.day
        t.assertEqual(ret, 2)

    def test_hour(t) -> None:
        ret = t.s.hour
        t.assertEqual(ret, 10)

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

            ret = t.s.lists

            t.assertEqual(ret, [earlier, later])
            t.discover_lists.assert_called_with(t.resolved)

    def test_shows(t) -> None:
        t.s.active = {'work', 'study'}

        cases = {
            'a named category inside its window shows': (
                t.todo('work'),
                True,
            ),
            'a named category outside its window does not': (
                t.todo('chores'),
                False,
            ),
            'a name the order does not know has no window to be outside': (
                t.todo('side-quests'),
                True,
            ),
            'a list that opted out never shows': (
                t.todo('work', parked=True),
                False,
            ),
            'and opting out beats having an unknown name': (
                t.todo('side-quests', parked=True),
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
                t.todo('chores'),
                True,
            ),
            'an open one is unaffected by the asking': (
                t.todo('work'),
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

    def category(t, name: str, hidden: int = 0, shown=('task',)) -> Mock:
        """A stand-in category, holding what the document reads off one."""
        stub = Mock(spec=['name', 'shown', 'hidden'])
        stub.name = name
        stub.shown = [published(title) for title in shown]
        stub.hidden = hidden
        return stub

    def setUpData(t) -> None:
        """Point the selection at a stub category and an active set."""
        t.s.active = {'work', 'career'}
        t.s.categories = [t.category('work')]

    def test_data(t) -> None:
        t.setUpData()

        ret = t.s.data

        with t.subTest('the day is recorded in its stored form'):
            t.assertEqual(ret['date'], '2026-08-05')

        with t.subTest('the active set reads in a settled order'):
            t.assertEqual(ret['active'], ['career', 'work'])

        with t.subTest('a category carries its name and its tasks'):
            t.assertEqual(
                ret['categories'],
                [
                    {
                        'name': 'work',
                        'hidden': 0,
                        'tasks': [{'title': 'task'}],
                    }
                ],
            )

        with t.subTest('and it says how many it is holding back'):
            # Without the count, an abridged document reads exactly like
            # a complete one, and a reader cannot tell it should ask for
            # the rest.
            t.s.categories = [t.category('work', hidden=4)]
            t.s.__dict__.pop('data')

            abridged = t.s.data

            t.assertEqual(
                abridged['categories'],
                [
                    {
                        'name': 'work',
                        'hidden': 4,
                        'tasks': [{'title': 'task'}],
                    }
                ],
            )

        with t.subTest('the keys are the documented ones, in order'):
            t.assertEqual(list(t.s.data), ['date', 'active', 'categories'])

    def test_json(t) -> None:
        t.setUpData()

        ret = t.s.json

        with t.subTest('the document is the serialized data'):
            t.assertEqual(loads(ret), t.s.data)

        with t.subTest('laid out for a person to read as well'):
            lines = ret.split('\n')

            t.assertGreater(len(lines), 1)
            t.assertTrue(lines[1].startswith('  "'))
            t.assertFalse(lines[1].startswith('   '))


class SelectionFromConfigTests(TestCase):
    """Unit tests for battodo.view.selection.Selection.from_config.

    The decode from configuration strings to what a selection takes.
    """

    def setUp(t) -> None:
        t.now = at('2026-08-05T10:30')
        t.conf = Mock(spec=['view', 'show_all'])
        t.conf.view = Mock(spec=['source_dir', 'top'])
        t.conf.view.source_dir = '~/a-source-dir'
        t.conf.view.top = '2'
        t.conf.show_all = True

    def test_from_config(t) -> None:
        selection = Selection.from_config(t.conf, t.now)

        with t.subTest('the source directory is left unexpanded'):
            t.assertEqual(selection.directory, Path('~/a-source-dir'))

        with t.subTest('the clock is the one it was given'):
            t.assertEqual(selection.now, t.now)

        with t.subTest('the count is read as a number'):
            t.assertEqual(selection.top_n, 2)

        with t.subTest('and the flag as a flag'):
            t.assertTrue(selection.show_all)

        with t.subTest('an unsupplied flag reads as off'):
            conf = Mock(spec=['view'])
            conf.view = Mock(spec=['source_dir', 'top'])
            conf.view.source_dir = '~/a-source-dir'
            conf.view.top = str(TOP_N)

            ret = Selection.from_config(conf, t.now)

            t.assertFalse(ret.show_all)

        with t.subTest('a count below one is refused'):
            t.conf.view.top = '0'
            with t.assertRaises(ValueError):
                Selection.from_config(t.conf, t.now)
