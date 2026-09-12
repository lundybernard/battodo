"""Property tests for `battodo.parser`, driven by Hypothesis.

Each case generates a todo list from the task-line grammar in
`strategies`, then asserts what the parser reads back from it. The suite
is higher-order: it runs outside the coverage and mutation gates.
"""

from unittest import TestCase

from hypothesis import example, given, settings
from hypothesis import strategies as st

from battodo.parser import TaskNode, TodoDocument

from .strategies import Node, document, documents, task_lines


def walk(tasks: list[TaskNode]) -> list[TaskNode]:
    """Every task in the tree, parents before children."""
    found = []
    for task in tasks:
        found.append(task)
        found.extend(walk(task.children))
    return found


def shape(tasks: list[TaskNode], lines: list[str]) -> list[Node]:
    """The task tree as the node shape the strategies draw."""
    return [
        Node(
            task.raw,
            [lines[index] for index in task.note_indices],
            shape(task.children, lines),
            task.is_subtask,
        )
        for task in tasks
    ]


class TodoDocumentTests(TestCase):
    @settings(max_examples=25)
    @given(st.text())
    def test_any_text_parses(t, text: str) -> None:
        doc = TodoDocument(text)
        ret = doc.tasks
        t.assertIsInstance(ret, list)

    @settings(max_examples=200)
    @given(st.lists(task_lines(), max_size=6))
    def test_every_task_line_is_a_task(t, lines: list[str]) -> None:
        doc = TodoDocument(document(lines))
        ret = walk(doc.tasks)
        t.assertEqual(len(ret), len(lines))

    @settings(max_examples=200)
    @example(lines=['- [ ] 0 [LOE::]'])
    @given(st.lists(task_lines(), min_size=1, max_size=6))
    def test_every_field_reads(t, lines: list[str]) -> None:
        doc = TodoDocument(document(lines))

        ret = [
            (task.loe, task.due, task.tags, task.task_id, task.repeat)
            for task in walk(doc.tasks)
        ]

        t.assertEqual(len(ret), len(lines))

    @settings(max_examples=200)
    @given(documents())
    def test_open_section_reads_back(t, case: tuple[str, list[Node]]) -> None:
        source, expected = case
        doc = TodoDocument(source)

        ret = shape(doc.tasks, doc.lines)

        t.assertEqual(ret, expected)
