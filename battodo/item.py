"""Read one item: find it, then describe it.

The two forms mirror `view`: text for a terminal, JSON for an agent.
Both describe a *single* task, so `subtasks` here is the nested list of
children rather than the count `view` publishes.

`Item` holds the values of one item. It is built on the `Task` a
selector names, so a selector reaches the same task in every command.
Each form is a view that reads the item through its attributes:
`ItemView` lays it out as text, and `ItemJsonView` as JSON.
`lib.get_item` composes them.

Values are derived, not stored: `P` reads as the 0-5 multiplier `view`
shows.
"""

from datetime import datetime
from functools import cached_property
from json import dumps
from pathlib import Path
from typing import Any

from batconf import Configuration

from .parser import TaskNode
from .rank import DEFAULT_DUE_CURVE, Curve, multiplier, parse_curve, rank
from .task import Task
from .view import RANK_PLACES

INDENT = '  '
# What a labelled row shows in place of an absent id. Fields print no
# row at all; an id is the one value whose absence is worth reading,
# since it is what every other command takes as a selector.
NO_VALUE = '-'


class Item:
    """One open task: its list, its fields, its children.

    Built on the `Task` a selector names, and ranked on the day that
    task carries.
    """

    def __init__(
        self,
        task: Task,
        rank_due_curve: str = DEFAULT_DUE_CURVE,
    ) -> None:
        self._task = task
        self._raw_curve = rank_due_curve

    @classmethod
    def from_config(
        cls,
        conf: Configuration,
        now: datetime,
        *,
        selector: str,
    ) -> 'Item':
        """Build the item `selector` names from a resolved configuration.

        The local day of the clock decides the rank.
        """
        task = Task(
            Path(conf.view.source_dir),
            selector,
            now.date(),
        )
        return cls(task, conf.view.rank_due_curve)

    @property
    def category(self) -> str:
        """The name of the list: its file's name without the extension."""
        return self._task.path.stem

    @property
    def node(self) -> TaskNode:
        """The task as the parser reads it."""
        return self._task.node

    @property
    def rank(self) -> float:
        """The task's rank on the day the task carries."""
        return rank(self.node, self._task.today, self._curve)

    @cached_property
    def _curve(self) -> Curve:
        """The due-date curve the task is ranked on.

        Raises
        ------
        ValueError
            The configured curve does not decode.
        """
        return parse_curve(self._raw_curve)

    @property
    def priority(self) -> float:
        """The task's stored priority, as a multiplier."""
        return multiplier(self.node)

    @property
    def subtasks(self) -> list[TaskNode]:
        """The task's children, done ones included, in file order."""
        return self.node.children


class ItemView:
    """An item rendered for a terminal: a title, then labelled rows."""

    def __init__(self, item: Item) -> None:
        self._item = item

    @property
    def text(self) -> str:
        """The title, the labelled rows, then the subtasks.

        Returned without a trailing newline.
        """
        width = self._width
        lines = [self._item.node.title]
        lines.extend(
            f'{INDENT}{label:<{width}}{INDENT}{value}'
            for label, value in self._rows
        )
        if self._item.subtasks:
            lines.append(f'{INDENT}subtasks')
            lines.extend(self._outline)
        return '\n'.join(lines)

    @property
    def _rows(self) -> list[tuple[str, str]]:
        """The labelled values the text form lists, in order.

        An absent field has no row. An absent id reads as NO_VALUE. The
        rank reads as a view row shows it: rounded once, not from the
        published rank. Each description line closes them with a row,
        and only the first of those carries a label.
        """
        node = self._item.node
        rows = [
            ('list', self._item.category),
            ('id', node.task_id or NO_VALUE),
            ('rank', f'{self._item.rank:.1f}'),
            ('P', f'{self._item.priority:.1f}'),
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
            (label, str(value))
            for label, value in stored
                if value is not None
        )  # fmt: skip
        if node.description_lines:
            first, *rest = node.description_lines
            rows.append(('description', first))
            rows.extend(('', line) for line in rest)
        return rows

    @property
    def _width(self) -> int:
        """How wide the labels pad to: the longest label."""
        return max(len(label) for label, _ in self._rows)

    @property
    def _outline(self) -> list[str]:
        """The subtask lines, indented below their label."""
        return [
            f'{INDENT * 2}{line}'
            for subtask in self._subtasks
            for line in subtask.lines
        ]

    @property
    def _subtasks(self) -> list['SubtaskView']:
        """The item's children, each laid out as text."""
        return [SubtaskView(child) for child in self._item.subtasks]


class SubtaskView:
    """One child of an item in SCHEMA.md markup, its children below it."""

    def __init__(self, node: TaskNode) -> None:
        self._node = node

    @property
    def lines(self) -> list[str]:
        """The child's line, then its children's, one indent deeper."""
        return [
            self._line,
            *(
                f'{INDENT}{line}'
                for subtask in self._subtasks
                for line in subtask.lines
            ),
        ]

    @property
    def _line(self) -> str:
        """The child in SCHEMA.md markup: the checkbox, title and fields."""
        return f'[{self._mark}] {self._node.title}{self._fields}'

    @property
    def _subtasks(self) -> list['SubtaskView']:
        """The child's own children, each laid out as text."""
        return [SubtaskView(child) for child in self._node.children]

    @property
    def _mark(self) -> str:
        """The checkbox mark: `x` once done, a space while open."""
        return 'x' if self._node.done else ' '

    @property
    def _fields(self) -> str:
        """The child's fields as SCHEMA.md writes them, in its order.

        An absent field is left out.
        """
        stored = (
            ('LOE', self._node.loe),
            ('DUE', self._node.due),
            ('REPEAT', self._node.repeat),
            ('TAGS', ','.join(self._node.tags) or None),
            ('ID', self._node.task_id),
        )
        return ''.join(
            f' [{name}:{value}]'
            for name, value in stored
                if value is not None
        )  # fmt: skip


class ItemJsonView:
    """An item laid out as JSON, for an agent to read."""

    def __init__(self, item: Item) -> None:
        self._item = item

    @property
    def json(self) -> str:
        """`_data` as a JSON document, indented for a person to read too.

        The schema is a contract for agents; see `_data` for its shape.
        """
        return dumps(self._data, indent=2)

    @property
    def _data(self) -> dict[str, Any]:
        """The machine-readable form of the item.

        Shaped as::

            {"list": "work", "id": "9o71lx", "title": "...", "done": false,
             "rank": 10.0, "priority": 4.0, "loe": 8, "due": "2026-08-12",
             "added": "2026-07-06", "repeat": null, "tags": ["yard"],
             "description": "...",
             "subtasks": [{"id": null, "title": "...", "done": false,
                           "loe": 2, "due": null, "repeat": null,
                           "tags": [], "description": null,
                           "subtasks": []}]}

        Every key is always present; an absent field is null, and so is
        the description of a task with no description lines. `subtasks`
        nests to any depth, and holds completed children as well as open
        ones -- a read reports the item as it stands.
        """
        node = self._item.node
        return {
            'list': self._item.category,
            'id': node.task_id,
            'title': node.title,
            'done': node.done,
            'rank': round(self._item.rank, RANK_PLACES),
            'priority': self._item.priority,
            'loe': node.loe,
            'due': node.due,
            'added': node.added,
            'repeat': node.repeat,
            'tags': node.tags,
            'description': node.description,
            'subtasks': [subtask.data for subtask in self._subtasks],
        }

    @property
    def _subtasks(self) -> list['SubtaskJsonView']:
        """The item's children, each laid out as JSON."""
        return [SubtaskJsonView(child) for child in self._item.subtasks]


class SubtaskJsonView:
    """One child of an item laid out as JSON.

    Carries no rank: SCHEMA.md gives a child no `P` of its own, so a
    rank computed for one would report the neutral multiplier as if the
    child had been prioritised.
    """

    def __init__(self, node: TaskNode) -> None:
        self._node = node

    @property
    def data(self) -> dict[str, Any]:
        """The child as `ItemJsonView._data` records it, with its children."""
        return {
            'id': self._node.task_id,
            'title': self._node.title,
            'done': self._node.done,
            'loe': self._node.loe,
            'due': self._node.due,
            'repeat': self._node.repeat,
            'tags': self._node.tags,
            'description': self._node.description,
            'subtasks': [subtask.data for subtask in self._subtasks],
        }

    @property
    def _subtasks(self) -> list['SubtaskJsonView']:
        """The child's own children, each laid out as JSON."""
        return [SubtaskJsonView(child) for child in self._node.children]
