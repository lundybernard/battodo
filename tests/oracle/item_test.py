"""Characterization tests for the item read.

Temporary scaffolding for the move of the item read onto property
objects. The suite pins what `build_item_json` publishes and what
`build_item` renders for the task a selector names in a list file drawn
from the schema grammar, and the error text when the selector names no
open task or several. The expected answer derives from the drawn file
and the clock, never from the code under test.
"""

from collections.abc import Callable
from datetime import datetime, timezone
from json import dumps
from pathlib import Path
from typing import Any
from unittest import TestCase

from hypothesis import given
from hypothesis import strategies as st

from battodo.item import build_item, build_item_json
from battodo.parser import TaskNode, TodoDocument
from battodo.rank import multiplier, rank
from battodo.selector import SelectionError
from battodo.view import RANK_PLACES
from tests.property.strategies import Node, grammar
from tests.property.task_test import (
    Answer,
    descend,
    outcome,
    selectors,
    source,
)

# The clock every read is asked at.
NOW = datetime(2026, 8, 5, 10, 30, tzinfo=timezone.utc)
TODAY = NOW.date()
# The indent the text form lays each level out with.
INDENT = '  '


class BuildItemJsonTests(TestCase):
    """Characterization tests for battodo.item.build_item_json."""

    maxDiff = None

    @given(grammar.documents, st.data())
    def test_document(
        t,
        drawn: tuple[str, list[Node]],
        data: st.DataObject,
    ) -> None:
        text, _ = drawn
        ancestries = descend(TodoDocument(text).tasks, [])
        selector = data.draw(item_selectors(ancestries))
        expected = published(outcome(text, ancestries, selector))

        with source(text) as directory:
            ret = answer(build_item_json, directory, selector)

        t.assertEqual(ret, expected)


class BuildItemTests(TestCase):
    """Characterization tests for battodo.item.build_item."""

    maxDiff = None

    @given(grammar.documents, st.data())
    def test_text(
        t,
        drawn: tuple[str, list[Node]],
        data: st.DataObject,
    ) -> None:
        text, _ = drawn
        ancestries = descend(TodoDocument(text).tasks, [])
        selector = data.draw(item_selectors(ancestries))
        expected = rendered(outcome(text, ancestries, selector))

        with source(text) as directory:
            ret = answer(build_item, directory, selector)

        t.assertEqual(ret, expected)


def item_selectors(
    ancestries: list[list[TaskNode]],
) -> st.SearchStrategy[str]:
    """An open task's title or id, or any selector the task suite draws.

    Half the draws name an open task, so most cases read an item.
    """
    # fmt: off
    names = [
        name
        for ancestry in ancestries
            if not ancestry[-1].done
        for name in (ancestry[-1].title, ancestry[-1].task_id)
            if name
    ]
    # fmt: on
    if not names:
        return selectors(ancestries)
    return st.one_of(st.sampled_from(names), selectors(ancestries))


def published(found: Answer) -> str:
    """The document the item publishes, or the error text."""
    if isinstance(found, str):
        return found
    name, _, ancestry = found
    return dumps(record(Path(name).stem, ancestry[-1]), indent=2)


def record(name: str, task: TaskNode) -> dict[str, Any]:
    """The task in list `name`: its fields, its rank, its children."""
    return {
        'list': name,
        'id': task.task_id,
        'title': task.title,
        'done': task.done,
        'rank': round(rank(task, TODAY), RANK_PLACES),
        'priority': multiplier(task),
        'loe': task.loe,
        'due': task.due,
        'added': task.added,
        'repeat': task.repeat,
        'tags': task.tags,
        'subtasks': [child_record(child) for child in task.children],
    }


def child_record(task: TaskNode) -> dict[str, Any]:
    """One child and its own children. A child carries no rank."""
    return {
        'id': task.task_id,
        'title': task.title,
        'done': task.done,
        'loe': task.loe,
        'due': task.due,
        'tags': task.tags,
        'subtasks': [child_record(child) for child in task.children],
    }


def answer(
    build: Callable[[Path, str, datetime], str],
    directory: Path,
    selector: str,
) -> str:
    """What `build` returns for the selector, or the error text."""
    try:
        return build(directory, selector, NOW)
    except SelectionError as error:
        return str(error)


def rendered(found: Answer) -> str:
    """The item as a terminal shows it, or the error text.

    The title leads. A labelled row follows per value, the values in
    one column. The children close it, one line each.
    """
    if isinstance(found, str):
        return found
    name, _, ancestry = found
    task = ancestry[-1]
    rows = labelled(Path(name).stem, task)
    width = max(len(label) for label, _ in rows)
    lines = [task.title]
    lines.extend(
        f'{INDENT}{label:<{width}}{INDENT}{value}' for label, value in rows
    )
    if task.children:
        lines.append(f'{INDENT}subtasks')
        lines.extend(outline(task.children, 2))
    return '\n'.join(lines)


def labelled(name: str, task: TaskNode) -> list[tuple[str, str]]:
    """The rows of the text form. An absent field has none.

    An absent id reads as a dash. The rank is the published one, shown
    to one decimal place.
    """
    rows = [
        ('list', name),
        ('id', task.task_id or '-'),
        ('rank', f'{round(rank(task, TODAY), RANK_PLACES):.1f}'),
        ('P', f'{multiplier(task):.1f}'),
    ]
    stored = (('LOE', task.loe), ('DUE', task.due), ('REPEAT', task.repeat))
    rows.extend(
        (label, str(value)) for label, value in stored if value is not None
    )
    if task.tags:
        rows.append(('TAGS', ', '.join(task.tags)))
    if task.added is not None:
        rows.append(('ADDED', task.added))
    return rows


def outline(tasks: list[TaskNode], depth: int) -> list[str]:
    """Each child in schema markup, its own children one indent deeper."""
    lines = []
    for task in tasks:
        mark = 'x' if task.done else ' '
        fields = ''.join(
            f' [{name}:{value}]'
            for name, value in (
                ('LOE', task.loe),
                ('DUE', task.due),
                ('TAGS', ','.join(task.tags) or None),
                ('ID', task.task_id),
            )
            if value is not None
        )
        lines.append(f'{INDENT * depth}[{mark}] {task.title}{fields}')
        lines.extend(outline(task.children, depth + 1))
    return lines
