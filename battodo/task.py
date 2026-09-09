"""The one task a command names, and what a command does to it.

`Task` decides which open task a selector reaches and which day a
completion is logged under. The write itself stays in `mutate`, which
owns the markdown and the journal. `lib` composes the two.
"""

from datetime import date, datetime
from functools import cached_property
from pathlib import Path

from batconf import Configuration

from .mutate import complete
from .parser import parse_date
from .selector import TaskRecord, TaskSelection


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
        self.completed: list[str] = []

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

    @cached_property
    def record(self) -> TaskRecord:
        """The task the selector names, with the list that holds it.

        Raises
        ------
        SelectionError
            The selector does not name exactly one open task.
        """
        return TaskSelection(self.source, self.selector).record

    def complete(self) -> None:
        """Log the completion under the day this task carries.

        Raises
        ------
        SelectionError
            The selector does not name exactly one open task.
        RepeatError
            The task repeats on a `[REPEAT:]` btodo cannot read. Raised
            before anything is written.
        """
        self.completed = complete(self.source, self.selector, self.today)
