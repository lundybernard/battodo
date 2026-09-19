from datetime import date, datetime, timezone
from unittest import TestCase
from unittest.mock import Mock, patch

from ..render import (
    COLUMNS,
    MIN_TASK_WIDTH,
    Row,
    Table,
    View,
    clip,
    table_width,
)

SRC = 'battodo.view.render'
TODAY = date(2026, 8, 5)
# Five columns wide enough to lay a short row out without clipping.
WIDTHS = [4, 3, 3, 20, 10]
# One short row's cells, in the order the columns run.
CELLS = ('4.2', '3.0', '2', 'A task', 'OVERDUE')


def autopatch(case: TestCase, target: str) -> Mock:
    """Stand in for `target`, put back when `case` finishes."""
    patcher = patch(f'{SRC}.{target}', autospec=True)
    double = patcher.start()
    case.addCleanup(patcher.stop)
    return double


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


def category(name: str, hidden: int = 0, rows: int = 1) -> Mock:
    """A stand-in category, holding what a view reads off one."""
    stub = Mock(spec=['name', 'shown', 'hidden'])
    stub.name = name
    stub.shown = [row(*CELLS)] * rows
    stub.hidden = hidden
    return stub


class ViewTests(TestCase):
    """Unit tests for battodo.view.render.View."""

    def setUp(t) -> None:
        t.get_terminal_size = autopatch(t, 'get_terminal_size')
        t.get_terminal_size.return_value.columns = 80

        t.selection = Mock(spec=['now', 'today', 'active', 'categories'])
        t.selection.now = datetime(2026, 8, 5, 10, 30, tzinfo=timezone.utc)
        t.selection.today = TODAY
        t.selection.active = {'work', 'study'}
        t.selection.categories = [category('work')]

        t.v = View(t.selection)

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

    def test_categories(t) -> None:
        ret = t.v.categories
        t.assertEqual(ret, t.selection.categories)

    def test_rows(t) -> None:
        with t.subTest('a category contributes the rows it shows'):
            ret = t.v.rows
            t.assertEqual(ret, t.selection.categories[0].shown)

        with t.subTest('and the categories run together in display order'):
            t.v.__dict__.pop('rows')
            first, second = category('work'), category('study', rows=2)
            t.v.categories = [first, second]

            ret = t.v.rows

            t.assertEqual(ret, first.shown + second.shown)

    def test_columns(t) -> None:
        ret = t.v.columns

        t.assertEqual(ret, 80)
        t.get_terminal_size.assert_called_once_with()

    def resize(t, width: int) -> list[int]:
        """The widths this view settles on at `width` columns."""
        t.get_terminal_size.return_value.columns = width
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
        t.v.rows = [row('4.2', '3.0', '2', long_title, 'OVERDUE')]

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

        with t.subTest('each carries the rows its category shows'):
            t.assertEqual(table.rows, t.selection.categories[0].shown)

        with t.subTest('and is told what that category held back'):
            t.v.categories = [category('work', hidden=4)]
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
