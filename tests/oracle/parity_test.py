"""Parity tests for the item objects.

Temporary scaffolding: `ItemJsonView` and `ItemView` answer as the
functions they replace, for list files drawn from the schema grammar.
The suite is deleted with those functions.
"""

from pathlib import Path
from unittest import TestCase

from hypothesis import given
from hypothesis import strategies as st

from battodo.item import (
    Item,
    ItemJsonView,
    ItemView,
    build_item,
    build_item_json,
)
from battodo.parser import TodoDocument
from battodo.selector import SelectionError
from battodo.task import Task
from tests.property.strategies import Node, grammar
from tests.property.task_test import descend, source

from .item_test import TODAY, answer, item_selectors


class ItemJsonViewTests(TestCase):
    """Parity tests for battodo.item.ItemJsonView.json.

    The reference is build_item_json.
    """

    maxDiff = None

    @given(grammar.documents, st.data())
    def test_json(
        t,
        drawn: tuple[str, list[Node]],
        data: st.DataObject,
    ) -> None:
        text, _ = drawn
        ancestries = descend(TodoDocument(text).tasks, [])
        selector = data.draw(item_selectors(ancestries))

        with source(text) as directory:
            ret = document(directory, selector)
            expected = answer(build_item_json, directory, selector)

        t.assertEqual(ret, expected)


class ItemViewTests(TestCase):
    """Parity tests for battodo.item.ItemView.text against build_item."""

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

        with source(text) as directory:
            ret = rendering(directory, selector)
            expected = answer(build_item, directory, selector)

        t.assertEqual(ret, expected)


def document(directory: Path, selector: str) -> str:
    """The document the item publishes, or the error text."""
    try:
        task = Task(
            directory,
            selector,
            TODAY,
        )
        return ItemJsonView(Item(task)).json
    except SelectionError as error:
        return str(error)


def rendering(directory: Path, selector: str) -> str:
    """The item as its view renders it, or the error text."""
    try:
        task = Task(
            directory,
            selector,
            TODAY,
        )
        return ItemView(Item(task)).text
    except SelectionError as error:
        return str(error)
