"""Show the open todo items that matter right now (R3).

`selection` decides which lists and which of their tasks a view holds,
and carries the machine-readable form of that choice (R2); `render`
lays the same choice out as aligned text for a terminal.

The names read outside the package are re-exported here, so
`battodo.view` stays the one import path.
"""

from .render import View
from .selection import RANK_PLACES, TOP_N, Selection
