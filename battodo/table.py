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
    out = [header]
    for table in tables:
        out.append('')
        out.append(table.heading)
        out.extend(table.lines)
    return '\n'.join(out)


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
        return self.name.replace('-', ' ').capitalize()

    @property
    def heading(self) -> str:
        """A titled rule spanning the table, e.g. `── Work ────`.

        Ruled to the table's own width, not the terminal's: a divider
        that wraps looks worse than a row that does.
        """
        prefix = f'{RULE * 2} {self.title} '
        return prefix + RULE * max(0, table_width(self.widths) - len(prefix))

    @property
    def lines(self) -> list[str]:
        """Everything under the heading: the column names, then the rows."""
        out = [self.line(self.columns)]
        out.extend(self.line(cells) for cells in self.rows)
        if self.hidden:
            out.append(f'{INDENT}{ELLIPSIS} and {self.hidden} more')
        return out

    def line(self, cells: tuple[str, ...]) -> str:
        """Clip, pad and align one row's cells. Trailing space is stripped."""
        laid = (
            f'{clip(cell, size):{align}{size}}'
            for cell, align, size in zip(cells, self.align, self.widths)
        )
        return f'{INDENT}{GAP.join(laid)}'.rstrip()


def table_width(widths: list[int]) -> int:
    """How wide a table laid out to `widths` comes out."""
    return len(INDENT) + sum(widths) + len(GAP) * (len(widths) - 1)


def clip(text: str, width: int) -> str:
    """`text` cut to `width`, the cut marked where it happened."""
    if len(text) <= width:
        return text
    return text[: width - 1] + ELLIPSIS


def column_widths(
    columns: tuple[str, ...],
    rows: list[tuple[str, ...]],
) -> list[int]:
    """Each column's width: its widest cell, the name included."""
    return [
        max(len(cell) for cell in column) for column in zip(columns, *rows)
    ]
