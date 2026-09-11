from datetime import date, datetime, timezone
from unittest import TestCase
from unittest.mock import Mock, patch, sentinel

from ..render import (
    COLUMNS,
    MIN_TASK_WIDTH,
    Row,
    Table,
    View,
    clip,
    due_label,
    table_width,
)

SRC = 'battodo.view.render'
TODAY = date(2026, 8, 5)
# Five columns wide enough to lay a short row out without clipping.
WIDTHS = [4, 3, 3, 20, 10]


def autopatch(case: TestCase, target: str) -> Mock:
    """Stand in for `target`, put back when `case` finishes."""
    patcher = patch(f'{SRC}.{target}', autospec=True)
    double = patcher.start()
    case.addCleanup(patcher.stop)
    return double


class DueLabelTests(TestCase):
    """Unit tests for battodo.view.render.due_label."""

    def test_dates(t) -> None:
        cases = {
            'no due date reads as nothing at all': (None, ''),
            'a date already past is called out': ('2026-08-04', 'OVERDUE'),
            'so is the day itself': ('2026-08-05', 'TODAY'),
            'a date still ahead shows as written': (
                '2026-08-20',
                '2026-08-20',
            ),
            'and a placeholder shows verbatim rather than raising': (
                'YYYY-MM-DD',
                'YYYY-MM-DD',
            ),
        }

        for name, (due, expected) in cases.items():
            with t.subTest(name):
                ret = due_label(due, TODAY)
                t.assertEqual(ret, expected)


class TableWidthTests(TestCase):
    """Unit tests for battodo.view.render.table_width."""

    def test_columns(t) -> None:
        ret = table_width([1, 1, 1, 1, 1])

        # Two of indent, the cells themselves, and a gap between each
        # neighbouring pair.
        t.assertEqual(ret, 2 + 5 + 8)


class ClipTests(TestCase):
    """Unit tests for battodo.view.render.clip."""

    def test_fits(t) -> None:
        ret = clip('abc', 3)
        t.assertEqual(ret, 'abc')

    def test_cut(t) -> None:
        ret = clip('abcdef', 3)

        with t.subTest('text too long is cut, and says so'):
            t.assertEqual(ret, 'ab…')

        with t.subTest('the mark counts towards the width'):
            t.assertEqual(len(ret), 3)


class RowTests(TestCase):
    """Unit tests for battodo.view.render.Row."""

    def setUp(t) -> None:
        t.rank = autopatch(t, 'rank')
        t.multiplier = autopatch(t, 'multiplier')
        t.open_children = autopatch(t, 'open_children')
        t.rank.return_value = 4.25
        t.multiplier.return_value = 3.0
        t.open_children.return_value = []

        t.task = Mock(spec=['title', 'loe', 'due'])
        t.task.title = 'A task'
        t.task.loe = 2
        t.task.due = None

        t.r = Row(t.task, TODAY)

    def test_children(t) -> None:
        ret = t.r.children
        t.assertEqual(ret, t.open_children.return_value)
        t.open_children.assert_called_once_with(t.task)

    def test_badge(t) -> None:
        with t.subTest('a task with nothing outstanding wears no badge'):
            ret = t.r.badge
            t.assertEqual(ret, '')

        with t.subTest('otherwise it carries the count'):
            t.r.children = [sentinel.child, sentinel.child]
            ret = t.r.badge
            t.assertEqual(ret, ' (+2)')

    def test_cells(t) -> None:
        with t.subTest('rank and priority are shown to one decimal'):
            ret = t.r.cells
            t.assertEqual(ret[:2], ('4.2', '3.0'))

        with t.subTest('the clock reaches the rank'):
            t.rank.assert_called_once_with(t.task, TODAY)

        with t.subTest('an unestimated task leaves its column empty'):
            t.task.loe = None
            t.r.__dict__.pop('cells')

            ret = t.r.cells

            t.assertEqual(ret[2], '')

        with t.subTest('a level of effort is shown when there is one'):
            t.task.loe = 2
            t.r.__dict__.pop('cells')

            ret = t.r.cells

            t.assertEqual(ret[2], '2')

        with t.subTest('the title carries its badge'):
            t.r.children = [sentinel.child]
            t.r.__dict__.pop('cells')

            ret = t.r.cells

            t.assertEqual(ret[3], 'A task (+1)')

        with t.subTest('and the due date its label'):
            t.task.due = '2026-08-04'
            t.r.__dict__.pop('cells')

            ret = t.r.cells

            t.assertEqual(ret[4], 'OVERDUE')

        with t.subTest('there is one cell per column'):
            ret = t.r.cells
            t.assertEqual(len(ret), len(COLUMNS))


def row(*cells: str) -> Row:
    """A stand-in row, holding only the cells a table lays out."""
    stub = Mock(spec=['cells'])
    stub.cells = cells
    return stub


class TableTests(TestCase):
    """Unit tests for battodo.view.render.Table."""

    def setUp(t) -> None:
        t.rows = [row('4.2', '3.0', '2', 'A task', 'OVERDUE')]
        t.tb = Table(
            'work',
            t.rows,
            WIDTHS,
            # Default: hidden=0,
        )

    def test_title(t) -> None:
        with t.subTest('a plain name is capitalized'):
            ret = t.tb.title
            t.assertEqual(ret, 'Work')

        with t.subTest('a hyphen reads as the space it stands in for'):
            t.tb.name = 'side-quests'
            ret = t.tb.title
            t.assertEqual(ret, 'Side quests')

    def test_heading(t) -> None:
        with t.subTest('the title sits in a rule spanning the table'):
            ret = t.tb.heading
            t.assertEqual(ret, '── Work ' + '─' * 42)

        with t.subTest('which is as wide as the table itself'):
            ret = t.tb.heading
            t.assertEqual(len(ret), table_width(WIDTHS))

        with t.subTest('a table too narrow for the title is not padded'):
            # The rule would have to run backwards to fit. A heading
            # that overruns its own narrow table beats one that wraps,
            # and a negative count must not eat the title.
            t.tb.name = 'a-very-long-category-name-indeed'
            t.tb.widths = [1, 1, 1, 1, 1]

            ret = t.tb.heading

            t.assertEqual(ret, '── A very long category name indeed ')

    def test_line(t) -> None:
        with t.subTest('cells are padded and aligned to the widths'):
            ret = t.tb.line(('4.2', '3.0', '2', 'A task', 'OVERDUE'))

            t.assertEqual(
                ret, '   4.2  3.0    2  A task                OVERDUE'
            )

        with t.subTest('trailing space is not left on the line'):
            ret = t.tb.line(('4.2', '3.0', '2', 'A task', ''))
            t.assertEqual(ret, '   4.2  3.0    2  A task')

        with t.subTest('a title too wide for its column is clipped'):
            ret = t.tb.line(('4.2', '3.0', '2', 'A' * 40, ''))
            t.assertTrue(ret.endswith('…'))

    def test_lines(t) -> None:
        with t.subTest('the column names lead, then a line per row'):
            ret = t.tb.lines

            t.assertEqual(
                ret,
                [
                    t.tb.line(COLUMNS),
                    '   4.2  3.0    2  A task                OVERDUE',
                ],
            )

        with t.subTest('a complete table says nothing about hiding'):
            ret = t.tb.lines
            t.assertNotIn('more', '\n'.join(ret))

        with t.subTest('an abridged one says how much it holds back'):
            t.tb.hidden = 3
            ret = t.tb.lines
            t.assertEqual(ret[-1], '  … and 3 more')

    def test_rows(t) -> None:
        ret = t.tb.rows
        t.assertEqual(ret, t.rows)

    def test_name(t) -> None:
        ret = t.tb.name
        t.assertEqual(ret, 'work')

    def test_widths(t) -> None:
        ret = t.tb.widths
        t.assertEqual(ret, WIDTHS)

    def test_hidden(t) -> None:
        ret = t.tb.hidden
        t.assertEqual(ret, 0)


def category(name: str, hidden: int = 0, shown=('task',)) -> Mock:
    """A stand-in category, holding what a view reads off one."""
    stub = Mock(spec=['name', 'shown', 'hidden'])
    stub.name = name
    stub.shown = list(shown)
    stub.hidden = hidden
    return stub


class ViewTests(TestCase):
    """Unit tests for battodo.view.render.View."""

    def setUp(t) -> None:
        t.Row = autopatch(t, 'Row')
        t.get_terminal_size = autopatch(t, 'get_terminal_size')
        t.get_terminal_size.return_value.columns = 80
        t.Row.side_effect = lambda task, today: row(
            '4.2',
            '3.0',
            '2',
            str(task),
            'OVERDUE',
        )

        t.selection = Mock(spec=['now', 'today', 'active', 'categories'])
        t.selection.now = datetime(2026, 8, 5, 10, 30, tzinfo=timezone.utc)
        t.selection.today = TODAY
        t.selection.active = {'work', 'study'}
        t.selection.categories = [category('work')]

        t.v = View(
            t.selection,
            # Default: width=0,
        )

    def test_today(t) -> None:
        ret = t.v.today
        t.assertEqual(ret, TODAY)

    def test_header(t) -> None:
        with t.subTest('the day, the date, the time, then what is open'):
            ret = t.v.header

            t.assertEqual(
                ret, 'Wednesday 2026-08-05 10:30 — active: study, work'
            )

        with t.subTest('the active set reads in a settled order'):
            # Given in the wrong order on purpose: a set would iterate
            # in whatever order it liked, which is no test of sorting.
            t.selection.active = ['work', 'study', 'career']
            ret = t.v.header
            t.assertTrue(ret.endswith('career, study, work'))

    def test_sections(t) -> None:
        ((found, rows),) = t.v.sections

        with t.subTest('each category is paired with a row per task shown'):
            t.assertEqual(found, t.selection.categories[0])
            t.assertEqual(len(rows), 1)

        with t.subTest('every row is built against the same day'):
            t.Row.assert_called_once_with('task', TODAY)

    def test_columns(t) -> None:
        with t.subTest('a width that was asked for is used as given'):
            t.v.width = 100
            ret = t.v.columns
            t.assertEqual(ret, 100)

        with t.subTest('otherwise the terminal is asked'):
            t.v.width = 0
            t.v.__dict__.pop('columns')

            ret = t.v.columns

            t.assertEqual(ret, 80)

        with t.subTest('and a view built without one asks by default'):
            ret = View(t.selection).columns
            t.assertEqual(ret, 80)

    def resize(t, width: int) -> list[int]:
        """The widths this view settles on at `width` columns."""
        t.v.width = width
        for cached in ('columns', 'widths'):
            t.v.__dict__.pop(cached, None)
        return t.v.widths

    def test_widths(t) -> None:
        with t.subTest('a column is as wide as its widest cell or name'):
            ret = t.v.widths
            # RANK is held open by its own name, P and LOE by theirs.
            t.assertEqual(ret[:3], [4, 3, 3])

        with t.subTest('a table claims no more of the terminal than it needs'):
            ret = t.v.widths
            t.assertLessEqual(sum(ret) + 2 + 8, 80)

        # The other columns take 27 of the line between them, so what is
        # left for titles is the terminal less that.
        long_title = 'A' * 60
        t.Row.side_effect = lambda task, today: row(
            '4.2',
            '3.0',
            '2',
            long_title,
            'OVERDUE',
        )
        t.v.__dict__.pop('sections')

        with t.subTest('titles take the room left over when they need it'):
            ret = t.resize(80)
            t.assertEqual(ret[3], 80 - 27)

        with t.subTest('and only as much as they need when there is more'):
            ret = t.resize(200)
            t.assertEqual(ret[3], len(long_title))

        with t.subTest('but the column never shrinks past readable'):
            ret = t.resize(10)
            t.assertEqual(ret[3], MIN_TASK_WIDTH)

    def test_tables(t) -> None:
        with t.subTest('one table per category, sharing the view widths'):
            (table,) = t.v.tables
            t.assertEqual(table.name, 'work')
            t.assertEqual(table.widths, t.v.widths)

        with t.subTest('each is told what its category held back'):
            t.selection.categories = [category('work', hidden=4)]
            t.v.__dict__.pop('sections')
            t.v.__dict__.pop('tables')

            ret = t.v.tables

            t.assertEqual(ret[0].hidden, 4)

    def test_text(t) -> None:
        lines = t.v.text.split('\n')

        with t.subTest('the header leads'):
            t.assertEqual(lines[0], t.v.header)

        with t.subTest('a blank line then a heading opens each table'):
            t.assertEqual(lines[1], '')
            t.assertEqual(lines[2], t.v.tables[0].heading)

        with t.subTest('and the table follows it'):
            t.assertEqual(lines[3:], t.v.tables[0].lines)

    def test___str__(t) -> None:
        ret = str(t.v)
        t.assertEqual(ret, t.v.text)
