"""Contract tests for the public rendering API, against real files.

One test per public name, one subtest per code path. Inputs are real
directories that hold real todo lists. This layer asserts return
values; interaction checks stay in the isolation tests beside the
code.
"""

from datetime import date, datetime
from json import loads
from os import environ
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from battodo.view import (
    TZ,
    build_json,
    build_view,
    discover_lists,
    due_label,
    open_children,
    parse,
    sort_key,
    visible_tasks,
)

# Wednesday mid-morning: the work window is open, the chores window
# is shut.
NOW = datetime(2026, 8, 5, 10, 30, tzinfo=TZ)
TODAY = NOW.date()
PARKED = '<!-- battodo:parked -->'
LONG_TITLE = 'A very long task title that has to be clipped to fit'


class SourceDirTests(TestCase):
    """Base: an empty source directory, removed when the test ends."""

    def setUp(t) -> None:
        tmp = TemporaryDirectory()
        t.addCleanup(tmp.cleanup)
        t.source = Path(tmp.name)

    def write(t, name: str, *items: str, parked: bool = False) -> Path:
        """Write the list `name`, holding `items` in its open section."""
        marker = f'{PARKED}\n\n' if parked else ''
        path = t.source / f'{name}.md'
        body = '\n'.join(items)
        path.write_text(
            f'# {name}\n\n{marker}## Open\n\n{body}\n', encoding='utf-8'
        )
        return path


class DiscoverListsTests(SourceDirTests):
    def test_discover_lists(t) -> None:
        career = t.write('career', '- [ ] A visible task [P:2]')
        study = t.write('study', '- [ ] A parked task [P:2]', parked=True)
        loose = t.source / 'notes.md'
        loose.write_text('# Notes\n\nNothing open here.\n', encoding='utf-8')

        found = discover_lists(t.source)

        with t.subTest('every list is found, in name order'):
            t.assertEqual(found, [career, study])

        with t.subTest('a file with no open section is not a list'):
            t.assertNotIn(loose, found)

        with t.subTest('a directory that is not there yields nothing'):
            t.assertEqual(discover_lists(t.source / 'absent'), [])


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
        )

        titles = [task.title for task in visible_tasks(doc, TODAY)]

        # Only a recurrence with a future due date is suppressed. A
        # one-off always stays, and a recurrence due today is shown.
        t.assertEqual(
            titles,
            [
                'Open item',
                'Later one-off',
                'Late recurrence',
                'Recurrence due today',
            ],
        )


class DueLabelTests(TestCase):
    def test_due_label(t) -> None:
        cases = {
            'no due date reads as nothing at all': (None, ''),
            'a date already past is called out': ('2026-08-04', 'OVERDUE'),
            'so is the day itself': ('2026-08-05', 'TODAY'),
            'a date still ahead shows as written': (
                '2026-08-20',
                '2026-08-20',
            ),
            'and so does a placeholder': ('YYYY-MM-DD', 'YYYY-MM-DD'),
        }
        for name, (due, expected) in cases.items():
            with t.subTest(name):
                t.assertEqual(due_label(due, TODAY), expected)


class SortKeyTests(TestCase):
    def test_sort_key(t) -> None:
        # `Dated` is too far out for its date to add rank, so all
        # items except `Higher` rank the same and the tie-breaks
        # order them.
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


class BuildViewTests(SourceDirTests):
    def test_a_parked_list_does_not_end_the_scan(t) -> None:
        # The parked list sorts first. The scan must step over it,
        # not stop at it.
        t.write('study', '- [ ] A parked task [P:5]', parked=True)
        t.write('career', '- [ ] A task after the parked list [P:2]')
        t.write('home-repair', '- [ ] The last task of all [P:2]')

        out = build_view(t.source, NOW, show_all=False, width=80)

        with t.subTest('the parked list contributes nothing'):
            t.assertNotIn('A parked task', out)

        with t.subTest('the list after it is still rendered'):
            t.assertIn('A task after the parked list', out)

        with t.subTest('and so is the last one'):
            t.assertIn('The last task of all', out)

    def test_a_list_with_nothing_to_show_is_skipped(t) -> None:
        # A list gets a table only when it has open items.
        t.write('career')
        t.write('events', '- [x] A completed task [P:3]')
        t.write('backlog', '- [ ] A visible task [P:2]')

        out = build_view(t.source, NOW, show_all=False, width=80)

        with t.subTest('a list with no items has no table'):
            t.assertNotIn('Career', out)

        with t.subTest('nor has one whose every item is finished'):
            t.assertNotIn('Events', out)

        with t.subTest('a list with something to show still renders'):
            t.assertIn('Backlog', out)

    def test_top_n(t) -> None:
        t.write('career', *(f'- [ ] Item {n} [P:3]' for n in range(1, 8)))

        with t.subTest('five items, and a count of what is held back'):
            out = build_view(t.source, NOW, show_all=False, width=80)
            t.assertIn('Item 5', out)
            t.assertNotIn('Item 6', out)
            t.assertIn('… and 2 more', out)

        with t.subTest('an explicit top_n replaces the default'):
            out = build_view(t.source, NOW, show_all=False, top_n=2, width=80)
            t.assertIn('Item 2', out)
            t.assertNotIn('Item 3', out)
            t.assertIn('… and 5 more', out)

        with t.subTest('show_all keeps every item and holds back none'):
            out = build_view(t.source, NOW, show_all=True, width=80)
            t.assertIn('Item 7', out)
            t.assertNotIn('… and', out)

    def test_width(t) -> None:
        t.write('career', f'- [ ] {LONG_TITLE} [P:3]')
        narrow = build_view(t.source, NOW, show_all=False, width=60)
        wide = build_view(t.source, NOW, show_all=False, width=120)

        with t.subTest('an explicit width bounds the table'):
            # The header line is prose, not columns.
            table = narrow.split('\n')[1:]
            t.assertLessEqual(max(len(line) for line in table), 60)

        with t.subTest('a narrow table clips the title it cannot fit'):
            t.assertNotIn(LONG_TITLE, narrow)
            t.assertIn('…', narrow)

        with t.subTest('a wide one does not have to'):
            t.assertIn(LONG_TITLE, wide)

        # With no explicit width, the layout reads COLUMNS from the
        # environment.
        for columns, expected in (('60', narrow), ('120', wide)):
            with t.subTest(f'no width given probes {columns} columns'):
                with patch.dict(environ, {'COLUMNS': columns}):
                    probed = build_view(t.source, NOW, show_all=False)
                t.assertEqual(probed, expected)

    def test_an_inactive_category(t) -> None:
        t.write('chores', '- [ ] An inactive category task [P:3]')
        t.write('career', '- [ ] An active category task [P:2]')

        with t.subTest('a shut window keeps its category out of the view'):
            out = build_view(t.source, NOW, show_all=False, width=80)
            t.assertNotIn('An inactive category task', out)
            t.assertIn('An active category task', out)

        with t.subTest('asking for everything reaches past the windows'):
            out = build_view(t.source, NOW, show_all=True, width=80)
            t.assertIn('An inactive category task', out)
            t.assertIn('An active category task', out)

        with t.subTest('though a list that opted out stays out even then'):
            t.write('backlog', '- [ ] A parked task [P:4]', parked=True)
            out = build_view(t.source, NOW, show_all=True, width=80)
            t.assertNotIn('A parked task', out)

        with t.subTest('and the header still names only what is open now'):
            # Which categories are active is a fact about the clock.
            # Asking to see everything does not reopen their windows.
            out = build_view(t.source, NOW, show_all=True, width=80)
            t.assertIn('active: career, events, study, work', out)


class BuildJsonTests(SourceDirTests):
    def categories(t, **kwargs: object) -> list[dict]:
        document = loads(build_json(t.source, NOW, **kwargs))  # type: ignore[arg-type]
        return document['categories']

    def test_top_n(t) -> None:
        t.write('career', *(f'- [ ] Item {n} [P:3]' for n in range(1, 8)))
        abridged = loads(build_json(t.source, NOW, show_all=False))

        with t.subTest('five tasks by default'):
            tasks = abridged['categories'][0]['tasks']
            t.assertEqual(tasks[-1]['title'], 'Item 5')

        with t.subTest('an explicit top_n replaces the default'):
            tasks = t.categories(show_all=False, top_n=2)[0]['tasks']
            t.assertEqual(len(tasks), 2)

        with t.subTest('show_all emits every one'):
            tasks = t.categories(show_all=True)[0]['tasks']
            t.assertEqual(len(tasks), 7)

        with t.subTest('nothing in the document says any were held back'):
            # The document does not say when it is abridged.
            t.assertEqual(list(abridged), ['date', 'active', 'categories'])
            t.assertEqual(list(abridged['categories'][0]), ['name', 'tasks'])

    def test_rank_is_rounded(t) -> None:
        # Seven days over a 30-day scale is a repeating fraction, so
        # the raw rank has more decimals than the document publishes.
        t.write('career', '- [ ] A fractional rank task [ADDED:2026-07-29]')

        task = t.categories(show_all=False)[0]['tasks'][0]

        with t.subTest('the published rank carries two decimal places'):
            t.assertEqual(task['rank'], 1.23)

        with t.subTest('which is not the raw computation'):
            t.assertNotEqual(task['rank'], 1 + 7 / 30)

    def test_the_document_is_pretty_printed(t) -> None:
        t.write('career', '- [ ] A single task [P:2]')

        lines = build_json(t.source, NOW, show_all=False).split('\n')

        with t.subTest('it spans more than one line'):
            t.assertGreater(len(lines), 1)

        with t.subTest('and is indented two spaces to the level'):
            t.assertTrue(lines[1].startswith('  "'))
            t.assertFalse(lines[1].startswith('   '))


class TimezoneTests(TestCase):
    def test_tz(t) -> None:
        # A named zone, not a fixed offset: the local day stays
        # stable across daylight-saving changes.
        summer = datetime(2026, 8, 5, 0, 30, tzinfo=TZ)
        winter = datetime(2026, 12, 5, 0, 30, tzinfo=TZ)

        with t.subTest('the offset follows the season'):
            t.assertNotEqual(summer.utcoffset(), winter.utcoffset())

        with t.subTest('but the local day does not shift'):
            t.assertEqual(summer.date(), date(2026, 8, 5))
            t.assertEqual(winter.date(), date(2026, 12, 5))
