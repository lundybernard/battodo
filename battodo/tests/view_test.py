from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from zoneinfo import ZoneInfo

from ..parser import parse
from ..view import (
    TZ,
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
"""


def at(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=TZ)


class TestActiveCategories(TestCase):
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


class TestDiscoverLists(TestCase):
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


class TestVisibleTasks(TestCase):
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


class TestSortKey(TestCase):
    def test_sort_key(t) -> None:
        doc = parse(LIST)
        tasks = sorted(visible_tasks(doc, date(2026, 8, 8)), key=sort_key)

        with t.subTest('priority descending, then due ascending'):
            t.assertEqual(
                [task.title for task in tasks],
                [
                    'Future plain',
                    'Earlier',
                    'Dated',
                    'High',
                    'Low',
                ],
            )

        with t.subTest('undated sorts after dated at equal priority'):
            order = [task.title for task in tasks]
            t.assertLess(order.index('Earlier'), order.index('High'))


class TestPlaceholderDates(TestCase):
    """Template files carry literal [DUE:YYYY-MM-DD]; nothing may crash."""

    def setUp(t) -> None:
        t.doc = parse('## Open\n\n- [ ] Tmpl [P:6] [DUE:YYYY-MM-DD]\n')

    def test_visible_tasks(t) -> None:
        tasks = visible_tasks(t.doc, date(2026, 8, 8))
        t.assertEqual([task.title for task in tasks], ['Tmpl'])

    def test_due_label(t) -> None:
        t.assertEqual(due_label('YYYY-MM-DD', date(2026, 8, 8)), 'YYYY-MM-DD')


class TestDueLabel(TestCase):
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


class TestBuildView(TestCase):
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
            t.assertNotIn('| 9 |', out)
            t.assertIn('Read', out)

        with t.subTest('top-N limits rows'):
            limited = build_view(t.dir, t.now, show_all=False, top_n=1)
            t.assertIn('Future plain', limited)
            t.assertNotIn('Earlier', limited)

        with t.subTest('header names the day and active set'):
            t.assertIn('active:', build_view(t.dir, t.now, show_all=True))

        with t.subTest('empty directory still renders a header'):
            empty = build_view(t.dir / 'nope', t.now, show_all=True)
            t.assertIn('active:', empty)

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


class TestTimezone(TestCase):
    def test_tz(t) -> None:
        t.assertEqual(TZ, ZoneInfo('America/Los_Angeles'))
