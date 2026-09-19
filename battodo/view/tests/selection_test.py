from datetime import date, datetime
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
    TodoDocument,
    TodoList,
    active_categories,
    open_children,
    sort_key,
    task_entry,
    visible_tasks,
)

SRC = 'battodo.view.selection'
TODAY = date(2026, 8, 5)
# What the parser reads back from each stored due date the cases use.
PARSED_DUE = {
    'a-later-date': date(2026, 8, 20),
    'an-earlier-date': date(2026, 8, 4),
    'an-unreadable-date': None,
}


def autopatch(case: TestCase, target: str) -> Mock:
    """Stand in for `target`, put back when `case` finishes."""
    patcher = patch(f'{SRC}.{target}', autospec=True)
    double = patcher.start()
    case.addCleanup(patcher.stop)
    return double


def at(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


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


class ActiveCategoriesTests(TestCase):
    """Unit tests for battodo.view.selection.active_categories.

    Each window is half-open: it opens on its first hour and is shut
    again on its closing hour, so the two never overlap.
    """

    def test_windows(t) -> None:
        always = {'study', 'career', 'events'}
        work = always | {'work'}
        chores = always | {'chores'}
        cases = {
            # Wed 2026-08-05: work 09-17, then chores 17-21.
            'weekday before work': ('2026-08-05T08:00', always),
            'weekday work opens': ('2026-08-05T09:00', work),
            'weekday work last hour': ('2026-08-05T16:00', work),
            'weekday work closes as chores open': (
                '2026-08-05T17:00',
                chores,
            ),
            'weekday chores last hour': ('2026-08-05T20:00', chores),
            'weekday chores close': ('2026-08-05T21:00', always),
            # Sat 2026-08-08: chores 10-20, and no work at any hour.
            'weekend before chores': ('2026-08-08T09:00', always),
            'weekend chores open': ('2026-08-08T10:00', chores),
            'weekend midday is never work': ('2026-08-08T12:00', chores),
            'weekend chores last hour': ('2026-08-08T19:00', chores),
            'weekend chores close': ('2026-08-08T20:00', always),
        }

        for name, (stamp, expected) in cases.items():
            with t.subTest(name):
                ret = active_categories(at(stamp))
                t.assertEqual(ret, expected)


class VisibleTasksTests(TestCase):
    """Unit tests for battodo.view.selection.visible_tasks."""

    def test_shown(t) -> None:
        doc = TodoDocument(
            '## Open\n'
            '- [ ] Open item [P:2]\n'
            '- [x] Finished item [P:2]\n'
            '- [ ] Later recurrence [P:2] [DUE:2026-09-01] [REPEAT:7d]\n'
            '- [ ] Later one-off [P:2] [DUE:2026-09-01]\n'
            '- [ ] Late recurrence [P:2] [DUE:2026-08-04] [REPEAT:7d]\n'
            '- [ ] Recurrence due today [P:2] [DUE:2026-08-05] [REPEAT:7d]\n'
            '- [ ] Placeholder date [P:2] [DUE:YYYY-MM-DD] [REPEAT:7d]\n'
        )

        titles = [task.title for task in visible_tasks(doc, TODAY)]

        # Only a recurrence still ahead of today is suppressed. Due
        # today it is the occurrence that has come round, and hiding it
        # is how a repeating chore silently goes undone. A one-off keeps
        # its place however far off it is, and an unreadable date is no
        # reason to drop an item.
        t.assertEqual(
            titles,
            [
                'Open item',
                'Later one-off',
                'Late recurrence',
                'Recurrence due today',
                'Placeholder date',
            ],
        )


class SortKeyTests(TestCase):
    """Unit tests for battodo.view.selection.sort_key."""

    def setUp(t) -> None:
        t.rank = autopatch(t, 'rank')

    def test_order(t) -> None:
        doc = TodoDocument(
            '## Open\n'
            '- [ ] B undated [P:3]\n'
            '- [ ] A undated [P:3]\n'
            '- [ ] Dated [P:3] [DUE:2026-09-30]\n'
            '- [ ] Higher [P:5]\n'
        )
        ranked = {'Higher': 5.0}
        t.rank.side_effect = lambda task, today: ranked.get(task.title, 3.0)

        ordered = [
            task.title
            for task in sorted(doc.tasks, key=lambda x: sort_key(x, TODAY))
        ]

        with t.subTest('rank decides first, and the highest leads'):
            t.assertEqual(ordered[0], 'Higher')

        with t.subTest('a due date sorts ahead of none at equal rank'):
            t.assertEqual(ordered[1], 'Dated')

        with t.subTest('the title breaks what is left'):
            t.assertEqual(ordered[2:], ['A undated', 'B undated'])

    def test_key(t) -> None:
        # The key itself is rank, then due, then title.
        t.rank.return_value = 3.0
        task = TodoDocument('## Open\n- [ ] Solo [P:3]\n').tasks[0]

        ret = sort_key(task, TODAY)

        t.assertEqual(ret, (-3.0, 'zzzz', 'Solo'))
        t.rank.assert_called_once_with(task, TODAY)


class OpenChildrenTests(TestCase):
    """Unit tests for battodo.view.selection.open_children."""

    def test_children(t) -> None:
        doc = TodoDocument(
            '## Open\n'
            '- [ ] Parent [P:3]\n'
            '  - [ ] A subtask [LOE:1]\n'
            '  - [ ] A checklist item\n'
            '  - [x] A finished child [LOE:1]\n'
            '- [ ] Childless [P:3]\n'
        )
        parent, childless = doc.tasks

        children = open_children(parent)
        empty = open_children(childless)

        # Subtasks and checklist items both count.
        t.assertEqual(
            [child.title for child in children],
            ['A subtask', 'A checklist item'],
        )
        t.assertEqual(empty, [])


class TaskEntryTests(TestCase):
    """Unit tests for battodo.view.selection.task_entry."""

    def setUp(t) -> None:
        t.rank = autopatch(t, 'rank')
        t.multiplier = autopatch(t, 'multiplier')
        t.open_children = autopatch(t, 'open_children')
        t.rank.return_value = 1.0
        t.multiplier.return_value = 3.0
        t.open_children.return_value = []

        t.task = Mock(
            spec=['task_id', 'title', 'loe', 'due', 'added', 'repeat', 'tags']
        )
        t.task.task_id = 'ab12cd'
        t.task.title = 'A task'
        t.task.loe = 2
        t.task.due = '2026-08-20'
        t.task.added = '2026-07-29'
        t.task.repeat = None
        t.task.tags = ['home']

    def test_fields(t) -> None:
        with t.subTest('stored fields are carried through verbatim'):
            ret = task_entry(t.task, TODAY)

            t.assertEqual(
                ret,
                {
                    'id': 'ab12cd',
                    'title': 'A task',
                    'rank': 1.0,
                    'priority': 3.0,
                    'loe': 2,
                    'due': '2026-08-20',
                    'added': '2026-07-29',
                    'repeat': None,
                    'tags': ['home'],
                    'subtasks': 0,
                },
            )

        with t.subTest('the due date keeps its stored form, unlabelled'):
            t.task.due = '2026-08-04'
            ret = task_entry(t.task, TODAY)
            t.assertEqual(ret['due'], '2026-08-04')

    def test_rank(t) -> None:
        t.rank.return_value = 1 + 7 / 30

        entry = task_entry(t.task, TODAY)

        with t.subTest('a rank is published to two decimal places'):
            t.assertEqual(entry['rank'], 1.23)
            t.assertNotEqual(entry['rank'], t.rank.return_value)

        with t.subTest('the clock reaches the rank'):
            t.rank.assert_called_with(t.task, TODAY)

    def test_children(t) -> None:
        t.open_children.return_value = [sentinel.child, sentinel.child]

        ret = task_entry(t.task, TODAY)

        # Open children are counted, not nested.
        t.assertEqual(ret['subtasks'], 2)


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
        t.rank = autopatch(t, 'rank')
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

    def test_tasks(t) -> None:
        with t.subTest('open tasks come back in the order rank gives'):
            ranked = {'Low': 1.0, 'High': 5.0}
            t.rank.side_effect = lambda task, today: ranked[task.title]
            t.tl.text = (
                '## Open\n'
                '- [ ] Low [P:1]\n'
                '- [ ] High [P:5]\n'
                '- [x] Gone [P:9]\n'
            )

            ret = t.tl.tasks

            t.assertEqual([task.title for task in ret], ['High', 'Low'])

        with t.subTest('a list with nothing open comes back empty'):
            t.tl.__dict__.pop('tasks')
            t.tl.text = '## Open\n\n- [x] Gone [P:9]\n'

            ret = t.tl.tasks

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
        t.tasks = TodoDocument(
            '## Open\n' + ''.join(f'- [ ] Item {n} [P:3]\n' for n in range(6))
        ).tasks
        t.c = Category('work', t.tasks, 2)

    def test_shown(t) -> None:
        with t.subTest('a limit takes the top of the list'):
            ret = t.c.shown
            t.assertEqual([task.title for task in ret], ['Item 0', 'Item 1'])

        with t.subTest('no limit shows every one'):
            t.c.limit = None
            ret = t.c.shown
            t.assertEqual(ret, t.tasks)

        with t.subTest('a limit past the end shows every one too'):
            t.c.limit = 99
            ret = t.c.shown
            t.assertEqual(ret, t.tasks)

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

    def test_tasks(t) -> None:
        ret = t.c.tasks
        t.assertEqual(ret, t.tasks)


class SelectionTests(TestCase):
    """Unit tests for battodo.view.selection.Selection."""

    def setUp(t) -> None:
        t.discover_lists = autopatch(t, 'discover_lists')
        t.active_categories = autopatch(t, 'active_categories')

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

    def todo(t, category: str, *, parked: bool = False, tasks=('a',)) -> Mock:
        """A stand-in list, holding only what a selection reads off one."""
        found = Mock(spec=['category', 'parked', 'tasks', 'order'])
        found.category = category
        found.parked = parked
        found.tasks = list(tasks)
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
        ret = t.s.active
        t.assertEqual(ret, t.active_categories.return_value)
        t.active_categories.assert_called_once_with(t.s.now)

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

    def test_lists(t) -> None:
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
            with patch(f'{SRC}.TodoList', autospec=True) as todo_list:
                todo_list.side_effect = [later, earlier]
                ret = t.s.lists

            t.assertEqual(ret, [earlier, later])
            t.discover_lists.assert_called_with(t.resolved)

    def test_shows(t) -> None:
        t.active_categories.return_value = {'work', 'study'}

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
        t.active_categories.return_value = {'work', 'study'}
        shown, shut, empty = (
            t.todo('work'),
            t.todo('chores'),
            t.todo('study', tasks=()),
        )
        t.s.lists = [shown, shut, empty]

        categories = t.s.categories

        with t.subTest('only the lists this view shows become categories'):
            t.assertEqual([c.name for c in categories], ['work'])

        with t.subTest("each carries that list's tasks"):
            t.assertEqual(categories[0].tasks, shown.tasks)

        with t.subTest('and the limit the view was asked for'):
            t.assertEqual(categories[0].limit, TOP_N)

        with t.subTest('a list with nothing open contributes no category'):
            t.assertNotIn('study', [c.name for c in categories])

    def category(t, name: str, hidden: int = 0, shown=('task',)) -> Mock:
        """A stand-in category, holding what the document reads off one."""
        stub = Mock(spec=['name', 'shown', 'hidden'])
        stub.name = name
        stub.shown = list(shown)
        stub.hidden = hidden
        return stub

    def setUpData(t) -> Mock:
        """Point the selection at stub categories, intercept task_entry."""
        task_entry_double = autopatch(t, 'task_entry')
        task_entry_double.side_effect = lambda task, today: {
            'title': str(task)
        }
        t.active_categories.return_value = {'work', 'career'}
        t.s.categories = [t.category('work')]
        return task_entry_double

    def test_data(t) -> None:
        task_entry_double = t.setUpData()

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

        with t.subTest('only the tasks the selection shows are serialized'):
            task_entry_double.assert_called_once_with('task', TODAY)

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
