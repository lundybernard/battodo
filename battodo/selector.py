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

from .lists import discover_lists
from .parser import TaskNode, TodoDocument


class SelectionError(Exception):
    """A selector did not name exactly one open task.

    Carries the record titles when more than one task answers: the
    fix is always a longer selector or the task's `[ID:]`.
    """


class TaskSelection:
    """The open tasks a selector reaches in a source directory.

    `lists` caches what it read, so one instance answers from one
    snapshot. A caller that writes a list builds a new selection.
    """

    def __init__(self, directory: Path, selector: str) -> None:
        self._directory = directory
        self._selector = selector

    @cached_property
    def lists(self) -> list[tuple[Path, TodoDocument]]:
        """Every discovered list, parsed, beside the path it came from."""
        return [
            (path, TodoDocument(path.read_text()))
            for path in discover_lists(self._directory)
        ]

    @cached_property
    def records(self) -> list['TaskRecord']:
        """Every open task the selector reaches, at any depth.

        An `[ID:]` record narrows out the title records, so a
        selector that is an id names the task carrying it rather than
        the tasks quoting it.
        """
        found = [
            TaskRecord(path, doc, ancestry)
            for path, doc in self.lists
            for ancestry in doc.ancestries
                if not ancestry[-1].done and self._selects(ancestry[-1])
        ]  # fmt: skip
        by_id = [
            record
            for record in found
                if record.task.task_id == self._selector
        ]  # fmt: skip
        return by_id or found

    def _selects(self, task: TaskNode) -> bool:
        """Whether the selector names `task`, done or not.

        An `[ID:]` equal to the selector names it, and so does a title
        that holds the selector in any case.
        """
        part = self._selector.lower()
        return task.task_id == self._selector or part in task.title.lower()

    @cached_property
    def record(self) -> 'TaskRecord':
        """The one open task the selector names.

        Raises
        ------
        SelectionError
            Nothing matches, or more than one does.
        """
        records = self.records
        if not records:
            raise SelectionError(f'no open task matches {self._selector!r}')
        if len(records) > 1:
            titles = ', '.join(repr(record.task.title) for record in records)
            raise SelectionError(
                f'{self._selector!r} matches {len(records)} open tasks: '
                f'{titles}'
            )
        return records[0]


@dataclass
class TaskRecord:
    """One open task, the list it lives in, and its ancestry.

    Internal to this module: `battodo.task.Task` gives callers the same
    fields.
    """

    path: Path
    doc: TodoDocument
    ancestry: list[TaskNode]

    @property
    def task(self) -> TaskNode:
        return self.ancestry[-1]
