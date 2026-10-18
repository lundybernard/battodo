from datetime import UTC, date, datetime
from unittest import TestCase
from unittest.mock import MagicMock, Mock, PropertyMock, call, patch

from ..render import MIN_TASK_WIDTH, Row, RowView, Table, View

SRC = 'battodo.view.render'
TODAY = date(2026, 8, 5)
COLUMNS = ('RANK', 'P', 'LOE', 'TASK', 'DUE')
ALIGN = ('>', '>', '>', '<', '<')
# One short row's cells, in the order the columns run.
CELLS = ('4.2', '3.0', '2', 'A task', 'OVERDUE')


def row(*cells: str) -> Row:
    """A stand-in row, holding only the cells a table lays out."""
    stub = Mock(spec=['cells'])
    stub.cells = cells
    return stub


def category(name: str, hidden: int = 0, rows: int = 1) -> Mock:
    """A stand-in category, holding what a view reads off one."""
    stub = Mock(spec=['name', 'shown', 'hidden'])
    stub.name = name
    stub.shown = [row(*CELLS)] * rows
    stub.hidden = hidden
    return stub


class ViewTests(TestCase):
    """Unit tests for battodo.view.render.View."""

    get_terminal_size: MagicMock

    def setUp(t) -> None:
        patches = ['get_terminal_size']
        for target in patches:
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)

        t.get_terminal_size.return_value.columns = 80

        t.selection = Mock(spec=['now', 'today', 'active', 'categories'])
        t.selection.now = datetime(2026, 8, 5, 10, 30, tzinfo=UTC)
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

    @patch(f'{SRC}.Table', autospec=True)
    def test_tables(t, table: MagicMock) -> None:
        t.v.categories = [
            category('work'),
            category('another-list', hidden=4, rows=2),
        ]
        t.v.widths = [4, 3, 3, 20, 7]

        ret = t.v.tables

        # A table per category, at the widths of the view, with the
        # cells of each row it shows and the count it holds back.
        t.assertEqual(ret, [table.return_value] * 2)
        t.assertEqual(
            table.call_args_list,
            [
                call('work', COLUMNS, ALIGN, [CELLS], [4, 3, 3, 20, 7], 0),
                call(
                    'another-list',
                    COLUMNS,
                    ALIGN,
                    [CELLS, CELLS],
                    [4, 3, 3, 20, 7],
                    4,
                ),
            ],
        )

    @patch(f'{SRC}.page_text', autospec=True)
    def test_text(t, page_text: MagicMock) -> None:
        t.v.tables = [Mock(spec=Table)]

        ret = t.v.text

        # The header, then the tables, laid out as one page.
        page_text.assert_called_once_with(t.v.header, t.v.tables)
        t.assertIs(ret, page_text.return_value)

    def test___str__(t) -> None:
        ret = str(t.v)
        t.assertEqual(ret, t.v.text)


class RowViewTests(TestCase):
    """Unit tests for battodo.view.render.RowView."""

    def setUp(t) -> None:
        t.task = Mock(spec=['title', 'loe', 'due'])
        t.task.title = 'A task'
        t.task.loe = 2
        t.task.due = None

        t.row = Mock(spec=Row)
        t.row.task = t.task
        t.row.today = TODAY
        t.row.rank = 4.25
        t.row.priority = 3.0
        t.row.subtasks = 0
        t.row.parsed_due = None

        t.rv = RowView(t.row)

    @patch.object(RowView, 'due_label', new_callable=PropertyMock)
    @patch.object(RowView, 'badge', new_callable=PropertyMock)
    def test_cells(t, badge: PropertyMock, due_label: PropertyMock) -> None:
        badge.return_value = ''
        due_label.return_value = ''

        with t.subTest('rank and priority are shown to one decimal'):
            ret = t.rv.cells
            t.assertEqual(ret[:2], ('4.2', '3.0'))

        with t.subTest('a level of effort is shown when there is one'):
            ret = t.rv.cells
            t.assertEqual(ret[2], '2')

        with t.subTest('an unestimated task leaves its column empty'):
            t.task.loe = None
            ret = t.rv.cells
            t.assertEqual(ret[2], '')

        with t.subTest('the title carries its badge'):
            badge.return_value = ' (+1)'
            ret = t.rv.cells
            t.assertEqual(ret[3], 'A task (+1)')

        with t.subTest('and the due column carries its label'):
            due_label.return_value = 'OVERDUE'
            ret = t.rv.cells
            t.assertEqual(ret[4], 'OVERDUE')

        with t.subTest('there is one cell for each of the five columns'):
            ret = t.rv.cells
            t.assertEqual(len(ret), 5)

    def test_badge(t) -> None:
        with t.subTest('a task with nothing outstanding wears no badge'):
            ret = t.rv.badge
            t.assertEqual(ret, '')

        with t.subTest('otherwise the badge carries the count'):
            t.row.subtasks = 2
            ret = t.rv.badge
            t.assertEqual(ret, ' (+2)')

    def test_due_label(t) -> None:
        cases = {
            'no due date reads as nothing at all': (None, None, ''),
            'a date already past is called out': (
                '2026-08-04',
                date(2026, 8, 4),
                'OVERDUE',
            ),
            'so is the day itself': ('2026-08-05', TODAY, 'TODAY'),
            'a date still ahead shows as written': (
                '2026-08-20',
                date(2026, 8, 20),
                '2026-08-20',
            ),
            'and a date the parser cannot read shows verbatim': (
                'YYYY-MM-DD',
                None,
                'YYYY-MM-DD',
            ),
        }

        for name, (due, parsed, expected) in cases.items():
            with t.subTest(name):
                t.task.due = due
                t.row.parsed_due = parsed
                ret = t.rv.due_label
                t.assertEqual(ret, expected)

    def test_row(t) -> None:
        ret = t.rv.row
        t.assertIs(ret, t.row)
