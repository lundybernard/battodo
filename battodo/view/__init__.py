"""Show the open todo items that matter right now (R3).

`selection` decides which lists and which of their tasks a view holds,
and carries the machine-readable form of that choice (R2); `render`
lays the same choice out as aligned text for a terminal.

The public names of both are re-exported here, so `battodo.view`
stays the one import path.
"""

from dataclasses import dataclass
from zoneinfo import ZoneInfo

from .render import Row, Table, View, due_label
from .selection import (
    COUNT_ERROR,
    RANK_PLACES,
    TOP_N,
    Category,
    Selection,
    SourceError,
    TodoList,
    active_categories,
    discover_lists,
    item_count,
    open_children,
    parse,
    sort_key,
    task_entry,
    visible_tasks,
)

# The host clock runs UTC while todos are anchored to the user's local
# day, so the zone is named rather than a fixed offset.
TZ = ZoneInfo('America/Los_Angeles')


@dataclass
class Config:
    """What a view reads, and how much of it a view shows.

    One source for now; R6 turns `source_dir` into a list of sources
    once the discovery/merge semantics in ADR 0004 are settled.

    Every value is a string: the environment source carries nothing
    else, so a consumer decodes what it needs. `top` is read as an
    integer by the view command.
    """

    source_dir: str = '~/todo'
    top: str = str(TOP_N)
