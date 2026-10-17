"""Lay rows of cells out as aligned text tables.

The view and the completed digest lay their tables out here. Each one
sizes one set of widths for all of its tables, so the columns line up
down the whole page, and joins the tables under its header with
`page_text`.
"""

INDENT = '  '
GAP = '  '
RULE = '─'
ELLIPSIS = '…'


def page_text(header: str, tables: list['Table']) -> str:
    """The header, then each table under a blank line and its heading."""
    raise NotImplementedError


class Table:
    """One titled table of rows, at widths a whole page shares.

    Every cell is cut to the width of its column. A column as wide as
    its widest cell cuts nothing.
    """

    def __init__(
        self,
        name: str,
        columns: tuple[str, ...],
        align: tuple[str, ...],
        rows: list[tuple[str, ...]],
        widths: list[int],
        hidden: int = 0,
    ) -> None:
        self.name = name
        self.columns = columns
        self.align = align
        self.rows = rows
        self.widths = widths
        self.hidden = hidden

    @property
    def title(self) -> str:
        raise NotImplementedError

    @property
    def heading(self) -> str:
        """A titled rule spanning the table, e.g. `── Work ────`.

        Ruled to the table's own width, not the terminal's: a divider
        that wraps looks worse than a row that does.
        """
        raise NotImplementedError

    @property
    def lines(self) -> list[str]:
        """Everything under the heading: the column names, then the rows."""
        raise NotImplementedError

    def line(self, cells: tuple[str, ...]) -> str:
        """Clip, pad and align one row's cells. Trailing space is stripped."""
        raise NotImplementedError


def table_width(widths: list[int]) -> int:
    """How wide a table laid out to `widths` comes out."""
    raise NotImplementedError


def clip(text: str, width: int) -> str:
    """`text` cut to `width`, the cut marked where it happened."""
    raise NotImplementedError


def column_widths(
    columns: tuple[str, ...],
    rows: list[tuple[str, ...]],
) -> list[int]:
    """Each column's width: its widest cell, the name included."""
    raise NotImplementedError
