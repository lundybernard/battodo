from unittest import TestCase
from unittest.mock import Mock

from ..table import Table, clip, column_widths, page_text, table_width

COLUMNS = ('NUM', 'TEXT')
ALIGN = ('>', '<')
# Two columns wide enough to lay a short row out without a cut.
WIDTHS = [4, 20]
# One short row's cells, in the order the columns run.
CELLS = ('4.2', 'A cell')


def table(heading: str, *lines: str) -> Mock:
    """A stand-in table, holding only the text a page reads off one."""
    stub = Mock(spec=['heading', 'lines'])
    stub.heading = heading
    stub.lines = list(lines)
    return stub


class PageTextTests(TestCase):
    """Unit tests for battodo.table.page_text."""

    def test_header(t) -> None:
        ret = page_text('a-header', [])
        t.assertEqual(ret, 'a-header')

    def test_tables(t) -> None:
        tables: list[Table] = [
            table('a-heading', 'a-line', 'another-line'),
            table('another-heading', 'a-last-line'),
        ]

        ret = page_text('a-header', tables)

        t.assertEqual(
            ret,
            'a-header\n'
            '\n'
            'a-heading\n'
            'a-line\n'
            'another-line\n'
            '\n'
            'another-heading\n'
            'a-last-line',
        )


class TableTests(TestCase):
    """Unit tests for battodo.table.Table."""

    def setUp(t) -> None:
        t.tb = Table(
            'another-list',
            COLUMNS,
            ALIGN,
            [CELLS],
            WIDTHS,
            # Default: hidden=0,
        )

    def test_title(t) -> None:
        with t.subTest('a plain name is capitalized'):
            t.tb.name = 'list'
            ret = t.tb.title
            t.assertEqual(ret, 'List')

        with t.subTest('a hyphen reads as the space it stands in for'):
            t.tb.name = 'another-list'
            ret = t.tb.title
            t.assertEqual(ret, 'Another list')

    def test_heading(t) -> None:
        with t.subTest('the title sits in a rule spanning the table'):
            ret = t.tb.heading
            t.assertEqual(ret, '── Another list ' + '─' * 12)

        with t.subTest('which is as wide as the table itself'):
            ret = t.tb.heading
            t.assertEqual(len(ret), 2 + 24 + 2)

        with t.subTest('a table too narrow for the title is not padded'):
            # The rule would have to run backwards to fit. A heading
            # that overruns its own narrow table beats one that wraps,
            # and a negative count must not eat the title.
            t.tb.widths = [1, 1]
            ret = t.tb.heading
            t.assertEqual(ret, '── Another list ')

    def test_lines(t) -> None:
        with t.subTest('the column names lead, then a line per row'):
            ret = t.tb.lines
            t.assertEqual(ret, ['   NUM  TEXT', '   4.2  A cell'])

        with t.subTest('an abridged table says how much it holds back'):
            t.tb.hidden = 3
            ret = t.tb.lines
            t.assertEqual(ret[-1], '  … and 3 more')

    def test_line(t) -> None:
        with t.subTest('cells are padded and aligned to the widths'):
            ret = t.tb.line(CELLS)
            t.assertEqual(ret, '   4.2  A cell')

        with t.subTest('trailing space is not left on the line'):
            ret = t.tb.line(('4.2', ''))
            t.assertEqual(ret, '   4.2')

        with t.subTest('a cell too wide for its column is clipped'):
            ret = t.tb.line(('12345', 'A' * 40))
            t.assertEqual(ret, '  123…  ' + 'A' * 19 + '…')

        with t.subTest('each column aligns the way the table says'):
            t.tb.align = ('<', '<')
            ret = t.tb.line(CELLS)
            t.assertEqual(ret, '  4.2   A cell')

    def test_name(t) -> None:
        ret = t.tb.name
        t.assertEqual(ret, 'another-list')

    def test_columns(t) -> None:
        ret = t.tb.columns
        t.assertEqual(ret, COLUMNS)

    def test_align(t) -> None:
        ret = t.tb.align
        t.assertEqual(ret, ALIGN)

    def test_rows(t) -> None:
        ret = t.tb.rows
        t.assertEqual(ret, [CELLS])

    def test_widths(t) -> None:
        ret = t.tb.widths
        t.assertEqual(ret, WIDTHS)

    def test_hidden(t) -> None:
        ret = t.tb.hidden
        t.assertEqual(ret, 0)


class TableWidthTests(TestCase):
    """Unit tests for battodo.table.table_width."""

    def test_columns(t) -> None:
        ret = table_width([1, 1, 1, 1, 1])

        # Two of indent, the cells themselves, and a gap between each
        # neighbouring pair.
        t.assertEqual(ret, 2 + 5 + 8)

    def test_gaps(t) -> None:
        ret = table_width([10, 20])

        # Two columns have one pair of neighbours between them.
        t.assertEqual(ret, 2 + 30 + 2)


class ClipTests(TestCase):
    """Unit tests for battodo.table.clip."""

    def test_fits(t) -> None:
        ret = clip('abc', 3)
        t.assertEqual(ret, 'abc')

    def test_cut(t) -> None:
        ret = clip('abcdef', 3)

        with t.subTest('text too long is cut, and says so'):
            t.assertEqual(ret, 'ab…')

        with t.subTest('the mark counts towards the width'):
            t.assertEqual(len(ret), 3)


class ColumnWidthsTests(TestCase):
    """Unit tests for battodo.table.column_widths."""

    def test_cells(t) -> None:
        ret = column_widths(COLUMNS, [('1', 'A cell'), ('12345', 'Another')])
        t.assertEqual(ret, [5, 7])

    def test_names(t) -> None:
        ret = column_widths(COLUMNS, [('1', 'A')])
        t.assertEqual(ret, [len('NUM'), len('TEXT')])

    def test_no_rows(t) -> None:
        ret = column_widths(COLUMNS, [])
        t.assertEqual(ret, [len('NUM'), len('TEXT')])
