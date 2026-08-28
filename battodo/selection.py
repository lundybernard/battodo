"""Which open task a selector names.

The lookup reads every discovered list, parked ones included, and
searches at every depth: a subtask carries no `[ID:]` until btodo first
touches it, so title text is the only way to reach one. A selector must
land on exactly one open task; anything else is a `SelectionError`, and
the fix is always a longer selector or the task's `[ID:]`.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from .parser import TaskNode, TodoFile, parse
from .view.selection import discover_lists


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


def _descend(
    tasks: list[TaskNode],
    ancestry: list[TaskNode],
) -> Iterator[list[TaskNode]]:
    """Every task at any depth, each with its ancestry."""
    for task in tasks:
        found = [*ancestry, task]
        yield found
        yield from _descend(task.children, found)


def _selects(task: TaskNode, selector: str) -> bool:
    return task.task_id == selector or selector.lower() in task.title.lower()


class TaskSelection:
    """The open tasks a selector reaches in a source directory."""

    def __init__(self, directory: Path, selector: str) -> None:
        self.directory = directory
        self.selector = selector

    @cached_property
    def lists(self) -> list[tuple[Path, TodoFile]]:
        """Every discovered list, parsed, beside the path it came from."""
        return [
            (path, parse(path.read_text()))
            for path in discover_lists(self.directory)
        ]

    @cached_property
    def records(self) -> list[TaskRecord]:
        """Every open task the selector reaches, at any depth.

        An `[ID:]` record narrows out the title records, so a
        selector that is an id names the task carrying it rather than
        the tasks quoting it.
        """
        found = [
            TaskRecord(path, doc, ancestry)
            for path, doc in self.lists
            for ancestry in _descend(doc.tasks, [])
            if not ancestry[-1].done and _selects(ancestry[-1], self.selector)
        ]
        by_id = [
            record for record in found if record.task.task_id == self.selector
        ]
        return by_id or found

    @cached_property
    def record(self) -> TaskRecord:
        """The one open task the selector names.

        Raises
        ------
        SelectionError
            Nothing matches, or more than one does.
        """
        records = self.records
        if not records:
            raise SelectionError(f'no open task matches {self.selector!r}')
        if len(records) > 1:
            titles = ', '.join(repr(record.task.title) for record in records)
            raise SelectionError(
                f'{self.selector!r} matches {len(records)} open tasks: '
                f'{titles}'
            )
        return records[0]
