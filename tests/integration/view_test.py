"""Contract tests for the public rendering API, against real files.

One test per public name, one subtest per code path. Inputs are real
directories that hold real todo lists. This layer asserts return
values; interaction checks stay in the isolation tests beside the
code.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from json import loads
from os import environ
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from battodo.parser import TodoDocument
from battodo.rank import DEFAULT_DUE_CURVE, parse_curve
from battodo.view import Selection, SelectionJsonView, View
from battodo.view.selection import Row
from tests.environment import TZ

# Wednesday mid-morning.
NOW = datetime(2026, 8, 5, 10, 30, tzinfo=TZ)
PARKED = '<!-- battodo:parked -->'
# The width the layout probes, through the variable the terminal size
# reads first.
WIDTH = 80
LONG_TITLE = 'A very long task title that has to be clipped to fit'


def source_dir(t: TestCase) -> Path:
    """An empty source directory, removed when the test ends."""
    tmp = TemporaryDirectory()
    t.addCleanup(tmp.cleanup)
    return Path(tmp.name)


@contextmanager
def empty_source() -> Iterator[Path]:
    """An empty source directory of its own, for one group of subtests."""
    with TemporaryDirectory() as tmp:
        yield Path(tmp)


def write(source: Path, name: str, *items: str, parked: bool = False) -> Path:
    """Write the list `name`, holding `items` in its open section."""
    marker = f'{PARKED}\n\n' if parked else ''
    path = source / f'{name}.md'
    body = '\n'.join(items)
    path.write_text(
        f'# {name}\n\n{marker}## Open\n\n{body}\n',
        encoding='utf-8',
    )
    return path


class RenderedViewTests(TestCase):
    """Contract tests for battodo.view.View.text."""

    def setUp(t) -> None:
        t.source = source_dir(t)

    @patch.dict(environ, {'COLUMNS': str(WIDTH)})
    def test_text(t) -> None:
        # The parked list sorts first. The scan must step over it,
        # not stop at it.
        write(t.source, 'study', '- [ ] A parked task [P:5]', parked=True)
        write(t.source, 'career', '- [ ] A task after the parked list [P:2]')
        write(t.source, 'home-repair', '- [ ] The last task of all [P:2]')

        out = View(Selection(t.source, NOW, show_all=False)).text

        with t.subTest('the parked list contributes nothing'):
            t.assertNotIn('A parked task', out)

        with t.subTest('the list after it is still rendered'):
            t.assertIn('A task after the parked list', out)

        with t.subTest('and so is the last one'):
            t.assertIn('The last task of all', out)

        # A list gets a table only when it has open items.
        with empty_source() as source:
            write(source, 'career')
            write(source, 'events', '- [x] A completed task [P:3]')
            write(source, 'backlog', '- [ ] A visible task [P:2]')

            out = View(Selection(source, NOW, show_all=False)).text

            with t.subTest('a list with no items has no table'):
                t.assertNotIn('Career', out)

            with t.subTest('nor has one whose every item is finished'):
                t.assertNotIn('Events', out)

            with t.subTest('a list with something to show still renders'):
                t.assertIn('Backlog', out)

        with empty_source() as source:
            write(
                source,
                'career',
                *(f'- [ ] Item {n} [P:3]' for n in range(1, 8)),
            )

            with t.subTest('five items, and a count of what is held back'):
                out = View(Selection(source, NOW, show_all=False)).text

                t.assertIn('Item 5', out)
                t.assertNotIn('Item 6', out)
                t.assertIn('… and 2 more', out)

            with t.subTest('an explicit top_n replaces the default'):
                selection = Selection(source, NOW, show_all=False, top_n=2)

                out = View(selection).text

                t.assertIn('Item 2', out)
                t.assertNotIn('Item 3', out)
                t.assertIn('… and 5 more', out)

            with t.subTest('show_all keeps every item and holds back none'):
                out = View(Selection(source, NOW, show_all=True)).text
                t.assertIn('Item 7', out)
                t.assertNotIn('… and', out)

        with empty_source() as source:
            write(source, 'career', f'- [ ] {LONG_TITLE} [P:3]')
            # The decorator restores the environment when the test ends.
            environ['COLUMNS'] = '60'
            narrow = View(Selection(source, NOW, show_all=False)).text
            environ['COLUMNS'] = '120'
            wide = View(Selection(source, NOW, show_all=False)).text
            environ['COLUMNS'] = str(WIDTH)

            with t.subTest('the probed width bounds the table'):
                # The header line is prose, not columns.
                table = narrow.split('\n')[1:]
                t.assertLessEqual(max(len(line) for line in table), 60)

            with t.subTest('a narrow table clips the title it cannot fit'):
                t.assertNotIn(LONG_TITLE, narrow)
                t.assertIn('…', narrow)

            with t.subTest('a wide one does not have to'):
                t.assertIn(LONG_TITLE, wide)

        with empty_source() as source:
            write(source, 'another-list', '- [ ] A shut category task [P:3]')
            write(source, 'a-list', '- [ ] An open category task [P:2]')

            with t.subTest('with no schedule, every list shows'):
                out = View(Selection(source, NOW, show_all=False)).text
                t.assertIn('A shut category task', out)
                t.assertIn('An open category task', out)

            with t.subTest('and the header names the day and the time alone'):
                out = View(Selection(source, NOW, show_all=False)).text
                t.assertEqual(out.split('\n')[0], 'Wednesday 2026-08-05 10:30')

            with t.subTest('a shut window keeps its category out of view'):
                out = View(scheduled(source, show_all=False)).text
                t.assertNotIn('A shut category task', out)
                t.assertIn('An open category task', out)

            with t.subTest('asking for everything reaches past the windows'):
                out = View(scheduled(source, show_all=True)).text
                t.assertIn('A shut category task', out)
                t.assertIn('An open category task', out)

            with t.subTest('though a list that opted out stays out even then'):
                write(
                    source,
                    'a-parked-list',
                    '- [ ] A parked task [P:4]',
                    parked=True,
                )

                out = View(scheduled(source, show_all=True)).text

                t.assertNotIn('A parked task', out)

            with t.subTest('and the header names only what is open now'):
                # Which categories are active is a fact about the clock.
                # Asking to see everything does not reopen their windows.
                out = View(scheduled(source, show_all=True)).text
                t.assertEqual(
                    out.split('\n')[0],
                    'Wednesday 2026-08-05 10:30 — active: a-list, a-third-list',
                )


def scheduled(source: Path, *, show_all: bool) -> Selection:
    """A selection of `source` under a schedule that is shut at NOW.

    At NOW, a Wednesday at 10:30, the window of another-list is shut
    and the window of a-list is open.
    """
    return Selection(
        source,
        NOW,
        show_all=show_all,
        windows='a-list=wed 10-11; another-list=mon-fri 17-21',
        always_active='a-third-list',
    )


class SelectionJsonViewTests(TestCase):
    """Contract tests for battodo.view.SelectionJsonView.json."""

    def setUp(t) -> None:
        t.source = source_dir(t)

    def categories(t, **kwargs: object) -> list[dict]:
        selection = Selection(t.source, NOW, **kwargs)  # type: ignore[arg-type]
        return loads(SelectionJsonView(selection).json)['categories']

    def test_json(t) -> None:
        write(
            t.source,
            'career',
            *(f'- [ ] Item {n} [P:3]' for n in range(1, 8)),
        )
        selection = Selection(t.source, NOW, show_all=False)
        abridged = loads(SelectionJsonView(selection).json)

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

        with t.subTest('each task names its list'):
            tasks = abridged['categories'][0]['tasks']
            t.assertEqual({task['list'] for task in tasks}, {'career'})

        # Seven days over a 30-day scale is a repeating fraction, so
        # the raw rank has more decimals than the document publishes.
        with empty_source() as source:
            write(
                source,
                'career',
                '- [ ] A fractional rank task [ADDED:2026-07-29]',
            )
            selection = Selection(source, NOW, show_all=False)
            document = loads(SelectionJsonView(selection).json)
            task = document['categories'][0]['tasks'][0]

            with t.subTest('the published rank carries two decimals'):
                t.assertEqual(task['rank'], 1.23)

            with t.subTest('which is not the raw computation'):
                t.assertNotEqual(task['rank'], 1 + 7 / 30)

        with empty_source() as source:
            write(source, 'career', '- [ ] A single task [P:2]')
            selection = Selection(source, NOW, show_all=False)
            lines = SelectionJsonView(selection).json.split('\n')

            with t.subTest('the document spans more than one line'):
                t.assertGreater(len(lines), 1)

            with t.subTest('and is indented two spaces to the level'):
                t.assertTrue(lines[1].startswith('  "'))
                t.assertFalse(lines[1].startswith('   '))


class SelectionTests(TestCase):
    """Contract tests for battodo.view.Selection."""

    def setUp(t) -> None:
        t.source = source_dir(t)

    def test_curve(t) -> None:
        with t.subTest('the default curve'):
            selection = Selection(t.source, NOW, show_all=False)
            ret = selection.curve
            t.assertEqual(ret, [(-30, 0.5), (-7, 1.0), (0, 2.0), (14, 4.0)])

        with t.subTest('a curve given in its place'):
            selection = Selection(
                t.source, NOW, show_all=False, rank_due_curve='0:3.0'
            )
            ret = selection.curve
            t.assertEqual(ret, [(0, 3.0)])


class RowTests(TestCase):
    """Contract tests for battodo.view.selection.Row."""

    def test_rank(t) -> None:
        default = parse_curve(DEFAULT_DUE_CURVE)
        cases = {
            # Eight weeks out, the default curve holds a task at its floor.
            'the default curve halves a far due date': (
                '- [ ] A dated task [P:2] [DUE:2026-09-30]',
                default,
                1.0,
            ),
            'a curve given in its place decides instead': (
                '- [ ] A dated task [P:2] [DUE:2026-09-30]',
                [(0, 3.0)],
                6.0,
            ),
            # Twenty days ahead, a recurrence ranks lower:
            # 5 x (0.5 + 0.5 x 10 / 23).
            'a recurrence due later is shown, ranked lower': (
                '- [ ] A refill [P:5] [DUE:2026-08-25] [REPEAT:90d]',
                default,
                5 * (0.5 + 0.5 * 10 / 23),
            ),
        }
        for name, (line, curve, expected) in cases.items():
            with t.subTest(name):
                task = TodoDocument(f'## Open\n{line}').tasks[0]
                row = Row(task, NOW.date(), curve)

                ret = row.rank

                t.assertAlmostEqual(ret, expected)
