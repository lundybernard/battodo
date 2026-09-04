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

from battodo import TZ
from battodo.view import Selection, View

# Wednesday mid-morning: the work window is open, the chores window
# is shut.
NOW = datetime(2026, 8, 5, 10, 30, tzinfo=TZ)
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
            f'# {name}\n\n{marker}## Open\n\n{body}\n',
            encoding='utf-8',
        )
        return path

    def reset(t) -> None:
        """No lists in the source directory, for the next subtest."""
        for path in t.source.glob('*.md'):
            path.unlink()


class RenderedViewTests(SourceDirTests):
    """Contract tests for battodo.view.View.text."""

    def test_text(t) -> None:
        # The parked list sorts first. The scan must step over it,
        # not stop at it.
        t.write('study', '- [ ] A parked task [P:5]', parked=True)
        t.write('career', '- [ ] A task after the parked list [P:2]')
        t.write('home-repair', '- [ ] The last task of all [P:2]')

        out = View(Selection(t.source, NOW, show_all=False), 80).text

        with t.subTest('the parked list contributes nothing'):
            t.assertNotIn('A parked task', out)

        with t.subTest('the list after it is still rendered'):
            t.assertIn('A task after the parked list', out)

        with t.subTest('and so is the last one'):
            t.assertIn('The last task of all', out)

        # A list gets a table only when it has open items.
        t.reset()
        t.write('career')
        t.write('events', '- [x] A completed task [P:3]')
        t.write('backlog', '- [ ] A visible task [P:2]')

        out = View(Selection(t.source, NOW, show_all=False), 80).text

        with t.subTest('a list with no items has no table'):
            t.assertNotIn('Career', out)

        with t.subTest('nor has one whose every item is finished'):
            t.assertNotIn('Events', out)

        with t.subTest('a list with something to show still renders'):
            t.assertIn('Backlog', out)

        t.reset()
        t.write('career', *(f'- [ ] Item {n} [P:3]' for n in range(1, 8)))

        with t.subTest('five items, and a count of what is held back'):
            out = View(Selection(t.source, NOW, show_all=False), 80).text
            t.assertIn('Item 5', out)
            t.assertNotIn('Item 6', out)
            t.assertIn('… and 2 more', out)

        with t.subTest('an explicit top_n replaces the default'):
            selection = Selection(t.source, NOW, show_all=False, top_n=2)
            out = View(selection, 80).text
            t.assertIn('Item 2', out)
            t.assertNotIn('Item 3', out)
            t.assertIn('… and 5 more', out)

        with t.subTest('show_all keeps every item and holds back none'):
            out = View(Selection(t.source, NOW, show_all=True), 80).text
            t.assertIn('Item 7', out)
            t.assertNotIn('… and', out)

        t.reset()
        t.write('career', f'- [ ] {LONG_TITLE} [P:3]')
        narrow = View(Selection(t.source, NOW, show_all=False), 60).text
        wide = View(Selection(t.source, NOW, show_all=False), 120).text

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
                    selection = Selection(t.source, NOW, show_all=False)
                    probed = View(selection).text
                t.assertEqual(probed, expected)

        t.reset()
        t.write('chores', '- [ ] An inactive category task [P:3]')
        t.write('career', '- [ ] An active category task [P:2]')

        with t.subTest('a shut window keeps its category out of the view'):
            out = View(Selection(t.source, NOW, show_all=False), 80).text
            t.assertNotIn('An inactive category task', out)
            t.assertIn('An active category task', out)

        with t.subTest('asking for everything reaches past the windows'):
            out = View(Selection(t.source, NOW, show_all=True), 80).text
            t.assertIn('An inactive category task', out)
            t.assertIn('An active category task', out)

        with t.subTest('though a list that opted out stays out even then'):
            t.write('backlog', '- [ ] A parked task [P:4]', parked=True)
            out = View(Selection(t.source, NOW, show_all=True), 80).text
            t.assertNotIn('A parked task', out)

        with t.subTest('and the header still names only what is open now'):
            # Which categories are active is a fact about the clock.
            # Asking to see everything does not reopen their windows.
            out = View(Selection(t.source, NOW, show_all=True), 80).text
            t.assertIn('active: career, events, study, work', out)


class SelectionDocumentTests(SourceDirTests):
    """Contract tests for battodo.view.Selection.json."""

    def categories(t, **kwargs: object) -> list[dict]:
        selection = Selection(t.source, NOW, **kwargs)  # type: ignore[arg-type]
        return loads(selection.json)['categories']

    def test_json(t) -> None:
        t.write('career', *(f'- [ ] Item {n} [P:3]' for n in range(1, 8)))
        abridged = loads(Selection(t.source, NOW, show_all=False).json)

        with t.subTest('five tasks by default'):
            tasks = abridged['categories'][0]['tasks']
            t.assertEqual(tasks[-1]['title'], 'Item 5')

        with t.subTest('an explicit top_n replaces the default'):
            tasks = t.categories(show_all=False, top_n=2)[0]['tasks']
            t.assertEqual(len(tasks), 2)

        with t.subTest('show_all emits every one'):
            tasks = t.categories(show_all=True)[0]['tasks']
            t.assertEqual(len(tasks), 7)

        with t.subTest('the document says how many were held back'):
            # A reader that cannot tell an abridged document from a
            # complete one has no way of knowing to ask for the rest.
            t.assertEqual(list(abridged), ['date', 'active', 'categories'])
            t.assertEqual(
                list(abridged['categories'][0]),
                ['name', 'hidden', 'tasks'],
            )
            t.assertEqual(abridged['categories'][0]['hidden'], 2)

        with t.subTest('and says none are when it is holding nothing back'):
            t.assertEqual(t.categories(show_all=True)[0]['hidden'], 0)

        # Seven days over a 30-day scale is a repeating fraction, so
        # the raw rank has more decimals than the document publishes.
        t.reset()
        t.write('career', '- [ ] A fractional rank task [ADDED:2026-07-29]')
        task = t.categories(show_all=False)[0]['tasks'][0]

        with t.subTest('the published rank carries two decimal places'):
            t.assertEqual(task['rank'], 1.23)

        with t.subTest('which is not the raw computation'):
            t.assertNotEqual(task['rank'], 1 + 7 / 30)

        t.reset()
        t.write('career', '- [ ] A single task [P:2]')
        lines = Selection(t.source, NOW, show_all=False).json.split('\n')

        with t.subTest('the document spans more than one line'):
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
