"""Characterization tests for the task a selector names.

Temporary scaffolding for the move of the selected task onto `Task`.
The suite pins which open task `TaskSelection.record` names in a list
file drawn from the schema grammar, and the error it raises when a
selector names no task or several. It is deleted with the record it
pins.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from hypothesis import given
from hypothesis import strategies as st

from battodo.parser import TaskNode, TodoDocument
from battodo.selector import SelectionError, TaskSelection

from ..property.strategies import Node, grammar

# The one list a generated source holds.
LIST_FILE = 'a-list.md'


class TaskSelectionTests(TestCase):
    """Characterization tests for battodo.selector.TaskSelection."""

    @given(grammar.documents, st.data())
    def test_record(
        t,
        drawn: tuple[str, list[Node]],
        data: st.DataObject,
    ) -> None:
        text, _ = drawn
        ancestries = descend(TodoDocument(as_read(text)).tasks, [])
        selector = data.draw(selectors(ancestries))
        expected = outcome(ancestries, selector)

        with source(text) as directory:
            ret = answer(TaskSelection(directory, selector))

        t.assertEqual(ret, expected)


def as_read(text: str) -> str:
    """The text as a read in text mode returns it, each line end a newline."""
    return StringIO(text, newline=None).read()


def descend(
    tasks: list[TaskNode],
    ancestry: list[TaskNode],
) -> list[list[TaskNode]]:
    """Every task at any depth, each with its ancestry, parents first."""
    found = []
    for task in tasks:
        found.append([*ancestry, task])
        found.extend(descend(task.children, [*ancestry, task]))
    return found


def selectors(ancestries: list[list[TaskNode]]) -> st.SearchStrategy[str]:
    """A drawn task's title or id, or a title no task need carry."""
    tasks = [ancestry[-1] for ancestry in ancestries]
    # fmt: off
    names = [
        name
        for task in tasks
        for name in (task.title, task.task_id)
            if name
    ]
    # fmt: on
    if not names:
        return grammar.titles
    return st.one_of(grammar.titles, st.sampled_from(names))


def outcome(
    ancestries: list[list[TaskNode]],
    selector: str,
) -> tuple[str, list[TaskNode]] | str:
    """The list and ancestry the selector names, or the error text."""
    # fmt: off
    found = [
        ancestry
        for ancestry in ancestries
            if not ancestry[-1].done
            and (
                ancestry[-1].task_id == selector
                or selector.lower() in ancestry[-1].title.lower()
            )
    ]
    by_id = [
        ancestry
        for ancestry in found
            if ancestry[-1].task_id == selector
    ]
    # fmt: on
    named = by_id or found
    if not named:
        return f'no open task matches {selector!r}'
    if len(named) > 1:
        titles = ', '.join(repr(ancestry[-1].title) for ancestry in named)
        return f'{selector!r} matches {len(named)} open tasks: {titles}'
    return LIST_FILE, named[0]


@contextmanager
def source(text: str) -> Iterator[Path]:
    """A source directory holding `text` as its one list file."""
    with TemporaryDirectory() as tmp:
        directory = Path(tmp)
        (directory / LIST_FILE).write_text(text, encoding='utf-8')
        yield directory


def answer(selection: TaskSelection) -> tuple[str, list[TaskNode]] | str:
    """The list and ancestry the selection names, or the error text."""
    try:
        record = selection.record
    except SelectionError as error:
        return str(error)
    return record.path.name, record.ancestry
