from datetime import date, datetime
from json import loads
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, Mock, patch

from ..selection import (
    CATEGORY_ORDER,
    COUNT_ERROR,
    TOP_N,
    Category,
    Selection,
    SourceError,
    TodoList,
    active_categories,
    category_order,
    discover_lists,
    item_count,
    open_children,
    parse,
    sort_key,
    task_entry,
    visible_tasks,
)

SRC = 'battodo.view.selection'
TODAY = date(2026, 8, 5)


def autopatch(case: TestCase, target: str) -> Mock:
    """Stand in for `target`, put back when `case` finishes."""
    patcher = patch(f'{SRC}.{target}', autospec=True)
    double = patcher.start()
    case.addCleanup(patcher.stop)
    return double


def at(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


class ActiveCategoriesTests(TestCase):
    """Each window is half-open: it opens on its first hour and is shut
    again on its closing hour, so the two never overlap."""

    def test_active_categories(t) -> None:
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
                t.assertEqual(active_categories(at(stamp)), expected)


def md(name: str, text: str) -> MagicMock:
    """A stand-in file: one that can be read, and can be sorted."""
    path = MagicMock(spec=Path)
    path.name = name
    path.read_text.return_value = text
    path.__lt__.side_effect = lambda other: name < other.name
    return path


class DiscoverListsTests(TestCase):
    def setUp(t) -> None:
        t.work = md('work.md', '# W\n\n## Open\n\n- [ ] A\n')
        t.backlog = md('backlog.md', '## Open\n\n- [ ] B\n')
        t.prose = md('SCHEMA.md', '# Schema\n\nprose, and no open section\n')
        t.dir = Mock(spec=Path)
        t.dir.is_dir.return_value = True
        t.dir.glob.return_value = [t.work, t.prose, t.backlog]

    def test_discover_lists(t) -> None:
        with t.subTest('a list is a file carrying an open section'):
            t.assertEqual(discover_lists(t.dir), [t.backlog, t.work])

        with t.subTest('which is what an ad-hoc name is admitted on'):
            t.assertIn(t.backlog, discover_lists(t.dir))

        with t.subTest('prose without one is not a list'):
            t.assertNotIn(t.prose, discover_lists(t.dir))

        with t.subTest('they come back in name order'):
            t.assertEqual(
                [path.name for path in discover_lists(t.dir)],
                ['backlog.md', 'work.md'],
            )

        with t.subTest('and only markdown is ever considered'):
            t.dir.glob.assert_called_with('*.md')

        with t.subTest('a directory that is not there yields nothing'):
            t.dir.is_dir.return_value = False
            t.assertEqual(discover_lists(t.dir), [])

        with t.subTest('and is not searched at all'):
            t.dir.glob.reset_mock()
            discover_lists(t.dir)
            t.dir.glob.assert_not_called()


class VisibleTasksTests(TestCase):
    def test_visible_tasks(t) -> None:
        doc = parse(
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
    def test_sort_key(t) -> None:
        doc = parse(
            '## Open\n'
            '- [ ] B undated [P:3]\n'
            '- [ ] A undated [P:3]\n'
            '- [ ] Dated [P:3] [DUE:2026-09-30]\n'
            '- [ ] Higher [P:5]\n'
        )

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

        with t.subTest('the key itself is rank, then due, then title'):
            task = parse('## Open\n- [ ] Solo [P:3]\n').tasks[0]
            t.assertEqual(sort_key(task, TODAY), (-3.0, 'zzzz', 'Solo'))


class CategoryOrderTests(TestCase):
    def test_category_order(t) -> None:
        with t.subTest('the named categories lead, in their own order'):
            t.assertEqual(
                sorted(['career', 'work', 'chores'], key=category_order),
                ['work', 'chores', 'career'],
            )

        with t.subTest('an ad-hoc name follows them, alphabetically'):
            t.assertEqual(
                sorted(['van', 'career', 'arts'], key=category_order),
                ['career', 'arts', 'van'],
            )


class OpenChildrenTests(TestCase):
    def test_open_children(t) -> None:
        doc = parse(
            '## Open\n'
            '- [ ] Parent [P:3]\n'
            '  - [ ] A subtask [LOE:1]\n'
            '  - [ ] A checklist item\n'
            '  - [x] A finished child [LOE:1]\n'
            '- [ ] Childless [P:3]\n'
        )
        parent, childless = doc.tasks

        with t.subTest('subtasks and checklist items both count'):
            t.assertEqual(
                [child.title for child in open_children(parent)],
                ['A subtask', 'A checklist item'],
            )

        with t.subTest('a task with no children has none open'):
            t.assertEqual(open_children(childless), [])


class TaskEntryTests(TestCase):
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

    def test_task_entry(t) -> None:
        with t.subTest('stored fields are carried through verbatim'):
            t.assertEqual(
                task_entry(t.task, TODAY),
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
            t.assertEqual(task_entry(t.task, TODAY)['due'], '2026-08-04')

        with t.subTest('a rank is published to two decimal places'):
            t.rank.return_value = 1 + 7 / 30
            entry = task_entry(t.task, TODAY)
            t.assertEqual(entry['rank'], 1.23)
            t.assertNotEqual(entry['rank'], t.rank.return_value)

        with t.subTest('the clock reaches the rank'):
            t.rank.assert_called_with(t.task, TODAY)

        with t.subTest('open children are counted, not nested'):
            t.open_children.return_value = [Mock(spec=[]), Mock(spec=[])]
            t.assertEqual(task_entry(t.task, TODAY)['subtasks'], 2)


class TodoListTests(TestCase):
    def setUp(t) -> None:
        t.path = Mock(spec=Path)
        t.path.stem = 'work'
        t.path.read_text.return_value = '## Open\n\n- [ ] A task [P:3]\n'
        t.tl = TodoList(t.path, TODAY)

    def test_category(t) -> None:
        t.assertEqual(t.tl.category, 'work')

    def test_text(t) -> None:
        with t.subTest('the file is read through'):
            t.assertEqual(t.tl.text, '## Open\n\n- [ ] A task [P:3]\n')

        with t.subTest('and read only the once'):
            again = t.tl.text
            t.assertEqual(again, t.tl.text)
            t.path.read_text.assert_called_once_with()

    def test_parked(t) -> None:
        with t.subTest('a list with no marker is not parked'):
            t.assertFalse(t.tl.parked)

        with t.subTest('the marker anywhere in the file parks it'):
            t.tl.__dict__.pop('parked')
            t.tl.text = '<!-- battodo:parked -->\n## Open\n\n- [ ] A [P:1]\n'
            t.assertTrue(t.tl.parked)

    def test_tasks(t) -> None:
        with t.subTest('open tasks come back in view order'):
            t.tl.text = (
                '## Open\n'
                '- [ ] Low [P:1]\n'
                '- [ ] High [P:5]\n'
                '- [x] Gone [P:9]\n'
            )
            t.assertEqual([task.title for task in t.tl.tasks], ['High', 'Low'])

        with t.subTest('a list with nothing open comes back empty'):
            t.tl.__dict__.pop('tasks')
            t.tl.text = '## Open\n\n- [x] Gone [P:9]\n'
            t.assertEqual(t.tl.tasks, [])

    def test_order(t) -> None:
        with t.subTest('a named category sorts by its place in the order'):
            t.assertEqual(t.tl.order, (CATEGORY_ORDER.index('work'), 'work'))

        with t.subTest('an unknown name sorts after every named one'):
            t.tl.category = 'side-quests'
            t.assertEqual(t.tl.order, (len(CATEGORY_ORDER), 'side-quests'))

        with t.subTest('and unknown names sort among themselves by name'):
            t.tl.category = 'backlog'
            first = t.tl.order
            t.tl.category = 'side-quests'
            t.assertLess(first, t.tl.order)


class CategoryTests(TestCase):
    def setUp(t) -> None:
        t.tasks = parse(
            '## Open\n' + ''.join(f'- [ ] Item {n} [P:3]\n' for n in range(6))
        ).tasks
        t.c = Category('work', t.tasks, 2)

    def test_shown(t) -> None:
        with t.subTest('a limit takes the top of the list'):
            t.assertEqual(
                [task.title for task in t.c.shown], ['Item 0', 'Item 1']
            )

        with t.subTest('no limit shows every one'):
            t.c.limit = None
            t.assertEqual(t.c.shown, t.tasks)

        with t.subTest('a limit past the end shows every one too'):
            t.c.limit = 99
            t.assertEqual(t.c.shown, t.tasks)

    def test_hidden(t) -> None:
        with t.subTest('what the limit held back is counted'):
            t.assertEqual(t.c.hidden, 4)

        with t.subTest('nothing is held back without a limit'):
            t.c.limit = None
            t.assertEqual(t.c.hidden, 0)

    def test_name(t) -> None:
        t.assertEqual(t.c.name, 'work')

    def test_tasks(t) -> None:
        t.assertEqual(t.c.tasks, t.tasks)


class SelectionTests(TestCase):
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
        t.assertEqual(t.s.today, TODAY)

    def test_limit(t) -> None:
        with t.subTest('an abridged view stops at the top few'):
            t.assertEqual(t.s.limit, TOP_N)

        with t.subTest('an explicit count replaces the default'):
            t.s.top_n = 2
            t.assertEqual(t.s.limit, 2)

        with t.subTest('asking for everything lifts the limit'):
            t.s.show_all = True
            t.assertIsNone(t.s.limit)

    def test_source(t) -> None:
        with t.subTest('the path is expanded and resolved'):
            t.assertEqual(t.s.source, t.resolved)
            t.directory.expanduser.assert_called_once_with()

        with t.subTest('a directory that is not there is an error'):
            t.s.__dict__.pop('source')
            t.resolved.is_dir.return_value = False
            with t.assertRaises(SourceError) as caught:
                _ = t.s.source
            t.assertIn(str(t.resolved), str(caught.exception))

    def test_active(t) -> None:
        t.assertEqual(t.s.active, t.active_categories.return_value)
        t.active_categories.assert_called_once_with(t.s.now)

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
            paths = [Mock(spec=Path), Mock(spec=Path)]
            t.discover_lists.return_value = paths
            later, earlier = t.todo('study'), t.todo('work')
            later.order, earlier.order = (2, 'study'), (0, 'work')
            with patch(f'{SRC}.TodoList', autospec=True) as todo_list:
                todo_list.side_effect = [later, earlier]
                t.assertEqual(t.s.lists, [earlier, later])
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
                t.assertEqual(t.s.shows(found), expected)

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
                t.assertEqual(t.s.shows(found), expected)

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

        with t.subTest('the day is recorded in its stored form'):
            t.assertEqual(t.s.data['date'], '2026-08-05')

        with t.subTest('the active set reads in a settled order'):
            t.assertEqual(t.s.data['active'], ['career', 'work'])

        with t.subTest('a category carries its name and its tasks'):
            t.assertEqual(
                t.s.data['categories'],
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
            t.assertEqual(
                t.s.data['categories'],
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

        with t.subTest('the document is the serialized data'):
            t.assertEqual(loads(t.s.json), t.s.data)

        with t.subTest('laid out for a person to read as well'):
            lines = t.s.json.split('\n')
            t.assertGreater(len(lines), 1)
            t.assertTrue(lines[1].startswith('  "'))
            t.assertFalse(lines[1].startswith('   '))


class ItemCountTests(TestCase):
    def test_item_count(t) -> None:
        with t.subTest('a configured count is read as a number'):
            t.assertEqual(item_count('2'), 2)

        for value in ('0', '-1', 'five', ''):
            with (
                t.subTest(f'{value!r} is not a count'),
                t.assertRaises(ValueError) as caught,
            ):
                item_count(value)
            t.assertIn(COUNT_ERROR, str(caught.exception))


class SelectionFromConfigTests(TestCase):
    """The decode from configuration strings to what a selection takes."""

    def setUp(t) -> None:
        t.now = at('2026-08-05T10:30')
        t.conf = Mock(spec=['view', 'show_all'])
        t.conf.view = Mock(spec=['source_dir', 'top'])
        t.conf.view.source_dir = '~/todo'
        t.conf.view.top = '2'
        t.conf.show_all = True

    def test_from_config(t) -> None:
        selection = Selection.from_config(t.conf, t.now)

        with t.subTest('the source directory is left unexpanded'):
            t.assertEqual(selection.directory, Path('~/todo'))

        with t.subTest('the clock is the one it was given'):
            t.assertEqual(selection.now, t.now)

        with t.subTest('the count is read as a number'):
            t.assertEqual(selection.top_n, 2)

        with t.subTest('and the flag as a flag'):
            t.assertTrue(selection.show_all)

        with t.subTest('an unsupplied flag reads as off'):
            conf = Mock(spec=['view'])
            conf.view = Mock(spec=['source_dir', 'top'])
            conf.view.source_dir = '~/todo'
            conf.view.top = str(TOP_N)

            t.assertFalse(Selection.from_config(conf, t.now).show_all)

        with t.subTest('a count below one is refused'):
            t.conf.view.top = '0'

            with t.assertRaises(ValueError):
                Selection.from_config(t.conf, t.now)
