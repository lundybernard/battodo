"""Lay a selection out as aligned text tables.

Output is plain aligned text, not markdown: a markdown table states no
column widths, so it prints ragged in a terminal. Widths come from the
content, once for the whole view, so the columns line up down the page
and not merely within one category.

Terminal width is read here rather than at the CLI boundary, because
the width is an input to the layout. The probe reads COLUMNS first, so
a caller that needs a fixed width pins it in the environment.

A row is built by the selection, and the published form reads the
same row, so the two never derive a task apart.
"""

from datetime import date
from functools import cached_property
from shutil import get_terminal_size

from ..table import Table, column_widths, page_text, table_width
from .selection import Category, Row, Selection

# Layout. TASK is the elastic column: every other one is as wide as its
# widest value, and the titles absorb whatever room is left over.
COLUMNS = ('RANK', 'P', 'LOE', 'TASK', 'DUE')
ALIGN = ('>', '>', '>', '<', '<')
TASK_COLUMN = COLUMNS.index('TASK')
# Below this, titles are too clipped to identify; a line that overruns a
# very narrow terminal and wraps beats one that says nothing.
MIN_TASK_WIDTH = 20


class View:
    """A selection rendered for a terminal: a header, then a table each."""

    def __init__(self, selection: Selection) -> None:
        self.selection = selection

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
    def categories(self) -> list[Category]:
        """The categories this view lays out, in display order."""
        return self.selection.categories

    @cached_property
    def rows(self) -> list[Row]:
        """Every row the view shows, across all of its categories."""
        return [
            row
            for category in self.categories
            for row in category.shown
        ]  # fmt: skip

    @cached_property
    def columns(self) -> int:
        """The width to lay out in: the terminal's, or 80 if it has none."""
        return get_terminal_size().columns

    @cached_property
    def widths(self) -> list[int]:
        """Each column's width: its widest cell, TASK fitted to the rest.

        Sized against every row in the view at once, so one set of
        widths serves all of its tables and the columns line up down the
        whole page.
        """
        cells = [row.cells for row in self.rows]
        widths = column_widths(COLUMNS, cells)
        room = self.columns - (table_width(widths) - widths[TASK_COLUMN])
        widths[TASK_COLUMN] = max(
            MIN_TASK_WIDTH,
            min(widths[TASK_COLUMN], room),
        )
        return widths

    @cached_property
    def tables(self) -> list[Table]:
        return [
            Table(
                category.name,
                COLUMNS,
                ALIGN,
                [row.cells for row in category.shown],
                self.widths,
                category.hidden,
            )
            for category in self.categories
        ]

    @cached_property
    def text(self) -> str:
        return page_text(self.header, self.tables)

    def __str__(self) -> str:
        return self.text


class RowView:
    """One row of a selection laid out as the cells of a table line.

    `RowJsonView` publishes the same row's stored fields verbatim. This
    view labels the due date and marks the open children.
    """

    def __init__(self, row: Row) -> None:
        self.row = row

    @property
    def cells(self) -> tuple[str, ...]:
        """The five values a table shows, in the order its columns run."""
        task = self.row.task
        return (
            f'{self.row.rank:.1f}',
            f'{self.row.priority:.1f}',
            '' if task.loe is None else str(task.loe),
            f'{task.title}{self.badge}',
            self.due_label,
        )

    @property
    def badge(self) -> str:
        """The outstanding-children mark, if the task has any.

        `(+2)`, not `(2 subtasks)`: it stays out of the title's way, and
        the count needs no plural.
        """
        subtasks = self.row.subtasks
        return f' (+{subtasks})' if subtasks else ''

    @property
    def due_label(self) -> str:
        """How the due date reads in a table: a label, or the date.

        Named apart from the stored `due` field, which `RowJsonView`
        publishes verbatim.
        """
        due = self.row.task.due
        if due is None:
            return ''
        parsed = self.row.parsed_due
        if parsed is None:
            # a placeholder such as YYYY-MM-DD: show it verbatim
            return due
        if parsed < self.row.today:
            return 'OVERDUE'
        if parsed == self.row.today:
            return 'TODAY'
        return due
