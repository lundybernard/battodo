"""Property tests for the task a selector names, driven by Hypothesis.

Each case writes a list file drawn from the schema grammar, then
asserts what `Task` holds for a selector: the list, the document and
the ancestry, or the error text when the selector names no open task
or several. The expected answer derives from the drawn file, never
from the code under test.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from hypothesis import given
from hypothesis import strategies as st

from battodo.parser import TaskNode, TodoDocument
from battodo.selector import SelectionError
from battodo.task import Task

from .strategies import Node, grammar

# The one list a generated source holds.
LIST_FILE = 'a-list.md'
# A day no selection reads.
TODAY = date(2026, 8, 5)

Answer = tuple[str, str, list[TaskNode]] | str


class TaskTests(TestCase):
    """Property tests for battodo.task.Task."""

    @given(grammar.documents, st.data())
    def test_selection(
        t,
        drawn: tuple[str, list[Node]],
        data: st.DataObject,
    ) -> None:
        text, _ = drawn
        read = as_read(text)
        ancestries = descend(TodoDocument(read).tasks, [])
        selector = data.draw(selectors(ancestries))
        expected = outcome(read, ancestries, selector)

        with source(text) as directory:
            ret = answer(Task(directory, selector, TODAY))

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
    read: str,
    ancestries: list[list[TaskNode]],
    selector: str,
) -> Answer:
    """What the task holds for the selector, or the error text.

    An `[ID:]` match narrows out the title matches.
    """
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
    return LIST_FILE, read, named[0]


@contextmanager
def source(text: str) -> Iterator[Path]:
    """A source directory holding `text` as its one list file."""
    with TemporaryDirectory() as tmp:
        directory = Path(tmp)
        (directory / LIST_FILE).write_text(text, encoding='utf-8')
        yield directory


def answer(task: Task) -> Answer:
    """What the task holds, or the error text."""
    try:
        return task.path.name, task.doc.text, task.ancestry
    except SelectionError as error:
        return str(error)
