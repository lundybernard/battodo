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
from functools import cache
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
    annotate_item,
    backfill_items,
    complete_item,
    scratch_item,
    update_item,
)
from battodo.mutate import ListError, SuppliedAttributes
from battodo.parser import (
    CHECKBOX_RE,
    OPEN_HEADING,
    TaskNode,
    TodoDocument,
    parse_date,
)
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
# How far a description line indents past its task line.
DESCRIPTION_INDENT = ' ' * 6
# Description lines the parser reads back as something else.
REFUSED_LINES = (
    '',
    '   ',
    '- [ ] A task line',
    '  - [x] A done task line',
    '## A heading',
    '<!-- A comment -->',
    'A line\rbroken',
)
# An attribute key, and the comma-then-key that ends a segment.
ATTRIBUTE_KEY = r'[a-z][a-z0-9_]*'
SEPARATOR_RE = re.compile(rf',[ \t]*{ATTRIBUTE_KEY}=')


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
        title = data.draw(supplied_titles())
        options = data.draw(supplied_options(ADD_OPTIONS))
        description = data.draw(supplied_descriptions())
        named = described(options, description)
        given = data.draw(supplied_attributes())
        before = Source(source_lists(text), None, [])
        expected = foreseen(
            added,
            before,
            list_name,
            title,
            options,
            description,
            given,
        )

        with written(before) as directory:
            conf = configuration(directory)
            ret = observed(
                add_item,
                conf,
                directory,
                list_name=list_name,
                title=title,
                **named,
                attrs=given.text,
                note=given.note,
            )

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
        title = data.draw(supplied_titles())
        options = data.draw(subtask_options())
        description = data.draw(supplied_descriptions())
        named = described(options, description)
        given = data.draw(supplied_attributes())
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
            description,
            given,
        )

        with written(before) as directory:
            conf = configuration(directory)
            ret = observed(
                add_item,
                conf,
                directory,
                list_name=list_name,
                title=title,
                parent=parent,
                **named,
                attrs=given.text,
                note=given.note,
            )

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
        title = data.draw(st.one_of(st.none(), supplied_titles()))
        description = data.draw(supplied_descriptions())
        titled = options if title is None else {**options, 'title': title}
        named = described(titled, description)
        given = data.draw(supplied_attributes())
        before = Source(source_lists(text), None, [])
        found = outcome(text, ancestries, selector)
        expected = foreseen(
            updated,
            before,
            found,
            title,
            options,
            description,
            given,
        )

        with written(before) as directory:
            conf = configuration(directory)
            ret = observed(
                update_item,
                conf,
                directory,
                selector=selector,
                **named,
                attrs=given.text,
                note=given.note,
            )

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
        given = data.draw(supplied_attributes())
        before = Source(source_lists(text), log, [])
        found = outcome(text, ancestries, selector)
        expected = foreseen(completed, before, found, given)

        with written(before) as directory:
            conf = configuration(directory)
            ret = observed(
                complete_item,
                conf,
                directory,
                selector=selector,
                attrs=given.text,
                note=given.note,
            )

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
        given = data.draw(supplied_attributes())
        before = Source(source_lists(text), log, [])
        found = outcome(text, ancestries, selector)
        expected = foreseen(scratched, before, found, given)

        with written(before) as directory:
            conf = configuration(directory)
            ret = observed(
                scratch_item,
                conf,
                directory,
                selector=selector,
                attrs=given.text,
                note=given.note,
            )

        t.assertEqual(ret, expected)


class AnnotateItemTests(TestCase):
    """Property tests for battodo.lib.annotate_item."""

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
        given = data.draw(note_inputs())
        before = Source(source_lists(text), log, [])
        found = outcome(text, ancestries, selector)
        expected = foreseen(annotated, before, found, given)

        with written(before) as directory:
            conf = configuration(directory)
            ret = observed(
                annotate_item,
                conf,
                directory,
                selector=selector,
                text=given.note,
                attrs=given.text,
            )

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


class SuppliedAttributesTests(TestCase):
    """Property tests for battodo.mutate.SuppliedAttributes."""

    maxDiff = None

    @given(st.data())
    def test_checked(t, data: st.DataObject) -> None:
        attrs = data.draw(attribute_maps())
        note = data.draw(st.one_of(st.none(), attribute_values()))
        text = ', '.join(f'{key}={value}' for key, value in attrs.items())
        expected = attrs if note is None else {**attrs, 'note': note}

        ret = SuppliedAttributes(text or None, note).checked

        # Every value comes back whole, in the order given.
        t.assertEqual(list(ret.items()), list(expected.items()))


def list_names() -> st.SearchStrategy[str]:
    """A list the source holds, or a name no list need carry."""
    return st.one_of(st.sampled_from(['a-list', 'b-list']), grammar.titles)


def supplied_titles() -> st.SearchStrategy[str]:
    """A title a caller supplies.

    One draw in four breaks the title across a line feed, a carriage
    return, or both.
    """
    broken = st.tuples(
        grammar.titles,
        st.sampled_from(['\n', '\r', '\r\n']),
        grammar.titles,
    ).map(''.join)
    return either(grammar.titles, either(grammar.titles, broken))


def attribute_maps() -> st.SearchStrategy[dict[str, str]]:
    """Up to four attributes, none of them keyed `note`."""
    keys = st.from_regex(ATTRIBUTE_KEY, fullmatch=True).filter(
        lambda key: key != 'note'
    )
    return st.dictionaries(keys, attribute_values(), max_size=4)


def attribute_values() -> st.SearchStrategy[str]:
    """A value on one line, rich in commas, `=` and spaces.

    A comma followed by a key and `=` ends a segment by design, so no
    value holds one.
    """
    text = st.text(
        st.characters(codec='utf-8', exclude_characters='\n\r'),
        max_size=4,
    )
    pieces = st.one_of(st.sampled_from([',', '=', ', ', ' Suite 4']), text)
    values = st.lists(pieces, min_size=1, max_size=4).map(''.join)
    return values.filter(lambda value: value and separated(value))


def separated(text: str) -> bool:
    """Whether `text` holds no comma-then-key, so it stays one segment."""
    return SEPARATOR_RE.search(text) is None


# Cached: the strategy is a deep tree, and a draw is cheap only once it
# is built.
@cache
def supplied_attributes() -> st.SearchStrategy['Attributes']:
    """The attribute inputs of a write, each left off or given.

    One first segment in four, and one note in four, does not read.
    """
    first = either(
        attribute_segments(),
        either(attribute_segments(), odd_first_segments()),
    )
    segments = st.tuples(
        first,
        st.lists(attribute_segments(), max_size=2),
    ).map(lambda drawn: [drawn[0], *drawn[1]])
    notes = either(
        attribute_values(), either(attribute_values(), odd_values())
    )
    return st.builds(
        Attributes,
        st.one_of(st.none(), segments),
        st.one_of(st.none(), notes),
    )


def note_inputs() -> st.SearchStrategy['Attributes']:
    """The TEXT and `--attrs` of a note.

    Half the draws give a readable TEXT alone, so most notes reach the
    task; the rest are any attribute inputs, none at all among them.
    """
    alone = st.builds(Attributes, st.none(), attribute_values())
    return either(supplied_attributes(), alone)


def attribute_segments() -> st.SearchStrategy[str]:
    """A `key=value` segment with a key of the grammar.

    The keys repeat often, `note` among them, and one value in eight
    does not read.
    """
    keys = either(
        st.from_regex(ATTRIBUTE_KEY, fullmatch=True),
        st.sampled_from(['cost', 'note']),
    )
    odd = either(attribute_values(), odd_values())
    values = either(attribute_values(), either(attribute_values(), odd))
    return st.builds('{}={}'.format, keys, values).filter(separated)


def odd_first_segments() -> st.SearchStrategy[str]:
    """A first segment that does not read: no `=`, or an odd key.

    Only the first segment can hold one: the split takes a later
    segment from its own key.
    """
    text = st.text(
        st.characters(codec='utf-8', exclude_characters='='),
        max_size=6,
    )
    odd_keys = text.filter(lambda key: not re.fullmatch(ATTRIBUTE_KEY, key))
    keyed = st.builds('{}={}'.format, odd_keys, attribute_values())
    return st.one_of(text, keyed).filter(separated)


def odd_values() -> st.SearchStrategy[str]:
    """A value that does not read: empty, or broken across lines.

    Some breaks follow a comma and lead a key, which does not split.
    """
    breaks = ['\n', '\r', '\r\n', ',\ncost=', ',\r\nnote=']
    broken = st.tuples(
        attribute_values(),
        st.sampled_from(breaks),
        attribute_values(),
    ).map(''.join)
    return st.one_of(st.just(''), broken.filter(separated))


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


def supplied_descriptions() -> st.SearchStrategy[str | None]:
    """A description a caller supplies, or None for none supplied.

    Half the draws supply none. The rest are empty, or one to three
    lines; one draw in four of those holds a line the parser reads back
    as something else.
    """
    lines = st.lists(description_texts(), min_size=1, max_size=3)
    refused = st.tuples(lines, st.sampled_from(REFUSED_LINES), st.data())
    given = either(
        either(lines, lines),
        refused.map(with_refused_line),
    ).map('\n'.join)
    return either(st.none(), either(st.just(''), given))


def description_texts() -> st.SearchStrategy[str]:
    """One description line as a caller types it, indent and all."""
    return st.builds(
        str.__add__,
        st.sampled_from(['', ' ', '    ']),
        grammar.titles.filter(
            lambda text: not text.strip().startswith(('#', '<!--'))
        ),
    )


def with_refused_line(
    drawn: tuple[list[str], str, st.DataObject],
) -> list[str]:
    """The lines with the refused line at a drawn place among them."""
    lines, refused, data = drawn
    place = data.draw(st.integers(min_value=0, max_value=len(lines)))
    return [*lines[:place], refused, *lines[place:]]


def described(
    options: dict[str, str],
    description: str | None,
) -> dict[str, str]:
    """The options, and the description where one is supplied."""
    if description is None:
        return options
    return {**options, 'description': description}


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
    description: str | None,
    given: 'Attributes',
) -> 'Outcome':
    """A new top-level task, last in the open section of its list.

    It carries the supplied fields in SCHEMA.md order, then its add
    date and a new id. Its description lines follow it. Its event
    carries the attributes.
    """
    attrs = attributes(given)
    name = list_file(before, list_name)
    values = checked(supplied(options, ADD_OPTIONS))
    if 'REPEAT' in values:
        next_due(values['REPEAT'], TODAY)
    refuse_line_break(title)
    lines = description_lines(description or '')
    fields = {
        **ordered(values),
        'ADDED': TODAY.isoformat(),
        'ID': next(new_ids()),
    }
    doc = TodoDocument(before.lists[name])
    index = doc.append_open(f'- [ ] {title}')
    doc.set_fields(index, fields)
    describe(doc, index, '', lines)
    entry = doc.lines[index]
    payload = addition(block(doc, index, lines), fields, attrs, name)
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


def configuration(directory: Path) -> Mock:
    """A resolved configuration that names `directory` as the source."""
    conf = Mock(spec=['view'])
    conf.view = Mock(spec=['source_dir'])
    conf.view.source_dir = str(directory)
    return conf


def observed(
    write: Callable[..., str],
    conf: Mock,
    directory: Path,
    **inputs: str | None,
) -> Any:
    """What `write` answers and leaves in `directory`, canonical.

    `inputs` are the command inputs `write` takes beside `conf`.
    """
    with patch(f'{MUTATE}.new_task_id', autospec=True) as new_task_id:
        new_task_id.side_effect = new_ids()
        try:
            answer = write(conf, NOW, **inputs)
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
    description: str | None,
    given: 'Attributes',
) -> 'Outcome':
    """A new subtask, last in its parent's block, one level deeper.

    It carries the supplied fields in SCHEMA.md order, then a new id,
    and its description lines follow it. A parent with no id is stamped
    first, on an event of its own. The event of the subtask carries the
    attributes.
    """
    attrs = attributes(given)
    name = list_file(before, list_name)
    fields = supplied(options, ADD_OPTIONS)
    refuse_root_fields(fields)
    values = checked(fields)
    text, ancestry = reached(found)
    if name != LIST_FILE:
        raise ValueError(f'{parent!r} names a task in {LIST_FILE}, not {name}')
    node = ancestry[-1]
    refuse_checklist_item(node)
    refuse_line_break(title)
    lines = description_lines(description or '')
    new = new_ids()
    stamped = not node.task_id
    parent_id = node.task_id or next(new)
    child_fields = {**ordered(values), 'ID': next(new)}
    doc = TodoDocument(text)
    if stamped:
        doc.set_field(node.raw_index, 'ID', parent_id)
    index = max(node.block) + 1
    indent = ' ' * (node.indent + len(INDENT))
    doc.insert(index, f'{indent}- [ ] {title}')
    doc.set_fields(index, child_fields)
    describe(doc, index, indent, lines)
    entry = doc.lines[index]
    events = []
    if stamped:
        stamp = {
            'delta': {'ID': [None, parent_id]},
            'snapshot': snapshot(node, LIST_FILE),
        }
        events.append(
            Appended('TaskUpdated', f'task/{parent_id}', stamp, LIST_FILE)
        )
    added_block = block(doc, index, lines)
    added_payload = addition(added_block, child_fields, attrs, LIST_FILE)
    child = {**added_payload, 'parent': parent_id}
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
    description: str | None,
    given: 'Attributes',
) -> 'Outcome':
    """The task with the named fields and title written over its own.

    A description named replaces its description lines, and an empty
    one clears them. A task with no id is given one. The event carries
    the attributes.
    """
    attrs = attributes(given)
    fields = supplied(options, UPDATE_OPTIONS)
    if not fields and title is None and description is None:
        raise ValueError(
            'nothing to update: name a field, a title or a description'
        )
    values = checked(fields)
    text, ancestry = reached(found)
    node = ancestry[-1]
    refuse_checklist_item(node)
    nested = len(ancestry) > 1
    if nested:
        refuse_root_fields(fields)
    if title is not None:
        refuse_line_break(title)
    lines = None if description is None else description_lines(description)
    task_id = node.task_id or next(new_ids())
    written_fields = dict(values)
    if not node.task_id:
        written_fields['ID'] = task_id
    doc = TodoDocument(text)
    doc.set_fields(node.raw_index, written_fields)
    if title is not None:
        doc.set_title(node.raw_index, title)
    if lines is not None:
        doc.drop(set(node.note_indices))
        indent = ' ' * node.indent
        describe(doc, node.raw_index, indent, lines)
    entry = doc.lines[node.raw_index]
    delta = {
        field: [node.fields.get(field), value]
        for field, value in written_fields.items()
    }
    if title is not None:
        delta['title'] = [node.title, title]
    if lines is not None:
        before_text = '\n'.join(node.description_lines) or None
        delta['description'] = [before_text, '\n'.join(lines) or None]
    payload: dict[str, Any] = {
        'delta': delta,
        'snapshot': snapshot(node, LIST_FILE),
    }
    if nested:
        payload['ancestry'] = path_of(ancestry)
    if attrs:
        payload['attrs'] = attrs
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


def completed(
    before: Source,
    found: Answer,
    given: 'Attributes',
) -> 'Outcome':
    """The task checked off, logged and journaled, per SCHEMA.md.

    Completing the last open child completes its parent. A finished
    top-level task loses its block, unless it repeats: then it stays
    with a new due date, and only its children go. The attributes go
    on the event of the named task, which is not a checklist item. Each
    stream task that keeps its line and gains an id is stamped first,
    on an event of its own.
    """
    attrs = attributes(given)
    text, ancestry = reached(found)
    ancestries = cascade(ancestry)
    root = ancestry[0]
    root_done = len(ancestries[-1]) == 1
    repeats = root_done and bool(root.repeat)
    rescheduled = next_due(root.repeat or '', TODAY) if repeats else None
    if attrs:
        refuse_checklist_attributes(ancestry[-1])
    ids = stream_ids(ancestries)
    streams = {
        stream_task(each).raw_index: stream_task(each) for each in ancestries
    }
    stamped: list[int] = []
    doc = TodoDocument(text)
    if rescheduled is not None:
        doc.set_field(root.raw_index, 'DUE', rescheduled.isoformat())
        doc.set_field(root.raw_index, 'ID', ids[root.raw_index])
        stamped.append(root.raw_index)
    if root_done:
        kept = {root.raw_index, *root.note_indices} if repeats else set()
        doc.drop(root.block - kept)
    else:
        for index, task_id in ids.items():
            doc.set_field(index, 'ID', task_id)
            stamped.append(index)
        for each in ancestries:
            doc.mark_done(each[-1].raw_index)
    entries = [
        log_entry(each, 'DONE', attrs if each is ancestry else None)
        for each in ancestries
            if not is_checklist_item(each[-1])
    ]  # fmt: skip
    events = [
        id_stamp(streams[index], ids[index])
        for index in stamped
            if not streams[index].task_id
    ]  # fmt: skip
    for each in ancestries:
        node = each[-1]
        delta: dict[str, Any] = {'done': [False, True]}
        if node is root and rescheduled is not None:
            delta['DUE'] = [root.due, rescheduled.isoformat()]
        payload: dict[str, Any] = {
            'delta': delta,
            'snapshot': snapshot(node, LIST_FILE),
            'ancestry': path_of(each),
            'completed_on': TODAY.isoformat(),
        }
        if is_checklist_item(node):
            payload['checklist_item'] = True
        if attrs and each is ancestry:
            payload['attrs'] = attrs
        stream = ids[stream_task(each).raw_index]
        events.append(
            Appended('TaskCompleted', f'task/{stream}', payload, LIST_FILE)
        )
    lists = {**before.lists, LIST_FILE: doc.text}
    log = appended(before.log, entries)
    after = Source(lists, log, journal(events))
    return Outcome('\n'.join(entries) or 'checked off', after)


def scratched(
    before: Source,
    found: Answer,
    given: 'Attributes',
) -> 'Outcome':
    """The task's whole block dropped, logged and journaled.

    Nothing cascades. A checklist item is not logged, and its event
    lands on the stream of the nearest ancestor that can carry an id.
    That ancestor, if it has no id, is stamped first, on an event of
    its own. The event carries the attributes; a checklist item takes
    none.
    """
    attrs = attributes(given)
    text, ancestry = reached(found)
    node = ancestry[-1]
    if attrs:
        refuse_checklist_attributes(node)
    stream = stream_task(ancestry)
    stream_id = stream.task_id or next(new_ids())
    doc = TodoDocument(text)
    if stream is not node:
        doc.set_field(stream.raw_index, 'ID', stream_id)
    doc.drop(node.block)
    entries = (
        []
        if is_checklist_item(node)
        else [log_entry(ancestry, 'SCRATCHED', attrs)]
    )
    payload: dict[str, Any] = {
        'delta': {'removed': [False, True]},
        'snapshot': snapshot(node, LIST_FILE),
        'ancestry': path_of(ancestry),
    }
    if is_checklist_item(node):
        payload['checklist_item'] = True
    if attrs:
        payload['attrs'] = attrs
    events = []
    if stream is not node and not stream.task_id:
        events.append(id_stamp(stream, stream_id))
    events.append(
        Appended('TaskScratched', f'task/{stream_id}', payload, LIST_FILE)
    )
    lists = {**before.lists, LIST_FILE: doc.text}
    log = appended(before.log, entries)
    after = Source(lists, log, journal(events))
    return Outcome('\n'.join(entries) or 'dropped', after)


def annotated(
    before: Source,
    found: Answer,
    given: 'Attributes',
) -> 'Outcome':
    """The note on the stream of the task, which changes nothing in it.

    A note that carries nothing is refused before the task is read, and
    a checklist item takes no note. A task with no id is stamped first,
    on an event of its own.
    """
    attrs = attributes(given)
    if not attrs:
        raise ValueError('nothing to note: give a note or an attribute')
    text, ancestry = reached(found)
    node = ancestry[-1]
    refuse_checklist_attributes(node)
    task_id = node.task_id or next(new_ids())
    doc = TodoDocument(text)
    events = []
    if not node.task_id:
        doc.set_field(node.raw_index, 'ID', task_id)
        stamp = {
            'delta': {'ID': [None, task_id]},
            'snapshot': snapshot(node, LIST_FILE),
        }
        events.append(
            Appended('TaskUpdated', f'task/{task_id}', stamp, LIST_FILE)
        )
    payload: dict[str, Any] = {'snapshot': snapshot(node, LIST_FILE)}
    if len(ancestry) > 1:
        payload['ancestry'] = path_of(ancestry)
    payload['attrs'] = attrs
    events.append(
        Appended('TaskAnnotated', f'task/{task_id}', payload, LIST_FILE)
    )
    entry = doc.lines[node.raw_index]
    lists = {**before.lists, LIST_FILE: doc.text}
    after = Source(lists, before.log, journal(events))
    return Outcome(f'{entry}\n{SOURCE}/{LIST_FILE}', after)


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
                'snapshot': snapshot(task, name),
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


class Attributes(NamedTuple):
    """The attribute inputs of a write, the segments not yet joined."""

    segments: list[str] | None
    note: str | None

    @property
    def text(self) -> str | None:
        """The `attrs` input: the segments joined, or None."""
        if self.segments is None:
            return None
        return ', '.join(self.segments)


def attributes(given: Attributes) -> dict[str, str]:
    """The attributes a write carries: each key against its value.

    Raises
    ------
    ValueError
        A segment holds no `=`, a key is outside the grammar, a value
        is empty or broken across lines, or a key repeats, checked in
        that order.
    """
    pairs = []
    for segment in given.segments or []:
        key, sign, value = segment.partition('=')
        if not sign:
            raise ValueError(f'attribute must read key=value, not {segment!r}')
        pairs.append((key, value))
    if given.note is not None:
        pairs.append(('note', given.note))
    found: dict[str, str] = {}
    for key, value in pairs:
        if not re.fullmatch(ATTRIBUTE_KEY, key):
            raise ValueError(
                f'attribute key must be a lowercase identifier, not {key!r}'
            )
        if not value:
            raise ValueError(f'attribute {key!r} must hold a value')
        if '\n' in value or '\r' in value:
            raise ValueError(
                f'attribute {key!r} must hold no line break, not {value!r}'
            )
        if key in found:
            raise ValueError(f'attribute {key!r} is given twice')
        found[key] = value
    return found


def refuse_checklist_attributes(task: TaskNode) -> None:
    """Refuse attributes on a checklist item.

    Raises
    ------
    ValueError
        `task` is a checklist item.
    """
    if is_checklist_item(task):
        raise ValueError('a checklist item takes no attributes')


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


def refuse_line_break(title: str) -> None:
    """Refuse a title that would end its task line.

    Raises
    ------
    ValueError
        `title` holds a line feed or a carriage return.
    """
    if '\n' in title or '\r' in title:
        raise ValueError(f'title must hold no line break, not {title!r}')


def description_lines(description: str) -> list[str]:
    """The lines of a supplied description, each stripped.

    An empty description holds none.

    Raises
    ------
    ValueError
        A line is blank, reads as a task line, a heading or a comment,
        or holds a carriage return.
    """
    if not description:
        return []
    lines = description.split('\n')
    for line in lines:
        text = line.strip()
        reason = (
            'is blank' if not text
            else 'reads as a task line' if CHECKBOX_RE.match(text)
            else 'reads as a heading' if text.startswith('## ')
            else 'reads as a comment' if text.startswith('<!--')
            else 'holds a carriage return' if '\r' in line
            else None
        )  # fmt: skip
        if reason is not None:
            raise ValueError(f'description line {line!r} {reason}')
    return [line.strip() for line in lines]


def describe(
    doc: TodoDocument,
    index: int,
    indent: str,
    lines: list[str],
) -> None:
    """Insert `lines` under the task line at `index`, which `indent` leads."""
    for offset, line in enumerate(lines, start=1):
        doc.insert(index + offset, f'{indent}{DESCRIPTION_INDENT}{line}')


def block(doc: TodoDocument, index: int, lines: list[str]) -> str:
    """The task line at `index` and the description lines under it."""
    return '\n'.join(doc.lines[index : index + 1 + len(lines)])


def ordered(fields: dict[str, str]) -> dict[str, str]:
    """The fields SCHEMA.md names, in its order."""
    return {
        field: fields[field]
        for field in SCHEMA_FIELDS
            if field in fields
    }  # fmt: skip


def id_stamp(task: TaskNode, task_id: str) -> 'Appended':
    """The `TaskUpdated` that records `task_id` given to `task`."""
    stamp = {
        'delta': {'ID': [None, task_id]},
        'snapshot': snapshot(task, LIST_FILE),
    }
    return Appended('TaskUpdated', f'task/{task_id}', stamp, LIST_FILE)


def new_ids() -> Iterator[str]:
    """New ids in a form no drawn text holds, numbered from one."""
    return (NEW_ID.format(number) for number in count(1))


def addition(
    written: str,
    fields: dict[str, str],
    attrs: dict[str, str],
    file: str,
) -> dict[str, Any]:
    """The payload of a new task in `file`: each field against nothing.

    The snapshot is the task line and its description lines as the
    parser reads them back. The attributes go in where any are given.
    """
    task = TodoDocument(f'{OPEN_HEADING}\n{written}').tasks[0]
    payload = {
        'delta': {field: [None, value] for field, value in fields.items()},
        'snapshot': snapshot(task, file),
    }
    if attrs:
        payload['attrs'] = attrs
    return payload


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


def snapshot(task: TaskNode, file: str) -> dict[str, Any]:
    """The task as `file` states it before the write, and its list.

    The list is the stem of `file`.
    """
    return {**state(task), 'list': Path(file).stem}


def state(task: TaskNode) -> dict[str, Any]:
    """The task and every task below it, as the file states them.

    Its description lines join into its description, absent when it
    has none. Its children nest in it, absent when it has none.
    """
    found: dict[str, Any] = {
        'title': task.title,
        'done': task.done,
        'fields': task.fields,
    }
    if task.description_lines:
        found['description'] = '\n'.join(task.description_lines)
    if task.children:
        found['children'] = [state(child) for child in task.children]
    return found


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


def log_entry(
    ancestry: list[TaskNode],
    status: str,
    attrs: dict[str, str] | None,
) -> str:
    """One completed-log record: the day, list, status, path, fields.

    The attributes follow as a JSON object in a block of their own.
    """
    task = ancestry[-1]
    fields = ''.join(
        f' [{field}:{task.fields[field]}]'
        for field in SCHEMA_FIELDS
            if field in task.fields
    )  # fmt: skip
    block = f' [attrs:{dumps(attrs)}]' if attrs else ''
    category = Path(LIST_FILE).stem
    path = path_of(ancestry)
    return f'{TODAY} | {category} | {status} | {path}{fields}{block}'


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
