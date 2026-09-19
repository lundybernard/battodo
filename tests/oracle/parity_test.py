"""Parity checks between the folded view objects and the functions.

Temporary scaffolding for the conversion of `battodo.view.selection` to
property objects. Each case runs one generated list file through both
surfaces and asserts they answer alike. It is deleted with the
functions it compares against.

The generated files and the recorded cases come from `view_test`, so
both halves of the bracket read the same input.
"""

from unittest import TestCase

from hypothesis import example, given, settings

from battodo.view.render import Row as TableRow
from battodo.view.selection import (
    Row,
    TaskNode,
    TodoDocument,
    TodoList,
    open_children,
    sort_key,
    task_entry,
    visible_tasks,
)

from ..property.strategies import document
from .view_test import CATEGORY, KNOWN_LINES, LIST_FILES, NOW, source

TODAY = NOW.date()


def parse(lines: list[str]) -> list[TaskNode]:
    """The top-level tasks of the list file `lines` make."""
    return TodoDocument(document(lines)).tasks


class RowTests(TestCase):
    """Parity checks for battodo.view.selection.Row."""

    maxDiff = None

    @settings(deadline=None)
    @example(lines=KNOWN_LINES)
    @given(LIST_FILES)
    def test_data(t, lines: list[str]) -> None:
        tasks = parse(lines)

        ret = [Row(task, TODAY).data for task in tasks]

        t.assertEqual(ret, [task_entry(task, TODAY) for task in tasks])

    @settings(deadline=None)
    @example(lines=KNOWN_LINES)
    @given(LIST_FILES)
    def test_key(t, lines: list[str]) -> None:
        tasks = parse(lines)

        ret = [Row(task, TODAY).key for task in tasks]

        t.assertEqual(ret, [sort_key(task, TODAY) for task in tasks])

    @settings(deadline=None)
    @example(lines=KNOWN_LINES)
    @given(LIST_FILES)
    def test_children(t, lines: list[str]) -> None:
        tasks = parse(lines)

        ret = [Row(task, TODAY).children for task in tasks]

        t.assertEqual(ret, [open_children(task) for task in tasks])

    @settings(deadline=None)
    @example(lines=KNOWN_LINES)
    @given(LIST_FILES)
    def test_cells(t, lines: list[str]) -> None:
        tasks = parse(lines)

        ret = [Row(task, TODAY).cells for task in tasks]

        t.assertEqual(ret, [TableRow(task, TODAY).cells for task in tasks])


class TodoListTests(TestCase):
    """Parity checks for battodo.view.selection.TodoList."""

    maxDiff = None

    @settings(deadline=None)
    @example(lines=KNOWN_LINES)
    @given(LIST_FILES)
    def test_visible(t, lines: list[str]) -> None:
        with source(lines) as directory:
            todo = TodoList(directory / f'{CATEGORY}.md', TODAY)

            ret = todo.visible

            # The parsed document is cached, so both surfaces read the
            # same task objects and compare by identity.
            expected = visible_tasks(todo.document, TODAY)

        t.assertEqual([row.task for row in ret], expected)
