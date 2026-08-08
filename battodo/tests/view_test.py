from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from zoneinfo import ZoneInfo

from ..parser import parse
from ..view import (
    TZ,
    SourceError,
    active_categories,
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


class BuildViewTests(TestCase):
    def setUp(t) -> None:
        t.tmp = TemporaryDirectory()
        t.addCleanup(t.tmp.cleanup)
        t.dir = Path(t.tmp.name)
        (t.dir / 'work.md').write_text(LIST)
        (t.dir / 'study.md').write_text('## Open\n\n- [ ] Read [P:2]\n')
        t.now = at('2026-08-05T10:00')

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
            t.assertIn('| Rank | P | LOE | Task | Due |', out)
            t.assertIn('| 6.0 | 2 |  | Waiting |  |', out)

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
