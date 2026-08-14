"""Show the open todo items that matter right now (R3).

`selection` decides which lists and which of their tasks a view holds,
and carries the machine-readable form of that choice (R2); `render`
lays the same choice out as aligned text for a terminal. `lib`
composes them into the two functions callers actually use.

The public names of all three are re-exported here, so `battodo.view`
stays the one import path -- and so the configuration dataclass below
keeps the dotted path its settings are looked up under.
"""

from dataclasses import dataclass
from zoneinfo import ZoneInfo

from .lib import build_json, build_view
from .render import Row, Table, View, due_label
from .selection import (
    Category,
    Selection,
    SourceError,
    TodoList,
    active_categories,
    discover_lists,
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
    """Where btodo looks for lists.

    One source for now; R6 turns this into a list of sources once the
    discovery/merge semantics in ADR 0004 are settled.

    Defined here rather than beside the selection code that uses the
    directory: the lookup namespace is left at its default, which
    derives from the module the class lives in, so this placement
    keeps every configuration key and environment name stable without
    naming the namespace explicitly.
    """

    source_dir: str = '~/todo'
