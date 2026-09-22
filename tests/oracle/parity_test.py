"""Parity tests for the Task selection properties.

Temporary scaffolding: `Task` answers as the selection record it
replaces, for list files drawn from the schema grammar. The suite is
deleted with the record's public surface.
"""

from datetime import date
from pathlib import Path
from unittest import TestCase

from hypothesis import given
from hypothesis import strategies as st

from battodo.parser import TaskNode, TodoDocument
from battodo.selector import SelectionError, TaskSelection
from battodo.task import Task

from ..property.strategies import Node, grammar
from .selector_test import as_read, descend, selectors, source

# A day no selection reads.
TODAY = date(2026, 8, 5)

Answer = tuple[Path, str, list[TaskNode], TaskNode] | str


class TaskTests(TestCase):
    """Parity tests for battodo.task.Task against TaskSelection.record."""

    @given(grammar.documents, st.data())
    def test_selection(
        t,
        drawn: tuple[str, list[Node]],
        data: st.DataObject,
    ) -> None:
        text, _ = drawn
        ancestries = descend(TodoDocument(as_read(text)).tasks, [])
        selector = data.draw(selectors(ancestries))

        with source(text) as directory:
            ret = task_answer(Task(directory, selector, TODAY))
            expected = record_answer(TaskSelection(directory, selector))

        t.assertEqual(ret, expected)


def task_answer(task: Task) -> Answer:
    """What the task holds, or the error text."""
    try:
        return task.path, task.doc.text, task.ancestry, task.node
    except SelectionError as error:
        return str(error)


def record_answer(selection: TaskSelection) -> Answer:
    """What the selection record holds, or the error text."""
    try:
        record = selection.record
    except SelectionError as error:
        return str(error)
    return record.path, record.doc.text, record.ancestry, record.task
