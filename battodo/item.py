"""Read one item: find it, then describe it (R3).

The two forms mirror `view`: text for a terminal, JSON for an agent.
Both describe a *single* task, so `subtasks` here is the nested list of
children rather than the count `view` publishes.

Values are derived, not stored: `P` reads as the 0-5 multiplier `view`
shows. `selector` supplies the lookup, so a selector reaches the same
task in every command.
"""

from datetime import datetime
from json import dumps
from pathlib import Path
from typing import Any

from batconf import Configuration

from .parser import TaskNode
from .rank import multiplier, rank
from .task import Task
from .view import RANK_PLACES

INDENT = '  '
# What a labelled row shows in place of an absent id. Fields print no
# row at all; an id is the one value whose absence is worth reading,
# since it is what every other command takes as a selector.
NO_VALUE = '-'


class Item:
    """One open task shown in full: its list, its fields, its children.

    Built on the `Task` a selector names, and ranked on the day that
    task carries.
    """

    def __init__(self, task: Task) -> None:
        self.task = task

    @classmethod
    def from_config(cls, conf: Configuration, now: datetime) -> 'Item':
        """Build an item from a resolved configuration.

        The local day of the clock decides the rank.
        """
        return cls(Task(Path(conf.view.source_dir), conf.selector, now.date()))

    @property
    def json(self) -> str:
        """`data` as a JSON document, indented for a person to read too.

        The schema is a contract for agents; see `data` for its shape.
        """
        return dumps(self.data, indent=2)

    @property
    def data(self) -> dict[str, Any]:
        """The machine-readable form of the item.

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
        """
        return {
            'list': self.category,
            'id': self.node.task_id,
            'title': self.node.title,
            'done': self.node.done,
            'rank': round(self.rank, RANK_PLACES),
            'priority': self.priority,
            'loe': self.node.loe,
            'due': self.node.due,
            'added': self.node.added,
            'repeat': self.node.repeat,
            'tags': self.node.tags,
            'subtasks': [subtask.data for subtask in self.subtasks],
        }

    @property
    def category(self) -> str:
        """The name of the list: its file's name without the extension."""
        return self.task.path.stem

    @property
    def node(self) -> TaskNode:
        """The task as the parser reads it."""
        return self.task.node

    @property
    def rank(self) -> float:
        """The task's rank on the day the task carries."""
        return rank(self.node, self.task.today)

    @property
    def priority(self) -> float:
        """The task's stored priority, as a multiplier."""
        return multiplier(self.node)

    @property
    def subtasks(self) -> list['Subtask']:
        """The task's children, done ones included, in file order."""
        return [Subtask(child) for child in self.node.children]


class Subtask:
    """One child of an item, with its own children.

    Carries no rank: SCHEMA.md gives a child no `P` of its own, so a
    rank computed for one would report the neutral multiplier as if the
    child had been prioritised.
    """

    def __init__(self, node: TaskNode) -> None:
        self.node = node

    @property
    def data(self) -> dict[str, Any]:
        """The child as `Item.data` records it, with its own children."""
        return {
            'id': self.node.task_id,
            'title': self.node.title,
            'done': self.node.done,
            'loe': self.node.loe,
            'due': self.node.due,
            'tags': self.node.tags,
            'subtasks': [subtask.data for subtask in self.subtasks],
        }

    @property
    def subtasks(self) -> list['Subtask']:
        """The child's own children, in file order."""
        return [Subtask(child) for child in self.node.children]

    @property
    def lines(self) -> list[str]:
        """The child's line, then its children's, one indent deeper."""
        return [
            self.line,
            *(
                f'{INDENT}{line}'
                for subtask in self.subtasks
                for line in subtask.lines
            ),
        ]

    @property
    def line(self) -> str:
        """The child in SCHEMA.md markup: the checkbox, title and fields."""
        return f'[{self.mark}] {self.node.title}{self.fields}'

    @property
    def mark(self) -> str:
        """The checkbox mark: `x` once done, a space while open."""
        return 'x' if self.node.done else ' '

    @property
    def fields(self) -> str:
        """The child's fields as SCHEMA.md writes them, in its order.

        An absent field is left out.
        """
        return ''.join(
            f' [{name}:{value}]'
            for name, value in (
                ('LOE', self.node.loe),
                ('DUE', self.node.due),
                ('TAGS', ','.join(self.node.tags) or None),
                ('ID', self.node.task_id),
            )
            if value is not None
        )


class ItemView:
    """An item rendered for a terminal: a title, then labelled rows."""

    def __init__(self, item: Item) -> None:
        self.item = item

    @property
    def text(self) -> str:
        """The title, the labelled rows, then the subtasks.

        Returned without a trailing newline.
        """
        width = self.width
        lines = [self.item.node.title]
        lines.extend(
            f'{INDENT}{label:<{width}}{INDENT}{value}'
            for label, value in self.rows
        )
        if self.item.subtasks:
            lines.append(f'{INDENT}subtasks')
            lines.extend(self.outline)
        return '\n'.join(lines)

    @property
    def rows(self) -> list[tuple[str, str]]:
        """The labelled values the text form lists, in order.

        An absent field has no row. An absent id reads as NO_VALUE.
        """
        node = self.item.node
        rows = [
            ('list', self.item.category),
            ('id', node.task_id or NO_VALUE),
            ('rank', f'{round(self.item.rank, RANK_PLACES):.1f}'),
            ('P', f'{self.item.priority:.1f}'),
        ]
        # SCHEMA.md's order, then ADDED, a btodo extension.
        stored = (
            ('LOE', node.loe),
            ('DUE', node.due),
            ('REPEAT', node.repeat),
            ('TAGS', ', '.join(node.tags) or None),
            ('ADDED', node.added),
        )
        rows.extend(
            (label, str(value)) for label, value in stored if value is not None
        )
        return rows

    @property
    def width(self) -> int:
        """How wide the labels pad to: the longest label."""
        return max(len(label) for label, _ in self.rows)

    @property
    def outline(self) -> list[str]:
        """The subtask lines, indented below their label."""
        return [
            f'{INDENT * 2}{line}'
            for subtask in self.item.subtasks
            for line in subtask.lines
        ]
