"""Read one item: find it, then describe it (R3).

The two forms mirror `view`: text for a terminal, JSON for an agent.
Both describe a *single* task, so `subtasks` here is the nested list of
children rather than the count `view` publishes -- the shape is the
item, not a row in a table.

Values are derived, not stored: `P` reads as the 0-5 multiplier
`view` shows, so the same task reads the same way in either command.
`selector` supplies the lookup, so the reach of a selector is one
rule, not two.
"""

from datetime import date, datetime
from json import dumps
from pathlib import Path
from typing import Any

from .parser import TaskNode
from .rank import multiplier, rank
from .selector import TaskSelection
from .view import RANK_PLACES

INDENT = '  '
# What a labelled row shows in place of an absent id. Fields print no
# row at all; an id is the one value whose absence is worth reading,
# since it is what every other command takes as a selector.
NO_VALUE = '-'
# The rows a stored field fills, by the data key that carries it, in
# SCHEMA.md's order. `TAGS` is a list and `ADDED` a btodo extension, so
# both are laid out separately.
FIELD_ROWS = (('LOE', 'loe'), ('DUE', 'due'), ('REPEAT', 'repeat'))


def subtask_entry(task: TaskNode) -> dict[str, Any]:
    """One child as `item_data` records it, with its own children.

    Carries no rank: SCHEMA.md gives a child no `P` of its own, so a
    rank computed for one would report the neutral multiplier as if the
    child had been prioritised.
    """
    return {
        'id': task.task_id,
        'title': task.title,
        'done': task.done,
        'loe': task.loe,
        'due': task.due,
        'tags': task.tags,
        'subtasks': [subtask_entry(child) for child in task.children],
    }


def item_data(path: Path, task: TaskNode, today: date) -> dict[str, Any]:
    """The machine-readable form of one item.

    Shaped as::

        {"list": "work", "id": "9o71lx", "title": "...", "done": false,
         "rank": 10.0, "priority": 4.0, "loe": 8, "due": "2026-08-12",
         "added": "2026-07-06", "repeat": null, "tags": ["yard"],
         "subtasks": [{"id": null, "title": "...", "done": false,
                       "loe": 2, "due": null, "tags": [],
                       "subtasks": []}]}

    Every key is always present; an absent field is null. `subtasks`
    nests to any depth, and holds completed children as well as open
    ones -- a read reports the item as it stands.

    Parameters
    ----------
    path : Path
        The list the task lives in; its stem names the list.
    task : TaskNode
        The task itself.
    today : date
        The day the rank is computed for.
    """
    return {
        'list': path.stem,
        'id': task.task_id,
        'title': task.title,
        'done': task.done,
        'rank': round(rank(task, today), RANK_PLACES),
        'priority': multiplier(task),
        'loe': task.loe,
        'due': task.due,
        'added': task.added,
        'repeat': task.repeat,
        'tags': task.tags,
        'subtasks': [subtask_entry(child) for child in task.children],
    }


def _rows(data: dict[str, Any]) -> list[tuple[str, str]]:
    """The labelled values the text form lists, in order."""
    rows = [
        ('list', data['list']),
        ('id', data['id'] or NO_VALUE),
        ('rank', f'{data["rank"]:.1f}'),
        ('P', f'{data["priority"]:.1f}'),
    ]
    rows.extend(
        (label, str(data[key]))
        for label, key in FIELD_ROWS
        if data[key] is not None
    )
    if data['tags']:
        rows.append(('TAGS', ', '.join(data['tags'])))
    if data['added'] is not None:
        rows.append(('ADDED', data['added']))
    return rows


def _child_lines(entries: list[dict[str, Any]], depth: int) -> list[str]:
    """The children, one line each, indented by depth.

    Fields print in SCHEMA.md's own markup: what the user typed, and
    what an edit has to put back.
    """
    lines = []
    for entry in entries:
        fields = ''.join(
            f' [{name}:{value}]'
            for name, value in (
                ('LOE', entry['loe']),
                ('DUE', entry['due']),
                ('TAGS', ','.join(entry['tags']) or None),
                ('ID', entry['id']),
            )
            if value is not None
        )
        mark = 'x' if entry['done'] else ' '
        lines.append(f'{INDENT * depth}[{mark}] {entry["title"]}{fields}')
        lines.extend(_child_lines(entry['subtasks'], depth + 1))
    return lines


def render_item(data: dict[str, Any]) -> str:
    """Lay `item_data` out for a terminal: a title, then labelled rows.

    Returns
    -------
    str
        The rendered item, without a trailing newline.
    """
    rows = _rows(data)
    width = max(len(label) for label, _ in rows)
    lines = [data['title']]
    lines.extend(
        f'{INDENT}{label:<{width}}{INDENT}{value}' for label, value in rows
    )
    if data['subtasks']:
        lines.append(f'{INDENT}subtasks')
        lines.extend(_child_lines(data['subtasks'], 2))
    return '\n'.join(lines)


def build_item(directory: Path, selector: str, now: datetime) -> str:
    """Render the one open task `selector` names.

    Parameters
    ----------
    directory : Path
        The source directory, `~` unexpanded.
    selector : str
        A task `[ID:]` or part of a title.
    now : datetime
        The clock, whose local day decides the rank.

    Returns
    -------
    str
        The rendered item, without a trailing newline.

    Raises
    ------
    SelectionError
        If `selector` does not name exactly one open task.
    """
    record = TaskSelection(directory, selector).record
    return render_item(item_data(record.path, record.task, now.date()))


def build_item_json(directory: Path, selector: str, now: datetime) -> str:
    """Serialize the same item `build_item` renders.

    Parameters
    ----------
    directory : Path
        The source directory, `~` unexpanded.
    selector : str
        A task `[ID:]` or part of a title.
    now : datetime
        The clock, whose local day decides the rank.

    Returns
    -------
    str
        A JSON document; see `item_data` for its shape.

    Raises
    ------
    SelectionError
        If `selector` does not name exactly one open task.
    """
    record = TaskSelection(directory, selector).record
    return dumps(item_data(record.path, record.task, now.date()), indent=2)
