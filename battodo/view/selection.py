"""Decide what a view shows: which lists, which tasks, in what order.

Kept apart from the table rendering so that layout has no say in what
is chosen. The machine-readable form (R2) lives here as
`Selection.json`: it is the selection serialized, not a rendering of it.

A view holds open items only, and suppresses future-dated *recurring*
items. SCHEMA.md's prose is stricter -- it would also hide future-dated
non-recurring items -- and R3 governs here.

Items sort by the rank computed in `rank.py` (ADR 0005) rather than by
stored priority, which is what lets the table show a rank at all: the
file states no order of its own.
"""

from datetime import date, datetime
from functools import cached_property
from json import dumps
from pathlib import Path

from batconf import Configuration

from ..lists import CATEGORY_ORDER, category_order, discover_lists, item_count
from ..parser import OPEN_HEADING, TaskNode, TodoDocument, parse_date
from ..rank import multiplier, rank


class SourceError(Exception):
    """The configured source directory yields no todo lists.

    Raised rather than rendering an empty view, which reads as
    "nothing to do" instead of "I looked in the wrong place". The
    message always carries the resolved path.
    """


ALWAYS_ACTIVE = frozenset({'study', 'career', 'events'})
NO_DUE_SORTS_LAST = 'zzzz'
# A list carrying this marker anywhere is parked: still discovered, so
# mutations reach it, but never surfaced in a view (ADR 0005).
PARKED_MARKER = 'battodo:parked'
# How many items of a category a view shows before it starts abridging.
TOP_N = 5
# How many decimal places a published rank carries.
RANK_PLACES = 2


def active_categories(now: datetime) -> set[str]:
    """Categories whose time window is open at `now`."""
    active = set(ALWAYS_ACTIVE)
    is_weekday = now.weekday() < 5
    hour = now.hour
    if is_weekday and 9 <= hour < 17:
        active.add('work')
    if is_weekday and 17 <= hour < 21:
        active.add('chores')
    if not is_weekday and 10 <= hour < 20:
        active.add('chores')
    return active


def visible_tasks(doc: TodoDocument, today: date) -> list[TaskNode]:
    """Open top-level tasks, minus suppressed future recurrences."""
    visible = []
    for task in doc.tasks:
        if task.done:
            continue
        due = parse_date(task.due)
        if due and task.repeat and due > today:
            continue
        visible.append(task)
    return visible


def sort_key(task: TaskNode, today: date) -> tuple[float, str, str]:
    """Rank descending, then nearest due, undated last, then title."""
    return (
        -rank(task, today),
        task.due or NO_DUE_SORTS_LAST,
        task.title,
    )


def open_children(task: TaskNode) -> list[TaskNode]:
    """The task's incomplete children: subtasks and checklist items."""
    return [child for child in task.children if not child.done]


def task_entry(task: TaskNode, today: date) -> dict[str, object]:
    """One task as `Selection.json` records it.

    Stored fields are carried verbatim -- no OVERDUE/TODAY labels.
    `rank` is rounded for display and must not be used to re-sort; the
    array order is the rank order.
    """
    return {
        'id': task.task_id,
        'title': task.title,
        'rank': round(rank(task, today), RANK_PLACES),
        'priority': multiplier(task),
        'loe': task.loe,
        'due': task.due,
        'added': task.added,
        'repeat': task.repeat,
        'tags': task.tags,
        'subtasks': len(open_children(task)),
    }


class TodoList:
    """One discovered list file: where it sorts, and what is open in it."""

    def __init__(self, path: Path, today: date) -> None:
        self.path = path
        self.today = today
        self.category = path.stem

    @cached_property
    def text(self) -> str:
        return self.path.read_text()

    @cached_property
    def parked(self) -> bool:
        return PARKED_MARKER in self.text

    @cached_property
    def tasks(self) -> list[TaskNode]:
        """The open tasks, in the order a view shows them."""
        return sorted(
            visible_tasks(TodoDocument(self.text), self.today),
            key=lambda task: sort_key(task, self.today),
        )

    @property
    def order(self) -> tuple[int, str]:
        """Where this list sits among the others."""
        return category_order(self.category)


class Category:
    """One list's place in a view: what it shows, and what it holds back."""

    def __init__(
        self,
        name: str,
        tasks: list[TaskNode],
        limit: int | None,
    ) -> None:
        self.name = name
        self.tasks = tasks
        self.limit = limit

    @property
    def shown(self) -> list[TaskNode]:
        """The tasks that make it into the view."""
        return self.tasks if self.limit is None else self.tasks[: self.limit]

    @property
    def hidden(self) -> int:
        """How many tasks the limit held back."""
        return len(self.tasks) - len(self.shown)


class Selection:
    """What one view shows, for one directory read at one moment."""

    def __init__(
        self,
        directory: Path,
        now: datetime,
        *,
        show_all: bool,
        top_n: int = TOP_N,
    ) -> None:
        self.directory = directory
        self.now = now
        self.show_all = show_all
        self.top_n = top_n

    @classmethod
    def from_config(cls, conf: Configuration, now: datetime) -> 'Selection':
        """Build a selection from a resolved configuration.

        Every configuration value is a string, so the item count is
        decoded here. A flag the user left off is absent, not false.

        Raises
        ------
        ValueError
            The configured count is not a whole number of one or more.
        """
        return cls(
            Path(conf.view.source_dir),
            now,
            show_all=bool(getattr(conf, 'show_all', False)),
            top_n=item_count(conf.view.top),
        )

    @cached_property
    def today(self) -> date:
        return self.now.date()

    @property
    def limit(self) -> int | None:
        """How many items a category may show; None for all of them."""
        return None if self.show_all else self.top_n

    @cached_property
    def source(self) -> Path:
        """The resolved source directory.

        Raises
        ------
        SourceError
            The directory is not there.
        """
        resolved = self.directory.expanduser().resolve()
        if not resolved.is_dir():
            raise SourceError(f'todo source directory not found: {resolved}')
        return resolved

    @cached_property
    def active(self) -> set[str]:
        return active_categories(self.now)

    @cached_property
    def lists(self) -> list[TodoList]:
        """Every list in the source, in display order.

        Raises
        ------
        SourceError
            The directory holds no todo lists.
        """
        paths = discover_lists(self.source)
        if not paths:
            raise SourceError(
                f'no todo lists (no file with a "{OPEN_HEADING}" heading) '
                f'in: {self.source}'
            )
        found = [TodoList(path, self.today) for path in paths]
        return sorted(found, key=lambda todo: todo.order)

    def shows(self, todo: TodoList) -> bool:
        """Whether `todo` has any place in this view.

        A named category is shown while its window is open, or whenever
        everything has been asked for -- a shut window is the view being
        selective, and asking for all of it says not to be. A name the
        display order does not know has no window to be outside of.

        Opting out is not a window, and nothing reopens it: a parked
        list stays out of every view.
        """
        named = todo.category in CATEGORY_ORDER
        shut = named and todo.category not in self.active
        if shut and not self.show_all:
            return False
        return not todo.parked

    @cached_property
    def categories(self) -> list[Category]:
        """The categories a view renders, each with its tasks."""
        return [
            Category(todo.category, todo.tasks, self.limit)
            for todo in self.lists
            if self.shows(todo) and todo.tasks
        ]

    @cached_property
    def data(self) -> dict[str, object]:
        """The machine-readable form of this selection.

        Shaped as::

            {"date": "2026-08-05",
             "active": ["career", "events", "study", "work"],
             "categories": [{"name": "work", "hidden": 2, "tasks": [
                 {"id": null, "title": "...", "rank": 6.0,
                  "priority": 2.0, "loe": null, "due": null,
                  "added": "2026-05-10", "repeat": null,
                  "tags": [], "subtasks": 0}]}]}

        `hidden` is how many of the category's open items this leaves
        out. Without it an abridged document reads exactly like a
        complete one, and a reader has no way of knowing to ask for
        the rest.
        """
        return {
            'date': self.today.isoformat(),
            'active': sorted(self.active),
            'categories': [
                {
                    'name': category.name,
                    'hidden': category.hidden,
                    'tasks': [
                        task_entry(task, self.today) for task in category.shown
                    ],
                }
                for category in self.categories
            ],
        }

    @cached_property
    def json(self) -> str:
        """`data` as a JSON document, indented for a person to read too.

        The schema is a contract for agents; see `data` for its shape.
        """
        return dumps(self.data, indent=2)
