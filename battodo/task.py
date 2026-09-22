"""The one task a command names, and what a command does to it.

`Task` decides which open task a selector reaches and which day a
completion is logged under. The write itself stays in `mutate`, which
owns the markdown and the journal. `lib` composes the two.
"""

from datetime import date, datetime
from functools import cached_property
from pathlib import Path

from batconf import Configuration

from .parser import TaskNode, TodoDocument, parse_date
from .selector import TaskSelection


def _completion_day(given: str | None, now: datetime) -> date:
    """The day a completion is logged under.

    Raises
    ------
    ValueError
        `given` is not an ISO date.
    """
    if given is None:
        return now.date()
    day = parse_date(given)
    if day is None:
        raise ValueError(f'completion date must be an ISO date, not {given!r}')
    return day


class Task:
    """One open task, selected from the source directory."""

    def __init__(self, directory: Path, selector: str, today: date) -> None:
        self.directory = directory
        self.selector = selector
        self.today = today

    @classmethod
    def from_config(cls, conf: Configuration, now: datetime) -> 'Task':
        """Build a task from a resolved configuration.

        A date the user left off is absent, not None, and the clock
        answers for it.

        Raises
        ------
        ValueError
            The configured date is not an ISO date. Raised before
            anything is written.
        """
        return cls(
            Path(conf.view.source_dir),
            conf.selector,
            _completion_day(getattr(conf, 'date', None), now),
        )

    @cached_property
    def source(self) -> Path:
        """The source directory, `~` expanded."""
        return self.directory.expanduser()

    @property
    def path(self) -> Path:
        """The list file that holds the task."""
        return self.selection.record.path

    @property
    def doc(self) -> TodoDocument:
        """The parsed list file that holds the task."""
        return self.selection.record.doc

    @property
    def ancestry(self) -> list[TaskNode]:
        """The task and every task above it, outermost first."""
        return self.selection.record.ancestry

    @property
    def node(self) -> TaskNode:
        """The task as the parser reads it."""
        return self.ancestry[-1]

    @cached_property
    def selection(self) -> TaskSelection:
        """The open tasks the selector reaches in the source.

        One selection answers from one read of the source, so every
        property above reads the same document.
        """
        return TaskSelection(self.source, self.selector)
