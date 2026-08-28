"""Which open task a selector names.

The lookup reads every discovered list, parked ones included, and
searches at every depth: a subtask carries no `[ID:]` until btodo first
touches it, so title text is the only way to reach one. A selector must
land on exactly one open task; anything else is a `SelectionError`, and
the fix is always a longer selector or the task's `[ID:]`.
"""

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from .parser import TaskNode, TodoFile


class SelectionError(Exception):
    """A selector did not name exactly one open task.

    Carries the record titles when more than one task answers: the
    fix is always a longer selector or the task's `[ID:]`.
    """


@dataclass
class TaskRecord:
    """One open task, the list it lives in, and its ancestry."""

    path: Path
    doc: TodoFile
    ancestry: list[TaskNode]

    @property
    def task(self) -> TaskNode:
        return self.ancestry[-1]


class TaskSelection:
    """The open tasks a selector reaches in a source directory."""

    def __init__(self, directory: Path, selector: str) -> None:
        self.directory = directory
        self.selector = selector

    @cached_property
    def lists(self) -> list[tuple[Path, TodoFile]]:
        """Every discovered list, parsed, beside the path it came from."""
        raise NotImplementedError

    @cached_property
    def records(self) -> list[TaskRecord]:
        """Every open task the selector reaches, at any depth.

        An `[ID:]` record narrows out the title records, so a
        selector that is an id names the task carrying it rather than
        the tasks quoting it.
        """
        raise NotImplementedError

    @cached_property
    def record(self) -> TaskRecord:
        """The one open task the selector names.

        Raises
        ------
        SelectionError
            Nothing matches, or more than one does.
        """
        raise NotImplementedError
