"""Property tests for the list writes, driven by Hypothesis.

Each case writes a source drawn from the schema grammar, runs one write
entry point of `battodo.lib` on it, and asserts the answer and what the
source holds after the write: the list files, the completed log and the
journal. The expected outcome derives from the drawn source and the
clock, never from the code under test. The cases began as the mutate
slice's oracle and outlived it (R4).

A new task id is random, so each case draws new ids from a stand-in,
and the two outcomes compare up to a renaming of the new ids.
"""

import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from itertools import count
from json import dumps, loads
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, NamedTuple
from unittest import TestCase
from unittest.mock import Mock, patch

from hypothesis import given
from hypothesis import strategies as st

from battodo.conf import TZ
from battodo.journal import Journal
from battodo.lib import (
    add_item,
    backfill_items,
    complete_item,
    scratch_item,
    update_item,
)
from battodo.mutate import ListError
from battodo.parser import OPEN_HEADING, TaskNode, TodoDocument, parse_date
from battodo.repeat import next_due
from battodo.selector import SelectionError

from .item_test import item_selectors
from .strategies import NEARBY, TODAY, Node, grammar
from .task_test import LIST_FILE, Answer, descend, outcome

# The clock every write runs at. Its day is TODAY.
NOW = datetime(2026, 8, 5, 10, 30, tzinfo=TZ)
# A second list with an empty open section: an add may target it, and
# no selector reaches a task in it.
OTHER_FILE = 'b-list.md'
OTHER = '# Another list\n\n## Open\n'
LOG_FILE = 'completed.md'
# Stands in for the source directory, which an answer may name.
SOURCE = '<source>'
# The module that draws new ids.
MUTATE = 'battodo.mutate'
# A new id as the stand-in draws it. No drawn text holds one: a title
# holds no bracket, and a drawn field value is shorter.
NEW_ID = 'fresh[{:04}'
NEW_ID_RE = re.compile(r'fresh\[\d{4,}')
# The event fields that differ on every run.
VOLATILE = frozenset({'event_id', 'occurred_at', 'recorded_at'})
# The errors a write refuses with, before it writes anything.
REFUSALS = (ListError, SelectionError, ValueError)
# The options a write reads, by the field each supplies, in the order
# the write passes them on.
ADD_OPTIONS = {
    'P': 'priority',
    'LOE': 'loe',
    'DUE': 'due',
    'REPEAT': 'repeat',
    'TAGS': 'tags',
}
UPDATE_OPTIONS = {'P': 'priority', 'DUE': 'due', 'TAGS': 'tags'}
SUBTASK_OPTIONS = {'LOE': 'loe', 'DUE': 'due', 'TAGS': 'tags'}
# SCHEMA.md's field order, which an add and a log entry write in.
SCHEMA_FIELDS = ('P', 'LOE', 'DUE', 'REPEAT', 'TAGS')
LOE_VALUES = ('1', '2', '3', '5', '8')
# The fields only a top-level task carries.
ROOT_FIELDS = ('P', 'REPEAT')
# The indent each level of the schema adds.
INDENT = '  '


class AddItemTests(TestCase):
    """Property tests for battodo.lib.add_item."""

    maxDiff = None

    @given(grammar.documents, st.data())
    def test_task(
        t,
        drawn: tuple[str, list[Node]],
        data: st.DataObject,
    ) -> None:
        text, _ = drawn
        list_name = data.draw(list_names())
        title = data.draw(grammar.titles)
        options = data.draw(supplied_options(ADD_OPTIONS))
        before = Source(source_lists(text), None, [])
        expected = foreseen(added, before, list_name, title, options)

        with written(before) as directory:
            conf = configuration(
                directory,
                list=list_name,
                title=title,
                **options,
            )
            ret = observed(add_item, conf, directory)

        t.assertEqual(ret, expected)

    @given(grammar.documents, st.data())
    def test_subtask(
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
        before = Source(source_lists(text), None, [])
        found = outcome(text, ancestries, parent)
        expected = foreseen(
            added_below,
            before,
            found,
            parent,
            list_name,
            title,
            options,
        )

        with written(before) as directory:
            conf = configuration(
                directory,
                list=list_name,
                title=title,
                parent=parent,
                **options,
            )
            ret = observed(add_item, conf, directory)

        t.assertEqual(ret, expected)


class UpdateItemTests(TestCase):
    """Property tests for battodo.lib.update_item."""

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
        title = data.draw(st.one_of(st.none(), grammar.titles))
        named = options if title is None else {**options, 'title': title}
        before = Source(source_lists(text), None, [])
        found = outcome(text, ancestries, selector)
        expected = foreseen(updated, before, found, title, options)

        with written(before) as directory:
            conf = configuration(directory, selector=selector, **named)
            ret = observed(update_item, conf, directory)

        t.assertEqual(ret, expected)


class CompleteItemTests(TestCase):
    """Property tests for battodo.lib.complete_item."""

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
        found = outcome(text, ancestries, selector)
        expected = foreseen(completed, before, found)

        with written(before) as directory:
            conf = configuration(directory, selector=selector)
            ret = observed(complete_item, conf, directory)

        t.assertEqual(ret, expected)


class ScratchItemTests(TestCase):
    """Property tests for battodo.lib.scratch_item."""

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
        found = outcome(text, ancestries, selector)
        expected = foreseen(scratched, before, found)

        with written(before) as directory:
            conf = configuration(directory, selector=selector)
            ret = observed(scratch_item, conf, directory)

        t.assertEqual(ret, expected)


class BackfillItemsTests(TestCase):
    """Property tests for battodo.lib.backfill_items."""

    maxDiff = None

    @given(grammar.documents)
    def test_outcome(t, drawn: tuple[str, list[Node]]) -> None:
        text, _ = drawn
        before = Source(source_lists(text), None, [])
        expected = foreseen(backfilled, before)

        with written(before) as directory:
            conf = configuration(directory)
            ret = observed(backfill_items, conf, directory)

        t.assertEqual(ret, expected)


def list_names() -> st.SearchStrategy[str]:
    """A list the source holds, or a name no list need carry."""
    return st.one_of(st.sampled_from(['a-list', 'b-list']), grammar.titles)


def supplied_options(
    table: dict[str, str],
) -> st.SearchStrategy[dict[str, str]]:
    """Each option `table` names, left off or given a drawn value.

    Half the options are left off.
    """
    drawn = {
        option: either(st.none(), option_values(field))
        for field, option in table.items()
    }
    return st.fixed_dictionaries(drawn).map(given_options)


class Source(NamedTuple):
    """What a source directory holds: lists, completed log, events."""

    lists: dict[str, str]
    log: str | None
    events: list[dict[str, Any]]


def source_lists(text: str) -> dict[str, str]:
    """The drawn list beside a list with an empty open section."""
    return {LIST_FILE: text, OTHER_FILE: OTHER}


def foreseen(
    model: Callable[..., 'Outcome'],
    before: Source,
    *args: Any,
) -> Any:
    """The outcome `model` derives, in canonical form.

    A refused write answers with the error and leaves `before` as it
    was.
    """
    try:
        found = model(before, *args)
    except REFUSALS as error:
        found = Outcome(refusal(error), before)
    return canonical(found)


def added(
    before: Source,
    list_name: str,
    title: str,
    options: dict[str, str],
) -> 'Outcome':
    """A new top-level task, last in the open section of its list.

    It carries the supplied fields in SCHEMA.md order, then its add
    date and a new id.
    """
    name = list_file(before, list_name)
    values = checked(supplied(options, ADD_OPTIONS))
    if 'REPEAT' in values:
        next_due(values['REPEAT'], TODAY)
    fields = {
        **ordered(values),
        'ADDED': TODAY.isoformat(),
        'ID': next(new_ids()),
    }
    doc = TodoDocument(before.lists[name])
    index = doc.append_open(f'- [ ] {title}')
    doc.set_fields(index, fields)
    entry = doc.lines[index]
    payload = addition(entry, fields)
    event = Appended('TaskAdded', f'task/{fields["ID"]}', payload, name)
    lists = {**before.lists, name: doc.text}
    after = Source(lists, before.log, journal([event]))
    return Outcome(f'{entry}\n{SOURCE}/{name}', after)


@contextmanager
def written(before: Source) -> Iterator[Path]:
    """A source directory holding the lists and the log of `before`."""
    with TemporaryDirectory() as tmp:
        directory = Path(tmp)
        for name, text in before.lists.items():
            (directory / name).write_text(text, encoding='utf-8')
        if before.log is not None:
            (directory / LOG_FILE).write_text(before.log, encoding='utf-8')
        yield directory


def configuration(directory: Path, **options: str) -> Mock:
    """A resolved configuration carrying `options` and nothing else.

    An option the user left off is absent, as batconf leaves it.
    """
    conf = Mock(spec=['view', *options])
    conf.view = Mock(spec=['source_dir'])
    conf.view.source_dir = str(directory)
    for name, value in options.items():
        setattr(conf, name, value)
    return conf


def observed(
    write: Callable[[Mock, datetime], str],
    conf: Mock,
    directory: Path,
) -> Any:
    """What `write` answers and leaves in `directory`, canonical."""
    with patch(f'{MUTATE}.new_task_id', autospec=True) as new_task_id:
        new_task_id.side_effect = new_ids()
        try:
            answer = write(conf, NOW)
        except REFUSALS as error:
            answer = refusal(error)
    named = answer.replace(str(directory), SOURCE)
    after = held(directory)
    return canonical(Outcome(named, after))


def parent_list_names() -> st.SearchStrategy[str]:
    """Most draws name the list that holds every drawn task."""
    return either(st.just(Path(LIST_FILE).stem), list_names())


def subtask_options() -> st.SearchStrategy[dict[str, str]]:
    """The options of a subtask add.

    One draw in four may offer a field only a top-level task carries.
    """
    child = supplied_options(SUBTASK_OPTIONS)
    return either(child, either(child, supplied_options(ADD_OPTIONS)))


def added_below(
    before: Source,
    found: Answer,
    parent: str,
    list_name: str,
    title: str,
    options: dict[str, str],
) -> 'Outcome':
    """A new subtask, last in its parent's block, one level deeper.

    It carries the supplied fields in SCHEMA.md order, then a new id. A
    parent with no id is stamped first, on an event of its own.
    """
    name = list_file(before, list_name)
    fields = supplied(options, ADD_OPTIONS)
    refuse_root_fields(fields)
    values = checked(fields)
    text, ancestry = reached(found)
    if name != LIST_FILE:
        raise ValueError(f'{parent!r} names a task in {LIST_FILE}, not {name}')
    node = ancestry[-1]
    refuse_checklist_item(node)
    new = new_ids()
    stamped = node.task_id is None
    parent_id = node.task_id or next(new)
    child_fields = {**ordered(values), 'ID': next(new)}
    doc = TodoDocument(text)
    if stamped:
        doc.set_field(node.raw_index, 'ID', parent_id)
    index = max(node.block) + 1
    indent = ' ' * (node.indent + len(INDENT))
    doc.insert(index, f'{indent}- [ ] {title}')
    doc.set_fields(index, child_fields)
    entry = doc.lines[index]
    events = []
    if stamped:
        stamp = {
            'delta': {'ID': [None, parent_id]},
            'snapshot': snapshot(node),
        }
        events.append(
            Appended('TaskUpdated', f'task/{parent_id}', stamp, LIST_FILE)
        )
    child = {**addition(entry, child_fields), 'parent': parent_id}
    child_stream = f'task/{child_fields["ID"]}'
    events.append(Appended('TaskAdded', child_stream, child, LIST_FILE))
    lists = {**before.lists, LIST_FILE: doc.text}
    after = Source(lists, before.log, journal(events))
    return Outcome(f'{entry}\n{SOURCE}/{LIST_FILE}', after)


def updated(
    before: Source,
    found: Answer,
    title: str | None,
    options: dict[str, str],
) -> 'Outcome':
    """The task with the named fields and title written over its own.

    A task with no id is given one.
    """
    fields = supplied(options, UPDATE_OPTIONS)
    if not fields and title is None:
        raise ValueError('nothing to update: name a field or a title')
    values = checked(fields)
    text, ancestry = reached(found)
    node = ancestry[-1]
    refuse_checklist_item(node)
    nested = len(ancestry) > 1
    if nested:
        refuse_root_fields(fields)
    task_id = node.task_id or next(new_ids())
    written_fields = dict(values)
    if not node.task_id:
        written_fields['ID'] = task_id
    doc = TodoDocument(text)
    doc.set_fields(node.raw_index, written_fields)
    if title is not None:
        doc.set_title(node.raw_index, title)
    entry = doc.lines[node.raw_index]
    delta = {
        field: [node.fields.get(field), value]
        for field, value in written_fields.items()
    }
    if title is not None:
        delta['title'] = [node.title, title]
    payload: dict[str, Any] = {'delta': delta, 'snapshot': snapshot(node)}
    if nested:
        payload['ancestry'] = path_of(ancestry)
    event = Appended('TaskUpdated', f'task/{task_id}', payload, LIST_FILE)
    lists = {**before.lists, LIST_FILE: doc.text}
    after = Source(lists, before.log, journal([event]))
    return Outcome(f'{entry}\n{SOURCE}/{LIST_FILE}', after)


def logs() -> st.SearchStrategy[str | None]:
    """A completed log as a write finds it.

    Absent, empty, or a heading with or without its newline.
    """
    heading = '# Completed Tasks'
    return st.sampled_from([None, '', f'{heading}\n', heading])


def completed(before: Source, found: Answer) -> 'Outcome':
    """The task checked off, logged and journaled, per SCHEMA.md.

    Completing the last open child completes its parent. A finished
    top-level task loses its block, unless it repeats: then it stays
    with a new due date, and only its children go.
    """
    text, ancestry = reached(found)
    ancestries = cascade(ancestry)
    root = ancestry[0]
    root_done = len(ancestries[-1]) == 1
    repeats = root_done and bool(root.repeat)
    rescheduled = next_due(root.repeat or '', TODAY) if repeats else None
    ids = stream_ids(ancestries)
    doc = TodoDocument(text)
    if rescheduled is not None:
        doc.set_field(root.raw_index, 'DUE', rescheduled.isoformat())
        doc.set_field(root.raw_index, 'ID', ids[root.raw_index])
    if root_done:
        kept = {root.raw_index, *root.note_indices} if repeats else set()
        doc.drop(root.block - kept)
    else:
        for index, task_id in ids.items():
            doc.set_field(index, 'ID', task_id)
        for each in ancestries:
            doc.mark_done(each[-1].raw_index)
    entries = [
        log_entry(ancestry, 'DONE')
        for ancestry in ancestries
            if not is_checklist_item(ancestry[-1])
    ]  # fmt: skip
    events = []
    for each in ancestries:
        node = each[-1]
        delta: dict[str, Any] = {'done': [False, True]}
        if node is root and rescheduled is not None:
            delta['DUE'] = [root.due, rescheduled.isoformat()]
        payload = {
            'delta': delta,
            'snapshot': snapshot(node),
            'ancestry': path_of(each),
        }
        stream = ids[stream_task(each).raw_index]
        events.append(
            Appended('TaskCompleted', f'task/{stream}', payload, LIST_FILE)
        )
    lists = {**before.lists, LIST_FILE: doc.text}
    log = appended(before.log, entries)
    after = Source(lists, log, journal(events))
    return Outcome('\n'.join(entries) or 'checked off', after)


def scratched(before: Source, found: Answer) -> 'Outcome':
    """The task's whole block dropped, logged and journaled.

    Nothing cascades. A checklist item is not logged, and its event
    lands on the stream of the nearest ancestor that can carry an id.
    """
    text, ancestry = reached(found)
    node = ancestry[-1]
    stream = stream_task(ancestry)
    stream_id = stream.task_id or next(new_ids())
    doc = TodoDocument(text)
    if stream is not node:
        doc.set_field(stream.raw_index, 'ID', stream_id)
    doc.drop(node.block)
    entries = (
        [] if is_checklist_item(node) else [log_entry(ancestry, 'SCRATCHED')]
    )
    payload = {
        'delta': {'removed': [False, True]},
        'snapshot': snapshot(node),
        'ancestry': path_of(ancestry),
    }
    event = Appended('TaskScratched', f'task/{stream_id}', payload, LIST_FILE)
    lists = {**before.lists, LIST_FILE: doc.text}
    log = appended(before.log, entries)
    after = Source(lists, log, journal([event]))
    return Outcome('\n'.join(entries) or 'dropped', after)


def backfilled(before: Source) -> 'Outcome':
    """Every open top-level task with no add date, stamped with TODAY.

    A task whose due date does not read is left alone. A list with
    nothing to stamp is not written.
    """
    new = new_ids()
    lists = dict(before.lists)
    stamped: dict[str, list[str]] = {}
    events = []
    for name in sorted(before.lists):
        doc = TodoDocument(before.lists[name])
        titles = []
        for task in doc.tasks:
            if not undated(task):
                continue
            task_id = task.task_id or next(new)
            doc.set_field(task.raw_index, 'ADDED', TODAY.isoformat())
            if not task.task_id:
                doc.set_field(task.raw_index, 'ID', task_id)
            titles.append(task.title)
            payload = {
                'delta': {'ADDED': [None, TODAY.isoformat()]},
                'snapshot': snapshot(task),
                'backfilled': True,
            }
            events.append(
                Appended('TaskAdded', f'task/{task_id}', payload, name)
            )
        if titles:
            lists[name] = doc.text
            stamped[name] = titles
    answer = '\n'.join(
        f'{name}: stamped {len(titles)}' for name, titles in stamped.items()
    )
    after = Source(lists, before.log, journal(events))
    return Outcome(answer or 'nothing to backfill', after)


def either(
    first: st.SearchStrategy[Any],
    second: st.SearchStrategy[Any],
) -> st.SearchStrategy[Any]:
    """A draw from `first` or from `second`, half the draws each."""
    return st.booleans().flatmap(lambda picked: first if picked else second)


def option_values(field: str) -> st.SearchStrategy[str]:
    """A value given for `field`.

    Three draws in four read as the field; the rest are any field value
    of the grammar.
    """
    readable = {
        'P': st.integers(min_value=0, max_value=130).map(str),
        'LOE': st.sampled_from(LOE_VALUES),
        'DUE': st.dates(
            min_value=TODAY - NEARBY,
            max_value=TODAY + NEARBY,
        ).map(str),
        'REPEAT': grammar.repeats,
        'TAGS': grammar.field_values,
    }
    reads = readable[field]
    return either(reads, either(reads, grammar.field_values))


def given_options(options: dict[str, str | None]) -> dict[str, str]:
    """The options a value was given for."""
    return {
        option: value
        for option, value in options.items()
            if value is not None
    }  # fmt: skip


class Outcome(NamedTuple):
    """What a write answers, and what its source holds after it."""

    answer: str
    source: Source


def refusal(error: Exception) -> str:
    """The answer a refused write gives: the error's type and text."""
    return f'{type(error).__name__}: {error}'


def canonical(found: Outcome) -> Any:
    """`found` as JSON data, its new ids renumbered in order of use."""
    text = dumps(found, sort_keys=True)
    order: dict[str, int] = {}

    def renumbered(new_id: re.Match[str]) -> str:
        number = order.setdefault(new_id.group(), len(order) + 1)
        return NEW_ID.format(number)

    return loads(NEW_ID_RE.sub(renumbered, text))


def list_file(before: Source, list_name: str) -> str:
    """The file of the list `list_name` names.

    Raises
    ------
    ListError
        No list in the source carries that name.
    """
    name = f'{list_name}.md'
    if name not in before.lists:
        stems = ', '.join(Path(file).stem for file in sorted(before.lists))
        raise ListError(
            f'no list named {list_name!r} in {SOURCE}; available: {stems}'
        )
    return name


def checked(fields: dict[str, str]) -> dict[str, str]:
    """The fields as written: each readable, a due date in ISO form.

    Raises
    ------
    ValueError
        A `P`, `LOE` or `DUE` does not read, checked in that order.
    """
    priority = fields.get('P')
    if priority is not None and not priority.isdigit():
        raise ValueError(f'P must be a whole number, not {priority!r}')
    loe = fields.get('LOE')
    if loe is not None and loe not in LOE_VALUES:
        raise ValueError(f'LOE must be one of 1, 2, 3, 5, 8, not {loe!r}')
    due = fields.get('DUE')
    if due is None:
        return dict(fields)
    day = parse_date(due)
    if day is None:
        raise ValueError(f'DUE must be an ISO date, not {due!r}')
    return {**fields, 'DUE': day.isoformat()}


def supplied(options: dict[str, str], table: dict[str, str]) -> dict[str, str]:
    """The fields the supplied options carry, in the order of `table`."""
    return {
        field: options[option]
        for field, option in table.items()
            if option in options
    }  # fmt: skip


def ordered(fields: dict[str, str]) -> dict[str, str]:
    """The fields SCHEMA.md names, in its order."""
    return {
        field: fields[field]
        for field in SCHEMA_FIELDS
            if field in fields
    }  # fmt: skip


def new_ids() -> Iterator[str]:
    """New ids in a form no drawn text holds, numbered from one."""
    return (NEW_ID.format(number) for number in count(1))


def addition(entry: str, fields: dict[str, str]) -> dict[str, Any]:
    """The payload of a new task line: each field against nothing.

    The snapshot is the line as the parser reads it back.
    """
    task = TodoDocument(f'{OPEN_HEADING}\n{entry}').tasks[0]
    return {
        'delta': {field: [None, value] for field, value in fields.items()},
        'snapshot': snapshot(task),
    }


class Appended(NamedTuple):
    """One event a write appends: its type, stream, payload and file."""

    type: str
    stream: str
    payload: dict[str, Any]
    file: str


def journal(appended_events: list[Appended]) -> list[dict[str, Any]]:
    """The events as the journal records them, numbered from one.

    Each event also counts its place in its own stream.
    """
    events: list[dict[str, Any]] = []
    for seq, event in enumerate(appended_events, start=1):
        prior = [
            found
            for found in events
                if found['stream_id'] == event.stream
        ]  # fmt: skip
        events.append(
            {
                'seq': seq,
                'stream_id': event.stream,
                'stream_seq': len(prior) + 1,
                'type': event.type,
                'schema_version': 1,
                'metadata': {'actor': 'agent', 'source_file': event.file},
                'payload': event.payload,
            }
        )
    return events


def held(directory: Path) -> Source:
    """What `directory` holds: its lists, its log, its journal events."""
    lists = {
        path.name: path.read_text(encoding='utf-8')
        for path in sorted(directory.glob('*.md'))
            if path.name != LOG_FILE
    }  # fmt: skip
    log_path = directory / LOG_FILE
    log = log_path.read_text(encoding='utf-8') if log_path.exists() else None
    events = [recorded(event) for event in Journal(directory).events]
    return Source(lists, log, events)


def refuse_root_fields(fields: dict[str, str]) -> None:
    """Refuse a field only a top-level task carries.

    Raises
    ------
    ValueError
        `fields` names one.
    """
    for field in ROOT_FIELDS:
        if field in fields:
            raise ValueError(
                f'{field} belongs to the top-level task, not to a subtask'
            )


def reached(found: Answer) -> tuple[str, list[TaskNode]]:
    """The list text and the ancestry of the task a selector reached.

    Raises
    ------
    SelectionError
        The selector reached no open task, or several.
    """
    if isinstance(found, str):
        raise SelectionError(found)
    _, text, ancestry = found
    return text, ancestry


def refuse_checklist_item(task: TaskNode) -> None:
    """Refuse a checklist item, which a field would promote.

    Raises
    ------
    ValueError
        `task` is a checklist item.
    """
    if is_checklist_item(task):
        raise ValueError(
            f'{task.title!r} is a checklist item: a field written to it '
            'would promote it to a subtask'
        )


def snapshot(task: TaskNode) -> dict[str, Any]:
    """The task as the file states it before the write."""
    return {'title': task.title, 'done': task.done, 'fields': task.fields}


def path_of(ancestry: list[TaskNode]) -> str:
    """The `Parent > Child` path of the last task in `ancestry`."""
    return ' > '.join(task.title for task in ancestry)


def cascade(ancestry: list[TaskNode]) -> list[list[TaskNode]]:
    """The target's ancestry, then each one its completion finishes.

    A parent finishes when no other child of it is open. Deepest first.
    """
    found = [ancestry]
    for depth in range(len(ancestry) - 2, -1, -1):
        parent, child = ancestry[depth], ancestry[depth + 1]
        open_siblings = [
            sibling
            for sibling in parent.children
                if not sibling.done and sibling is not child
        ]  # fmt: skip
        if open_siblings:
            break
        found.append(ancestry[: depth + 1])
    return found


def stream_ids(ancestries: list[list[TaskNode]]) -> dict[int, str]:
    """The id of each stream the ancestries land on, by its line.

    A stream task with no id takes a new one, once.
    """
    ids: dict[int, str] = {}
    new = new_ids()
    for ancestry in ancestries:
        stream = stream_task(ancestry)
        if stream.raw_index not in ids:
            ids[stream.raw_index] = stream.task_id or next(new)
    return ids


def log_entry(ancestry: list[TaskNode], status: str) -> str:
    """One completed-log record: the day, list, status, path, fields."""
    task = ancestry[-1]
    fields = ''.join(
        f' [{field}:{task.fields[field]}]'
        for field in SCHEMA_FIELDS
            if field in task.fields
    )  # fmt: skip
    category = Path(LIST_FILE).stem
    return f'{TODAY} | {category} | {status} | {path_of(ancestry)}{fields}'


def is_checklist_item(task: TaskNode) -> bool:
    """A child that carries no field."""
    return bool(task.indent) and not task.fields


def stream_task(ancestry: list[TaskNode]) -> TaskNode:
    """The nearest task in `ancestry`, from the target up, with fields.

    A top-level task always qualifies.
    """
    return next(
        task
        for task in reversed(ancestry)
            if not is_checklist_item(task)
    )  # fmt: skip


def appended(log: str | None, entries: list[str]) -> str | None:
    """The completed log with `entries` after it.

    A log that ends mid-line gains a newline first. With no entries the
    log is left alone, absent or not.
    """
    if not entries:
        return log
    existing = log or ''
    lead = '\n' if existing and not existing.endswith('\n') else ''
    joined = '\n'.join(entries)
    return f'{existing}{lead}{joined}\n'


def undated(task: TaskNode) -> bool:
    """An open top-level task with no add date, whose due date reads."""
    if task.done or task.indent or task.added:
        return False
    due = task.fields.get('DUE')
    return due is None or parse_date(due) is not None


def recorded(event: dict[str, Any]) -> dict[str, Any]:
    """The event without the fields that differ on every run."""
    return {
        name: value
        for name, value in event.items()
            if name not in VOLATILE
    }  # fmt: skip
