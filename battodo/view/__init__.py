"""Show the open todo items that matter right now (R3).

`selection` decides which lists and which of their tasks a view holds,
and carries the machine-readable form of that choice (R2); `render`
lays the same choice out as aligned text for a terminal.

The public names of both are re-exported here, so `battodo.view`
stays the one import path.
"""

from .render import Row, Table, View, due_label
from .selection import (
    RANK_PLACES,
    TOP_N,
    Category,
    Selection,
    SourceError,
    TodoList,
    active_categories,
    open_children,
    parse,
    sort_key,
    task_entry,
    visible_tasks,
)
