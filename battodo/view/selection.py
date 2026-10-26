"""Decide what a view shows: which lists, which tasks, in what order.

Layout has no say in what is chosen: the table module reads this one,
and never the other way about. The machine-readable form (README.md,
"Machine-readable output") lives here as `SelectionJsonView`, which
reads a selection through its attributes. The table's `RowView` and
the published form read the same row, so the two never derive a task
apart.

A view holds every open top-level item. A due date far ahead lowers an
item's rank instead of hiding it (ADR 0026).

Items sort by the rank computed in `rank.py` (ADR 0005) rather than by
stored priority, which is what lets the table show a rank at all: the
file states no order of its own.
"""

import re
from datetime import date, datetime
from functools import cached_property
from json import dumps
from pathlib import Path
from typing import NamedTuple

from batconf import Configuration

from ..lists import category_order, discover_lists, full_view, item_count
from ..parser import OPEN_HEADING, TaskNode, TodoDocument, parse_date
from ..rank import DEFAULT_DUE_CURVE, Curve, multiplier, parse_curve, rank
from ..repeat import WEEKDAYS


class SourceError(Exception):
    """The configured source directory yields no todo lists.

    Raised rather than rendering an empty view, which reads as
    "nothing to do" instead of "I looked in the wrong place". The
    message always carries the resolved path.
    """


NO_DUE_SORTS_LAST = 'zzzz'
# A list carrying this marker anywhere is parked: still discovered, so
# mutations reach it, but never surfaced in a view (ADR 0005).
PARKED_MARKER = 'battodo:parked'
# How many items of a category a view shows before it starts abridging.
TOP_N = 5
# How many decimal places a published rank carries.
RANK_PLACES = 2
# One window: a day or a run of days, then a span of whole hours.
WINDOW_RE = re.compile(
    rf'(?P<first>{"|".join(WEEKDAYS)})'
    rf'(?:\s*-\s*(?P<last>{"|".join(WEEKDAYS)}))?'
    r'\s+(?P<start>\d{1,2})\s*-\s*(?P<end>\d{1,2})',
    re.IGNORECASE,
)
# A window's end hour can reach the end of the day, and no further.
DAY_HOURS = 24
# What the windows of a view report when they do not read.
ENTRY_ERROR = 'a view.windows entry must read <category>=<window>'
WINDOW_ERROR = 'a view.windows window must read <days> <start>-<end>'
NAME_ERROR = 'view.windows names a category twice'


class Selection:
    """What one view shows, for one directory read at one moment."""

    def __init__(
        self,
        directory: Path,
        now: datetime,
        *,
        show_all: bool,
        top_n: int = TOP_N,
        rank_due_curve: str = DEFAULT_DUE_CURVE,
        windows: str = '',
        always_active: str = '',
    ) -> None:
        self.directory = directory
        self.now = now
        self.show_all = show_all
        self.top_n = top_n
        self.rank_due_curve = rank_due_curve
        self.windows = windows
        self.always_active = always_active

    @classmethod
    def from_config(
        cls,
        conf: Configuration,
        now: datetime,
        *,
        show_all: bool,
    ) -> 'Selection':
        """Build a selection from a resolved configuration.

        Every configuration value is a string, so the item count is
        decoded by `item_count`, and `view.all` by `full_view`.
        `show_all` shows every item whatever `view.all` holds. The
        due-date curve is decoded once, by `curve`, and the schedule by
        `schedule` and `always_open`.

        Raises
        ------
        ValueError
            The configured count is not a whole number of one or more,
            or `view.all` is not true or false.
        """
        return cls(
            Path(conf.view.source_dir),
            now,
            # The decode runs before the flag, so --all never hides a
            # bad view.all.
            show_all=full_view(conf.view.all) or show_all,
            top_n=item_count(conf.view.top),
            rank_due_curve=conf.view.rank_due_curve,
            # The lookup reads an empty value as absent, so each read
            # supplies the empty default itself.
            windows=getattr(conf.view, 'windows', ''),
            always_active=getattr(conf.view, 'always_active', ''),
        )

    @property
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
        """The categories open at `now`: the always-open names, and each
        category with a window that holds now.
        """
        names = set(self.always_open)
        names.update(
            name
            for name, windows in self.schedule.items()
                if any(window.holds(self.day, self.hour) for window in windows)
        )  # fmt: skip
        return names

    @property
    def always_open(self) -> frozenset[str]:
        """The categories no window shuts."""
        names = {part.strip() for part in self.always_active.split(',')}
        return frozenset(names - {''})

    @property
    def schedule(self) -> dict[str, list['Window']]:
        """The windows of each category the view schedules.

        Raises
        ------
        ValueError
            The configured windows do not read.
        """
        return parse_windows(self.windows)

    @property
    def day(self) -> int:
        """Which day of the week the clock falls on. Monday is 0."""
        return self.now.weekday()

    @property
    def hour(self) -> int:
        """The hour of the day the clock reads."""
        return self.now.hour

    @cached_property
    def lists(self) -> list['TodoList']:
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
        found = [TodoList(path, self.today, self.curve) for path in paths]
        return sorted(found, key=lambda todo: todo.order)

    @cached_property
    def curve(self) -> Curve:
        """The due-date curve every task of the view is ranked on.

        Raises
        ------
        ValueError
            The configured curve does not decode.
        """
        return parse_curve(self.rank_due_curve)

    def shows(self, todo: 'TodoList') -> bool:
        """Whether `todo` has any place in this view.

        A category with windows is shown while it is active, or whenever
        everything has been asked for -- a shut window is the view being
        selective, and asking for all of it says not to be. A category
        with no window has no window to be outside of.

        Opting out is not a window, and nothing reopens it: a parked
        list stays out of every view.
        """
        scheduled = todo.category in self.schedule
        shut = scheduled and todo.category not in self.active
        if shut and not self.show_all:
            return False
        return not todo.parked

    @cached_property
    def categories(self) -> list['Category']:
        """The categories a view renders, each with its rows."""
        return [
            Category(todo.category, todo.rows, self.limit)
            for todo in self.lists
                if self.shows(todo) and todo.rows
        ]  # fmt: skip


def parse_windows(text: str) -> dict[str, list['Window']]:
    """Decode the windows of each category from `text`.

    Parameters
    ----------
    text : str
        `<category>=<window>[, <window>]...` entries, separated by `;`.
        An empty text schedules nothing.

    Raises
    ------
    ValueError
        An entry or a window does not read, or two entries name the
        same category.
    """
    schedule: dict[str, list[Window]] = {}
    entries = text.split(';') if text.strip() else []
    for entry in entries:
        name, mark, spans = (part.strip() for part in entry.partition('='))
        if not (name and mark and spans):
            raise ValueError(f'{ENTRY_ERROR}: {entry.strip()!r}')
        if name in schedule:
            raise ValueError(f'{NAME_ERROR}: {name!r}')
        schedule[name] = [parse_window(span) for span in spans.split(',')]
    return schedule


def parse_window(text: str) -> 'Window':
    """Decode one `<days> <start>-<end>` window.

    Raises
    ------
    ValueError
        The window does not read, its days run backwards, or its hours
        do not fall inside one day.
    """
    token = text.strip()
    found = WINDOW_RE.fullmatch(token)
    if found is None:
        raise ValueError(f'{WINDOW_ERROR}: {token!r}')
    last_day = found['last'] or found['first']
    first = WEEKDAYS.index(found['first'].lower())
    last = WEEKDAYS.index(last_day.lower())
    start, end = int(found['start']), int(found['end'])
    if first > last or not start < end <= DAY_HOURS:
        raise ValueError(f'{WINDOW_ERROR}: {token!r}')
    return Window(first, last, start, end)


class Window(NamedTuple):
    """The hours a category is open on a run of days of the week.

    Days count from Monday as 0. `end` is the first hour past the window.
    """

    first: int
    last: int
    start: int
    end: int

    def holds(self, day: int, hour: int) -> bool:
        """Whether the window is open on `day` at `hour`."""
        return self.first <= day <= self.last and self.start <= hour < self.end


class TodoList:
    """One discovered list file: where it sorts, and what is open in it."""

    def __init__(self, path: Path, today: date, curve: Curve) -> None:
        self.path = path
        self.today = today
        self.curve = curve

    @cached_property
    def category(self) -> str:
        """The list's name: the file's name without its extension."""
        return self.path.stem

    @cached_property
    def text(self) -> str:
        return self.path.read_text()

    @cached_property
    def document(self) -> TodoDocument:
        """The list file, parsed."""
        return TodoDocument(self.text)

    @cached_property
    def open_rows(self) -> list['Row']:
        """A row per open top-level task."""
        return [
            Row(task, self.today, self.curve)
            for task in self.document.tasks
                if not task.done
        ]  # fmt: skip

    @cached_property
    def parked(self) -> bool:
        return PARKED_MARKER in self.text

    @cached_property
    def rows(self) -> list['Row']:
        """A row per open task, in the order a view shows them."""
        return sorted(self.open_rows, key=lambda row: row.key)

    @property
    def order(self) -> tuple[int, str]:
        """Where this list sits among the others."""
        return category_order(self.category)


class Category:
    """One list's place in a view: what it shows, and what it holds back."""

    def __init__(
        self,
        name: str,
        rows: list['Row'],
        limit: int | None,
    ) -> None:
        self.name = name
        self.rows = rows
        self.limit = limit

    @property
    def shown(self) -> list['Row']:
        """The rows that make it into the view."""
        return self.rows if self.limit is None else self.rows[: self.limit]

    @property
    def hidden(self) -> int:
        """How many rows the limit held back."""
        return len(self.rows) - len(self.shown)


class Row:
    """One task as a view carries it: its rank, priority and children.

    `RowView` lays the row out as a table line, and `RowJsonView`
    publishes the task's record from the same values.
    """

    def __init__(self, task: TaskNode, today: date, curve: Curve) -> None:
        self.task = task
        self.today = today
        self.curve = curve

    @cached_property
    def key(self) -> tuple[float, str, str]:
        """Rank descending, then nearest due, undated last, then title."""
        return (
            -self.rank,
            self.task.due or NO_DUE_SORTS_LAST,
            self.task.title,
        )

    @cached_property
    def rank(self) -> float:
        """The task's rank on the day and the curve of the view."""
        return rank(self.task, self.today, self.curve)

    @cached_property
    def priority(self) -> float:
        """The task's stored priority, as a multiplier."""
        return multiplier(self.task)

    @cached_property
    def subtasks(self) -> int:
        """How many of the task's children are still open."""
        return len(self.children)

    @cached_property
    def children(self) -> list[TaskNode]:
        """The task's incomplete children: subtasks and checklist items."""
        return [
            child
            for child in self.task.children
                if not child.done
        ]  # fmt: skip

    @cached_property
    def parsed_due(self) -> date | None:
        """The stored due date as a date, or None if it cannot be read."""
        return parse_date(self.task.due)


class SelectionJsonView:
    """A selection laid out as JSON, for an agent to read."""

    def __init__(self, selection: Selection) -> None:
        self.selection = selection

    @property
    def json(self) -> str:
        """`data` as a JSON document, indented for a person to read too.

        The schema is a contract for agents; see `data` for its shape.
        """
        return dumps(self.data, indent=2)

    @property
    def data(self) -> dict[str, object]:
        """The machine-readable form of the selection.

        Shaped as::

            {"date": "2026-08-05",
             "active": ["career", "events", "study", "work"],
             "categories": [{"name": "work", "hidden": 2, "tasks": [
                 {"list": "work", "id": null, "title": "...", "rank": 6.0,
                  "priority": 2.0, "loe": null, "due": null,
                  "added": "2026-05-10", "repeat": null,
                  "tags": [], "subtasks": 0}]}]}
        """
        return {
            'date': self.selection.today.isoformat(),
            'active': sorted(self.selection.active),
            'categories': [category.data for category in self.categories],
        }

    @property
    def categories(self) -> list['CategoryJsonView']:
        """The selection's categories, each laid out as JSON."""
        return [
            CategoryJsonView(category)
            for category in self.selection.categories
        ]


class CategoryJsonView:
    """One category of a selection laid out as JSON."""

    def __init__(self, category: Category) -> None:
        self.category = category

    @property
    def data(self) -> dict[str, object]:
        """The category as `SelectionJsonView.data` records it.

        `hidden` is how many of the category's open items the view
        leaves out. Without it an abridged document reads exactly like
        a complete one, and a reader has no way of knowing to ask for
        the rest.
        """
        return {
            'name': self.category.name,
            'hidden': self.category.hidden,
            'tasks': [row.data for row in self.rows],
        }

    @property
    def rows(self) -> list['RowJsonView']:
        """The rows the category shows, each laid out as JSON."""
        name = self.category.name
        return [RowJsonView(row, name) for row in self.category.shown]


class RowJsonView:
    """One task of a selection laid out as JSON.

    `list_name` is the name of the category that shows the row.
    """

    def __init__(self, row: Row, list_name: str) -> None:
        self.row = row
        self.list_name = list_name

    @property
    def data(self) -> dict[str, object]:
        """The task as `CategoryJsonView.data` records it.

        Stored fields are carried verbatim -- no OVERDUE/TODAY labels.
        `rank` is rounded for display and must not be used to re-sort;
        the array order is the rank order.
        """
        task = self.row.task
        return {
            'list': self.list_name,
            'id': task.task_id,
            'title': task.title,
            'rank': round(self.row.rank, RANK_PLACES),
            'priority': self.row.priority,
            'loe': task.loe,
            'due': task.due,
            'added': task.added,
            'repeat': task.repeat,
            'tags': task.tags,
            'subtasks': self.row.subtasks,
        }
