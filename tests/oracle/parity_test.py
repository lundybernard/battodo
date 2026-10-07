"""Parity tests for the write objects.

Temporary scaffolding: each write object, written out as the lib entry
points write one, leaves a source drawn from the schema grammar as the
mutate function it replaces leaves it, and answers as that function
answers. The suite is deleted with those functions.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest import TestCase
from unittest.mock import patch

from hypothesis import given
from hypothesis import strategies as st

from battodo.journal import Journal
from battodo.mutate import (
    Addition,
    Backfill,
    CompletedLog,
    Completion,
    ListError,
    Scratch,
    SubtaskAddition,
    Update,
    add_subtask,
    add_task,
    backfill_all,
    complete,
    scratch,
    update_task,
)
from battodo.parser import TodoDocument
from battodo.selector import SelectionError
from battodo.task import Task
from tests.property.item_test import item_selectors
from tests.property.strategies import TODAY, Node, grammar
from tests.property.task_test import descend

from .mutate_test import (
    ADD_OPTIONS,
    MUTATE,
    SOURCE,
    UPDATE_OPTIONS,
    Outcome,
    Source,
    canonical,
    held,
    list_names,
    logs,
    new_ids,
    parent_list_names,
    refusal,
    source_lists,
    subtask_options,
    supplied,
    supplied_options,
    written,
)


class AdditionTests(TestCase):
    """Parity tests for battodo.mutate.Addition against add_task."""

    maxDiff = None

    @given(grammar.documents, st.data())
    def test_outcome(
        t,
        drawn: tuple[str, list[Node]],
        data: st.DataObject,
    ) -> None:
        text, _ = drawn
        list_name = data.draw(list_names())
        title = data.draw(grammar.titles)
        options = data.draw(supplied_options(ADD_OPTIONS))
        fields = supplied(options, ADD_OPTIONS)
        before = Source(source_lists(text), None, [])

        with written(before) as directory:
            expected = outcome_of(
                lambda: add_task(directory, list_name, title, fields, TODAY),
                directory,
            )

        with written(before) as directory:
            ret = outcome_of(
                lambda: added(directory, list_name, title, fields),
                directory,
            )

        t.assertEqual(ret, expected)


class SubtaskAdditionTests(TestCase):
    """Parity tests for battodo.mutate.SubtaskAddition against add_subtask."""

    maxDiff = None

    @given(grammar.documents, st.data())
    def test_outcome(
        t,
        drawn: tuple[str, list[Node]],
        data: st.DataObject,
    ) -> None:
        text, _ = drawn
        ancestries = descend(TodoDocument(text).tasks, [])
        parent = data.draw(item_selectors(ancestries))
        list_name = data.draw(parent_list_names())
        title = data.draw(grammar.titles)
        options = data.draw(subtask_options())
        fields = supplied(options, ADD_OPTIONS)
        before = Source(source_lists(text), None, [])

        with written(before) as directory:
            expected = outcome_of(
                lambda: add_subtask(
                    Task(directory, parent, TODAY),
                    list_name,
                    title,
                    fields,
                ),
                directory,
            )

        with written(before) as directory:
            ret = outcome_of(
                lambda: added_below(
                    Task(directory, parent, TODAY),
                    list_name,
                    title,
                    fields,
                ),
                directory,
            )

        t.assertEqual(ret, expected)


class UpdateTests(TestCase):
    """Parity tests for battodo.mutate.Update against update_task."""

    maxDiff = None

    @given(grammar.documents, st.data())
    def test_outcome(
        t,
        drawn: tuple[str, list[Node]],
        data: st.DataObject,
    ) -> None:
        text, _ = drawn
        ancestries = descend(TodoDocument(text).tasks, [])
        selector = data.draw(item_selectors(ancestries))
        options = data.draw(supplied_options(UPDATE_OPTIONS))
        fields = supplied(options, UPDATE_OPTIONS)
        title = data.draw(st.one_of(st.none(), grammar.titles))
        before = Source(source_lists(text), None, [])

        with written(before) as directory:
            expected = outcome_of(
                lambda: update_task(
                    Task(directory, selector, TODAY),
                    fields,
                    title=title,
                ),
                directory,
            )

        with written(before) as directory:
            ret = outcome_of(
                lambda: updated(
                    Task(directory, selector, TODAY),
                    fields,
                    title,
                ),
                directory,
            )

        t.assertEqual(ret, expected)


class CompletionTests(TestCase):
    """Parity tests for battodo.mutate.Completion against complete."""

    maxDiff = None

    @given(grammar.documents, st.data())
    def test_outcome(
        t,
        drawn: tuple[str, list[Node]],
        data: st.DataObject,
    ) -> None:
        text, _ = drawn
        ancestries = descend(TodoDocument(text).tasks, [])
        selector = data.draw(item_selectors(ancestries))
        log = data.draw(logs())
        before = Source(source_lists(text), log, [])

        with written(before) as directory:
            expected = outcome_of(
                lambda: complete(Task(directory, selector, TODAY)),
                directory,
            )

        with written(before) as directory:
            ret = outcome_of(
                lambda: completed(Task(directory, selector, TODAY)),
                directory,
            )

        t.assertEqual(ret, expected)


class ScratchTests(TestCase):
    """Parity tests for battodo.mutate.Scratch against scratch."""

    maxDiff = None

    @given(grammar.documents, st.data())
    def test_outcome(
        t,
        drawn: tuple[str, list[Node]],
        data: st.DataObject,
    ) -> None:
        text, _ = drawn
        ancestries = descend(TodoDocument(text).tasks, [])
        selector = data.draw(item_selectors(ancestries))
        log = data.draw(logs())
        before = Source(source_lists(text), log, [])

        with written(before) as directory:
            expected = outcome_of(
                lambda: scratch(Task(directory, selector, TODAY)),
                directory,
            )

        with written(before) as directory:
            ret = outcome_of(
                lambda: scratched(Task(directory, selector, TODAY)),
                directory,
            )

        t.assertEqual(ret, expected)


class BackfillTests(TestCase):
    """Parity tests for battodo.mutate.Backfill.

    The reference is backfill_all.
    """

    maxDiff = None

    @given(grammar.documents)
    def test_outcome(t, drawn: tuple[str, list[Node]]) -> None:
        text, _ = drawn
        before = Source(source_lists(text), None, [])

        with written(before) as directory:
            expected = outcome_of(
                lambda: backfill_all(directory, TODAY),
                directory,
            )

        with written(before) as directory:
            ret = outcome_of(lambda: backfilled(directory), directory)

        t.assertEqual(ret, expected)


def outcome_of(write: Callable[[], object], directory: Path) -> Any:
    """What `write` answers and leaves in `directory`, canonical."""
    with patch(f'{MUTATE}.new_task_id', autospec=True) as new_task_id:
        new_task_id.side_effect = new_ids()
        try:
            answer = repr(write())
        except (ListError, SelectionError, ValueError) as error:
            answer = refusal(error)
    named = answer.replace(str(directory), SOURCE)
    after = held(directory)
    return canonical(Outcome(named, after))


def added(
    directory: Path,
    list_name: str,
    title: str,
    fields: dict[str, str],
) -> tuple[Path, str]:
    """The new task written out: the list it went to, and its line."""
    addition = Addition(directory, list_name, title, fields, TODAY)
    recorded(addition)
    return addition.path, addition.entry


def added_below(
    parent: Task,
    list_name: str,
    title: str,
    fields: dict[str, str],
) -> tuple[Path, str]:
    """The new subtask written out: the list it went to, and its line."""
    addition = SubtaskAddition(parent, list_name, title, fields)
    recorded(addition)
    return addition.path, addition.entry


def updated(
    task: Task,
    fields: dict[str, str],
    title: str | None,
) -> tuple[Path, str]:
    """The update written out: the list it went to, and the line."""
    update = Update(task, fields, title)
    recorded(update)
    return update.path, update.entry


def completed(task: Task) -> list[str]:
    """The completion written out, and its log entries."""
    completion = Completion(task)
    recorded(completion)
    return completion.entries


def scratched(task: Task) -> list[str]:
    """The scratch written out, and its log entries."""
    dropped = Scratch(task)
    recorded(dropped)
    return dropped.entries


def backfilled(directory: Path) -> dict[str, list[str]]:
    """Every backfilled list written out, its stamped titles by name."""
    lists = Backfill(directory, TODAY).lists
    for each in lists:
        recorded(each)
    return {
        each.path.name: [task.title for task in each.tasks] for each in lists
    }


def recorded(change: Any) -> None:
    """Write `change` out: its list, its log entries, its events.

    Every value is read before the first write, as the lib entry points
    read them.
    """
    text, entries, events = change.text, change.entries, change.events
    change.path.write_text(text)
    CompletedLog(change.source).append(entries)
    journal = Journal(change.source)
    for event in events:
        journal.append(
            event.type,
            event.stream,
            event.payload,
            actor='agent',
            source_file=change.path.name,
        )
