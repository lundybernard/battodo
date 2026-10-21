"""Show the open todo items that matter right now.

`selection` decides which lists and which of their tasks a view holds,
and builds one row per task. Its `SelectionJsonView` lays a selection
out as the machine-readable record (README.md, "Machine-readable
output"). `render` lays the rows out as aligned text for a terminal,
through one `RowView` per row.

The names read outside the package are re-exported here, so
`battodo.view` stays the one import path.
"""

from .render import View
from .selection import RANK_PLACES, TOP_N, Selection, SelectionJsonView
