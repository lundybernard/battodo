"""Lay a selection out as aligned text tables.

Output is plain aligned text, not markdown. The pipe tables this started
as were written for a chat client to re-render; read in a terminal --
which is where `btodo view` actually lands -- they printed ragged,
because a markdown table needs no column widths and so nothing computed
any. Widths here come from the content, once for the whole view, so the
columns line up down the page and not merely within one category.

Terminal width is read here rather than at the CLI boundary: the width
is an input to the layout, and the view is the only thing that knows
whether one was supplied. Passing `width` explicitly overrides the
probe, which is what keeps the layout tests independent of `$COLUMNS`.
"""

from datetime import date
from functools import cached_property
from shutil import get_terminal_size

from ..parser import Task, parse_date
from ..rank import multiplier, rank
from .selection import Category, Selection, open_children

# Layout. TASK is the elastic column: every other one is as wide as its
# widest value, and the titles absorb whatever room is left over.
COLUMNS = ('RANK', 'P', 'LOE', 'TASK', 'DUE')
ALIGN = ('>', '>', '>', '<', '<')
TASK_COLUMN = COLUMNS.index('TASK')
INDENT = '  '
GAP = '  '
RULE = '─'
ELLIPSIS = '…'
# Below this, titles are too clipped to identify; a line that overruns a
# very narrow terminal and wraps beats one that says nothing.
MIN_TASK_WIDTH = 20


def due_label(due: str | None, today: date) -> str:
    """How a due date reads in the table: a label, or the date itself."""
    if due is None:
        return ''
    parsed = parse_date(due)
    if parsed is None:
        # a placeholder such as YYYY-MM-DD: show it verbatim
        return due
    if parsed < today:
        return 'OVERDUE'
    if parsed == today:
        return 'TODAY'
    return due


def table_width(widths: list[int]) -> int:
    """How wide a table laid out to `widths` comes out."""
    return len(INDENT) + sum(widths) + len(GAP) * (len(COLUMNS) - 1)


def clip(text: str, width: int) -> str:
    """`text` cut to `width`, the cut marked where it happened."""
    if len(text) <= width:
        return text
    return text[: width - 1] + ELLIPSIS


class Row:
    """One task as the five cells a table shows it in."""

    def __init__(self, task: Task, today: date) -> None:
        self.task = task
        self.today = today

    @cached_property
    def children(self) -> list[Task]:
        return open_children(self.task)

    @property
    def badge(self) -> str:
        """The outstanding-children mark, if the task has any.

        `(+2)`, not `(2 subtasks)`: it stays out of the title's way, and
        the count needs no plural.
        """
        return f' (+{len(self.children)})' if self.children else ''

    @cached_property
    def cells(self) -> tuple[str, ...]:
        """The row's five values, in COLUMNS order."""
        return (
            f'{rank(self.task, self.today):.1f}',
            f'{multiplier(self.task):.1f}',
            '' if self.task.loe is None else str(self.task.loe),
            f'{self.task.title}{self.badge}',
            due_label(self.task.due, self.today),
        )


class Table:
    """One category's rows, at a width the whole view shares."""

    def __init__(
        self,
        name: str,
        rows: list[Row],
        widths: list[int],
        hidden: int = 0,
    ) -> None:
        self.name = name
        self.rows = rows
        self.widths = widths
        self.hidden = hidden

    @property
    def title(self) -> str:
        return self.name.replace('-', ' ').capitalize()

    @property
    def heading(self) -> str:
        """A titled rule spanning the table, e.g. `-- Work ------`.

        Ruled to the table's own width rather than the terminal's: the
        two differ only where the MIN_TASK_WIDTH floor has already
        overrun a very narrow terminal, and a divider that wraps looks
        worse than a row that does.
        """
        prefix = f'{RULE * 2} {self.title} '
        return prefix + RULE * max(0, table_width(self.widths) - len(prefix))

    def line(self, cells: tuple[str, ...]) -> str:
        """Pad and align one row's cells. Trailing space is stripped."""
        padded = list(cells)
        padded[TASK_COLUMN] = clip(
            padded[TASK_COLUMN], self.widths[TASK_COLUMN]
        )
        laid = (
            f'{cell:{align}{size}}'
            for cell, align, size in zip(padded, ALIGN, self.widths)
        )
        return f'{INDENT}{GAP.join(laid)}'.rstrip()

    @property
    def lines(self) -> list[str]:
        """Everything under the heading: the column names, then the rows."""
        out = [self.line(COLUMNS)]
        out.extend(self.line(row.cells) for row in self.rows)
        if self.hidden:
            out.append(f'{INDENT}{ELLIPSIS} and {self.hidden} more')
        return out


class View:
    """A selection rendered for a terminal: a header, then a table each."""

    def __init__(self, selection: Selection, width: int = 0) -> None:
        self.selection = selection
        self.width = width

    @property
    def today(self) -> date:
        return self.selection.today

    @property
    def header(self) -> str:
        now = self.selection.now
        return (
            f'{now.strftime("%A")} {self.today} {now.strftime("%H:%M")} '
            f'— active: {", ".join(sorted(self.selection.active))}'
        )

    @cached_property
    def sections(self) -> list[tuple[Category, list[Row]]]:
        """Each category with its rows, before any width is known."""
        return [
            (category, [Row(task, self.today) for task in category.shown])
            for category in self.selection.categories
        ]

    @cached_property
    def columns(self) -> int:
        """The width to lay out in; 0 asks the terminal, 80 if there is none."""
        return self.width or get_terminal_size().columns

    @cached_property
    def widths(self) -> list[int]:
        """Each column's width: its widest cell, TASK fitted to the rest.

        Sized against every row in the view at once, so one set of
        widths serves all of its tables and the columns line up down the
        whole page.
        """
        rows = [row for _, rows in self.sections for row in rows]
        widths = [
            max([len(name), *(len(row.cells[index]) for row in rows)])
            for index, name in enumerate(COLUMNS)
        ]
        room = self.columns - (table_width(widths) - widths[TASK_COLUMN])
        widths[TASK_COLUMN] = max(
            MIN_TASK_WIDTH, min(widths[TASK_COLUMN], room)
        )
        return widths

    @cached_property
    def tables(self) -> list[Table]:
        return [
            Table(category.name, rows, self.widths, category.hidden)
            for category, rows in self.sections
        ]

    @cached_property
    def text(self) -> str:
        out = [self.header]
        for table in self.tables:
            out.append('')
            out.append(table.heading)
            out.extend(table.lines)
        return '\n'.join(out)

    def __str__(self) -> str:
        return self.text
