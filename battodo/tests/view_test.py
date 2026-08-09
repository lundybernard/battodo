import re
from datetime import date, datetime
from json import loads
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from zoneinfo import ZoneInfo

from ..parser import parse
from ..view import (
    TZ,
    SourceError,
    active_categories,
    build_json,
    build_view,
    discover_lists,
    due_label,
    sort_key,
    visible_tasks,
)

LIST = """# Work

## Open

- [ ] High [P:9]
- [ ] Dated [P:9] [DUE:2026-01-02]
- [ ] Earlier [P:9] [DUE:2026-01-01]
- [ ] Low [P:1]
- [x] Done [P:99]
- [ ] Future repeat [P:99] [DUE:2999-01-01] [REPEAT:14d]
- [ ] Future plain [P:50] [DUE:2999-01-01]
- [ ] Waiting [P:2] [ADDED:2026-05-10]
"""

# Shapes taken from the live lists: a legacy inflated P, an item with no
# LOE and no DUE, a parent with an open child, and a template's literal
# YYYY-MM-DD placeholder -- each one sizes a column differently.
CHORES = """# Chores

## Open

- [ ] Pay credit cards [P:95] [LOE:1] [DUE:2026-08-01]
- [ ] Put together a repair plan for the back porch deck [P:70] [LOE:3]
  - [ ] Measure the joists [LOE:1]
  - [x] Price the lumber [LOE:1]
- [ ] Chip the brush pile [P:89]
- [ ] Cat Care [P:7] [LOE:6] [DUE:YYYY-MM-DD]
"""


def at(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=TZ)


class ActiveCategoriesTests(TestCase):
    def test_active_categories(t) -> None:
        always = {'study', 'career', 'events'}
        cases = {
            # Wed 2026-08-05
            'weekday work hours': ('2026-08-05T10:00', always | {'work'}),
            'weekday evening': ('2026-08-05T18:00', always | {'chores'}),
            'weekday early': ('2026-08-05T07:00', always),
            'weekday late': ('2026-08-05T22:00', always),
            # Sat 2026-08-08
            'weekend midday': ('2026-08-08T12:00', always | {'chores'}),
            'weekend early': ('2026-08-08T08:00', always),
        }
        for name, (stamp, expected) in cases.items():
            with t.subTest(name):
                t.assertEqual(active_categories(at(stamp)), expected)


class DiscoverListsTests(TestCase):
    def setUp(t) -> None:
        t.tmp = TemporaryDirectory()
        t.addCleanup(t.tmp.cleanup)
        t.dir = Path(t.tmp.name)

    def test_discover_lists(t) -> None:
        (t.dir / 'work.md').write_text('# W\n\n## Open\n\n- [ ] A\n')
        (t.dir / 'backlog.md').write_text('## Open\n\n- [ ] B\n')
        (t.dir / 'SCHEMA.md').write_text('# Schema\n\nprose\n')
        (t.dir / 'completed.md').write_text('2026-01-01 | work | DONE | X\n')
        (t.dir / 'notes.txt').write_text('## Open\n')

        with t.subTest('only markdown with an Open section'):
            found = [p.name for p in discover_lists(t.dir)]
            t.assertEqual(found, ['backlog.md', 'work.md'])

        with t.subTest('ad-hoc lists are included'):
            t.assertIn('backlog.md', found)

        with t.subTest('missing directory yields nothing'):
            t.assertEqual(discover_lists(t.dir / 'nope'), [])


class VisibleTasksTests(TestCase):
    def setUp(t) -> None:
        t.doc = parse(LIST)
        t.today = date(2026, 8, 8)

    def test_visible_tasks(t) -> None:
        titles = [task.title for task in visible_tasks(t.doc, t.today)]

        with t.subTest('completed hidden'):
            t.assertNotIn('Done', titles)

        with t.subTest('future recurring hidden'):
            t.assertNotIn('Future repeat', titles)

        with t.subTest('future non-recurring shown, per R3 and the script'):
            t.assertIn('Future plain', titles)


class SortKeyTests(TestCase):
    def setUp(t) -> None:
        t.today = date(2026, 8, 8)
        t.order = [
            task.title
            for task in sorted(
                visible_tasks(parse(LIST), t.today),
                key=lambda task: sort_key(task, t.today),
            )
        ]

    def test_sort_key(t) -> None:
        with t.subTest('rank descending, then due ascending'):
            t.assertEqual(
                t.order,
                [
                    # 2 x (1 + two months waiting) = 6.0
                    'Waiting',
                    # 1.36 x (1 + capped lateness) = 5.44, earlier first
                    'Earlier',
                    'Dated',
                    # 3.0 x 1: a high legacy P, but nothing pressing
                    'Future plain',
                    'High',
                    'Low',
                ],
            )

        with t.subTest('undated sorts after dated at equal rank'):
            t.assertLess(t.order.index('Earlier'), t.order.index('High'))

        with t.subTest('lateness outranks a much larger stored priority'):
            t.assertLess(
                t.order.index('Earlier'), t.order.index('Future plain')
            )


class PlaceholderDatesTests(TestCase):
    """Template files carry literal YYYY-MM-DD; nothing may crash."""

    def setUp(t) -> None:
        t.doc = parse(
            '## Open\n\n- [ ] Tmpl [P:6] [DUE:YYYY-MM-DD] [ADDED:YYYY-MM-DD]\n'
        )

    def test_visible_tasks(t) -> None:
        tasks = visible_tasks(t.doc, date(2026, 8, 8))
        t.assertEqual([task.title for task in tasks], ['Tmpl'])

    def test_sort_key(t) -> None:
        today = date(2026, 8, 8)
        task = t.doc.tasks[0]
        t.assertEqual(sort_key(task, today), (-1.24, 'YYYY-MM-DD', 'Tmpl'))

    def test_due_label(t) -> None:
        t.assertEqual(due_label('YYYY-MM-DD', date(2026, 8, 8)), 'YYYY-MM-DD')


class DueLabelTests(TestCase):
    def test_due_label(t) -> None:
        today = date(2026, 8, 8)
        cases = {
            None: '',
            '2026-08-07': 'OVERDUE',
            '2026-08-08': 'TODAY',
            '2026-09-01': '2026-09-01',
        }
        for due, expected in cases.items():
            with t.subTest(str(due)):
                t.assertEqual(due_label(due, today), expected)


class ListsFixture(TestCase):
    """A work and a study list, read at a weekday mid-morning."""

    def setUp(t) -> None:
        t.tmp = TemporaryDirectory()
        t.addCleanup(t.tmp.cleanup)
        t.dir = Path(t.tmp.name)
        (t.dir / 'work.md').write_text(LIST)
        (t.dir / 'study.md').write_text('## Open\n\n- [ ] Read [P:2]\n')
        t.now = at('2026-08-05T10:00')


class BuildViewTests(ListsFixture):
    def test_build_view(t) -> None:
        with t.subTest('active categories only'):
            out = build_view(t.dir, t.now, show_all=True)
            t.assertIn('Work', out)
            t.assertIn('Study', out)

        with t.subTest('inactive category omitted'):
            out = build_view(t.dir, at('2026-08-05T22:00'), show_all=True)
            t.assertNotIn('Earlier', out)
            t.assertIn('Read', out)

        with t.subTest('rows carry the computed rank and the multiplier'):
            out = build_view(t.dir, t.now, show_all=True)
            t.assertIn('RANK', out)
            t.assertRegex(
                out, re.compile(r'^\s+6\.0\s+2\.0\s+Waiting$', re.MULTILINE)
            )

        with t.subTest('top-N limits rows'):
            limited = build_view(t.dir, t.now, show_all=False, top_n=1)
            t.assertIn('Waiting', limited)
            t.assertNotIn('Earlier', limited)

        with t.subTest('header names the day and active set'):
            t.assertIn('active:', build_view(t.dir, t.now, show_all=True))

        with t.subTest('list with nothing visible is skipped'):
            (t.dir / 'career.md').write_text('## Open\n\n- [x] Nope [P:5]\n')
            t.assertNotIn('Career', build_view(t.dir, t.now, show_all=True))

        with t.subTest('ad-hoc list outside the categories is shown'):
            (t.dir / 'backlog.md').write_text(
                '## Open\n\n- [ ] Someday [P:4]\n'
            )
            out = build_view(t.dir, t.now, show_all=True)
            t.assertIn('Backlog', out)
            t.assertIn('Someday', out)

        with t.subTest('a parked list opts out of the view'):
            (t.dir / 'backlog.md').write_text(
                '# Backlog\n\n<!-- battodo:parked -->\n\n'
                '## Open\n\n- [ ] Someday [P:4]\n'
            )
            out = build_view(t.dir, t.now, show_all=True)
            t.assertNotIn('Someday', out)

        with t.subTest('but stays discoverable, so mutations reach it'):
            found = [p.name for p in discover_lists(t.dir)]
            t.assertIn('backlog.md', found)


class BuildJsonTests(ListsFixture):
    """The agent-facing view (R2): same selection, no presentation."""

    def render(t, **kwargs) -> dict:
        # Default: show_all=True,
        kwargs.setdefault('show_all', True)
        return loads(build_json(t.dir, t.now, **kwargs))

    def test_build_json(t) -> None:
        doc = t.render()

        with t.subTest('the header fields the human view prints'):
            t.assertEqual(doc['date'], '2026-08-05')
            t.assertEqual(doc['active'], ['career', 'events', 'study', 'work'])

        with t.subTest('active categories only, in view order'):
            names = [category['name'] for category in doc['categories']]
            t.assertEqual(names, ['work', 'study'])

        with t.subTest('tasks carry the rank order, not a rank label'):
            titles = [task['title'] for task in doc['categories'][0]['tasks']]
            t.assertEqual(
                titles,
                ['Waiting', 'Earlier', 'Dated', 'Future plain', 'High', 'Low'],
            )

        with t.subTest('every field of a task is serialized'):
            t.assertEqual(
                doc['categories'][0]['tasks'][0],
                {
                    'id': None,
                    'title': 'Waiting',
                    'rank': 6.0,
                    'priority': 2.0,
                    'loe': None,
                    'due': None,
                    'added': '2026-05-10',
                    'repeat': None,
                    'tags': [],
                    'subtasks': 0,
                },
            )

        with t.subTest('due dates stay verbatim, unlabelled'):
            dated = doc['categories'][0]['tasks'][1]
            t.assertEqual(dated['due'], '2026-01-01')

        with t.subTest('top-N limits tasks'):
            work = t.render(show_all=False, top_n=1)['categories'][0]
            t.assertEqual(
                [task['title'] for task in work['tasks']], ['Waiting']
            )

        with t.subTest('open subtasks are counted, not nested'):
            (t.dir / 'career.md').write_text(
                '## Open\n\n- [ ] Parent [P:3]\n'
                '  - [ ] Child [P:1]\n'
                '  - [x] Finished [P:1]\n'
            )
            career = next(
                category
                for category in t.render()['categories']
                if category['name'] == 'career'
            )
            t.assertEqual(career['tasks'][0]['subtasks'], 1)


class TableLayoutTests(TestCase):
    """Column widths come from the content, for the whole view at once.

    The markdown pipe tables this replaced computed no widths at all, so
    every table printed ragged in a terminal.
    """

    def setUp(t) -> None:
        t.tmp = TemporaryDirectory()
        t.addCleanup(t.tmp.cleanup)
        t.dir = Path(t.tmp.name)
        (t.dir / 'chores.md').write_text(CHORES)
        # Sat midday: chores are active, and nothing else has a list.
        t.now = at('2026-08-08T12:00')

    def test_build_view(t) -> None:
        lines = build_view(t.dir, t.now, show_all=True, width=100).split('\n')

        with t.subTest('columns are padded to their widest cell'):
            t.assertEqual(
                lines[3:8],
                [
                    '  RANK    P  LOE  TASK' + ' ' * 53 + 'DUE',
                    '  14.4  4.8    1  Pay credit cards'
                    + ' ' * 41
                    + 'OVERDUE',
                    '   4.6  4.6       Chip the brush pile',
                    (
                        '   3.8  3.8    3  Put together a repair plan '
                        'for the back porch deck (+1)'
                    ),
                    '   1.3  1.3    6  Cat Care' + ' ' * 49 + 'YYYY-MM-DD',
                ],
            )

        with t.subTest('the rule spans the table, under a titled heading'):
            heading = lines[2]
            t.assertTrue(heading.startswith('── Chores ─'))
            t.assertEqual(len(heading), 85)

        with t.subTest('a narrow terminal clips titles, nothing else'):
            rendered = build_view(t.dir, t.now, show_all=True, width=50)
            narrow = rendered.split('\n')
            t.assertEqual(
                narrow[4],
                '  14.4  4.8    1  Pay credit cards      OVERDUE',
            )
            t.assertIn('   3.8  3.8    3  Put together a repa…', narrow)
            t.assertEqual(len(narrow[2]), 50)

        with t.subTest('below the floor, titles keep a readable width'):
            rendered = build_view(t.dir, t.now, show_all=True, width=10)
            cramped = rendered.split('\n')
            t.assertIn('   3.8  3.8    3  Put together a repa…', cramped)

        with t.subTest('and the rule still spans its overrunning table'):
            t.assertEqual(len(cramped[2]), 50)

        with t.subTest('the terminal is probed when no width is given'):
            t.assertIn('Chores', build_view(t.dir, t.now, show_all=True))

        with t.subTest('a truncated table says how much it is hiding'):
            top = build_view(t.dir, t.now, show_all=False, top_n=2, width=100)
            t.assertIn('Pay credit cards', top)
            t.assertNotIn('Cat Care', top)
            t.assertIn('… and 2 more', top)

        with t.subTest('a complete table says nothing about hiding'):
            t.assertNotIn('… and', '\n'.join(lines))


class MissingSourceTests(TestCase):
    """A source that yields no lists is an error, not a bare header.

    Pointed at a home directory with no `todo/` in it, `btodo view`
    printed only its header and exited 0 -- the resolved path it had
    looked in was never shown.
    """

    def setUp(t) -> None:
        t.tmp = TemporaryDirectory()
        t.addCleanup(t.tmp.cleanup)
        t.dir = Path(t.tmp.name)
        t.now = at('2026-08-05T10:00')

    def test_build_view(t) -> None:
        with t.subTest('missing directory names the resolved path'):
            missing = t.dir / 'nope'
            with t.assertRaises(SourceError) as caught:
                build_view(missing, t.now, show_all=True)
            t.assertIn(str(missing), str(caught.exception))

        with t.subTest('a directory holding no lists is an error too'):
            (t.dir / 'SCHEMA.md').write_text('# Schema\n\nprose\n')
            with t.assertRaises(SourceError) as caught:
                build_view(t.dir, t.now, show_all=True)
            t.assertIn(str(t.dir), str(caught.exception))

        with t.subTest('a tilde in the path is expanded before reporting'):
            with t.assertRaises(SourceError) as caught:
                build_view(Path('~/nope-todo'), t.now, show_all=True)
            t.assertNotIn('~', str(caught.exception))

        with t.subTest('lists that are merely all-filtered still render'):
            (t.dir / 'work.md').write_text('## Open\n\n- [x] Done [P:1]\n')
            t.assertIn('active:', build_view(t.dir, t.now, show_all=True))


class TimezoneTests(TestCase):
    def test_tz(t) -> None:
        t.assertEqual(TZ, ZoneInfo('America/Los_Angeles'))
