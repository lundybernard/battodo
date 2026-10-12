"""The writes to a todo list, one object each (ADR 0004, ADR 0005).

A write object derives the new text of one list and the journal events
that record it. Its `write` method reads every value first, then writes
the list, the completed-log records and the events, so the markdown
stays authoritative while the journal accumulates history. The document
performs every line edit.

`Addition` and `SubtaskAddition` create a task. A top-level task
lands last in the `## Open` section of a named list and carries only
the fields the caller gave it, plus the `[ADDED:]` and `[ID:]` btodo
owns. A subtask lands last in its parent's block, one level deeper:
the file states the relation by indentation, and the event names the
parent by id.

`Completion` follows SCHEMA.md's completion rules: it logs the
ancestry to `completed.md`, checks the box, removes the block once all
of it is done, and reschedules a recurring task instead of removing
it. `Scratch` abandons a task: the block goes, the log records it as
SCRATCHED, and nothing cascades or reschedules. `Update` sets the
fields and the title it is given and leaves the rest of the list, or
moves a top-level task and its block to another list.
`Reopen` brings a closed task back open, named by its stream in the
journal. `Annotation` records a note on a task and changes nothing in it.
`Backfill` stamps `[ADDED:]` once on every task that lacks it, and
leaves a list with nothing to stamp unwritten, so file sync sees no
change.

A write to an existing task is built on the `Task` its caller built,
so the write edits the document that selection read.
"""

import re
from collections.abc import Sequence
from datetime import date, tzinfo
from functools import cached_property
from json import dumps
from pathlib import Path
from typing import Any, NamedTuple, Protocol

from .history import StreamSelection, TaskStream
from .journal import (
    ADDED_EVENT,
    ANNOTATED_EVENT,
    COMPLETED_EVENT,
    SCRATCHED_EVENT,
    UPDATED_EVENT,
    Journal,
    new_task_id,
)
from .lists import discover_lists
from .parser import (
    ANCESTRY_SEPARATOR,
    CHECKBOX_RE,
    DESCRIPTION_INDENT,
    OPEN_HEADING,
    SCHEMA_FIELDS,
    Ancestry,
    TaskNode,
    TodoDocument,
    parse_date,
)
from .repeat import next_due
from .selector import SelectionError
from .task import Task

COMPLETED_LOG = 'completed.md'
# Opens the attribute block that ends a completed-log record.
ATTRIBUTES_MARK = '[attrs:'
DONE_STATUS = 'DONE'
SCRATCHED_STATUS = 'SCRATCHED'
# Whom every journal event names as its actor.
ACTOR = 'agent'
LOE_VALUES = ('1', '2', '3', '5', '8')
# SCHEMA.md indents every level by two spaces.
SUBTASK_INDENT = 2
# The fields a top-level task owns. SCHEMA.md gives a subtask no `P` of
# its own, and only the root task is rescheduled, so a `[REPEAT:]` on a
# child never fires.
ROOT_ONLY_FIELDS = ('P', 'REPEAT')
# An attribute key: a letter, then letters, digits or underscores.
ATTRIBUTE_KEY = re.compile(r'[a-z][a-z0-9_]*')
# The one place `--attrs` splits: a comma, spaces or tabs, then the next
# `key=`. A line break does not split, so the value refuses it.
ATTRIBUTE_SEPARATOR = re.compile(rf',[ \t]*(?={ATTRIBUTE_KEY.pattern}=)')
# The key the text of `--note` enters the attributes under.
NOTE_KEY = 'note'


class ListError(Exception):
    """No discovered list in the source directory carries that name.

    Raised rather than creating the file: `btodo add` writes to lists
    the user already keeps, and a typo that silently spawns `wrk.md`
    hides the task instead of filing it.
    """


class Addition:
    """The add of a top-level task, last in the open section of a list.

    The line carries only the fields the caller supplied, in SCHEMA.md
    order, then the `[ADDED:]` and `[ID:]` btodo owns. An absent `P`
    means 0 to the parser, so no field is invented.
    """

    def __init__(
        self,
        source: Path,
        list_name: str,
        title: str,
        fields: dict[str, str],
        today: date,
        description: str | None = None,
        attrs: dict[str, str] | None = None,
    ) -> None:
        self.source = source
        self.list_name = list_name
        self.title = title
        self.fields = fields
        self.today = today
        self.description = description
        self.attrs = attrs

    def write(self) -> None:
        """Write the list, its log records and its events.

        Every value is read before the first write, so a refused write
        writes nothing.
        """
        text = self.text
        changes = Changeset(
            {self.path: text},
            self.entries,
            self.events,
            self.path,
            self.source,
        )
        changes.write()

    @cached_property
    def path(self) -> Path:
        """The discovered list whose filename stem is `list_name`.

        Cached: discovery reads every list in the source.

        Raises
        ------
        ListError
            No discovered list carries that stem.
        """
        return NamedList(self.source, self.list_name).path

    @property
    def text(self) -> str:
        """The list with the task in it.

        Raises
        ------
        ListError
            `list_name` names no discovered list.
        ValueError
            A supplied `P`, `LOE`, `DUE` or `REPEAT` does not read, the
            title holds a line break, or a description line is refused.
            `RepeatError`, a ValueError, covers `REPEAT`.
        """
        return self.document.text

    @property
    def document(self) -> TodoDocument:
        """The list as read, the task last in its open section.

        Its description lines go under it.
        """
        doc = TodoDocument(self.parsed.text)
        written = self.written
        title = SuppliedTitle(self.title).checked
        description_lines = self.description_lines
        doc.insert(self.index, f'- [ ] {title}')
        doc.set_fields(self.index, written)
        doc.insert_description(self.index, description_lines)
        return doc

    @cached_property
    def parsed(self) -> TodoDocument:
        """The list as read.

        Cached: one read of the file answers every property.
        """
        return TodoDocument(self.path.read_text())

    @property
    def written(self) -> dict[str, str]:
        """The fields the line carries.

        The supplied fields come first, read and in SCHEMA.md order,
        then the add date and the id.
        """
        return {
            **self.supplied.ordered,
            'ADDED': self.today.isoformat(),
            'ID': self.task_id,
        }

    @property
    def supplied(self) -> 'SuppliedFields':
        """The supplied fields, read against the add date."""
        return SuppliedFields(self.fields, self.today)

    @property
    def description_lines(self) -> list[str]:
        """The lines of the given description, read; none if none is given.

        Raises
        ------
        ValueError
            A description line is refused.
        """
        if self.description is None:
            return []
        return SuppliedDescription(self.description).lines

    @property
    def index(self) -> int:
        """Where the task lands: last in the open section."""
        return self.parsed.open_end

    @cached_property
    def task_id(self) -> str:
        """A new id. Cached: drawn at random, so every read names one."""
        return new_task_id()

    @property
    def entry(self) -> str:
        """The task line as written."""
        return self.document.lines[self.index]

    @property
    def block(self) -> str:
        """The task line and its description lines, as written."""
        end = self.index + 1 + len(self.description_lines)
        return '\n'.join(self.document.lines[self.index : end])

    @property
    def entries(self) -> list[str]:
        """None: an add logs no completed-log record."""
        return []

    @property
    def events(self) -> list['Event']:
        """One `TaskAdded`, on the stream of the new task."""
        added = AddedLine(self.block, self.written, self.path.stem, self.attrs)
        payload = added.payload
        return [Event(ADDED_EVENT, f'task/{self.task_id}', payload)]


class SubtaskAddition:
    """The add of a subtask, last in its parent's block, one level deeper.

    Indentation is the file's only statement of the relation; the
    `TaskAdded` payload names the parent by id. A parent with no `[ID:]`
    is stamped first, on an event of its own.
    """

    def __init__(
        self,
        parent: Task,
        list_name: str,
        title: str,
        fields: dict[str, str],
        description: str | None = None,
        attrs: dict[str, str] | None = None,
    ) -> None:
        self.parent = parent
        self.list_name = list_name
        self.title = title
        self.fields = fields
        self.description = description
        self.attrs = attrs

    def write(self) -> None:
        """Write the list, its log records and its events.

        Every value is read before the first write, so a refused write
        writes nothing.
        """
        text = self.text
        changes = Changeset(
            {self.path: text},
            self.entries,
            self.events,
            self.path,
            self.source,
        )
        changes.write()

    @property
    def source(self) -> Path:
        """The source directory of the parent."""
        return self.parent.source

    @cached_property
    def path(self) -> Path:
        """The discovered list whose filename stem is `list_name`.

        Cached: discovery reads every list in the source.

        Raises
        ------
        ListError
            No discovered list carries that stem.
        """
        return NamedList(self.source, self.list_name).path

    @property
    def text(self) -> str:
        """The list with the subtask in it.

        Raises
        ------
        ListError
            `list_name` names no discovered list.
        ValueError
            `fields` names a field only the top-level task carries, or a
            supplied value does not read.
        SelectionError
            The parent's selector does not name exactly one open task.
        ValueError
            The parent is a task in another list or a checklist item,
            the title holds a line break, or a description line is
            refused.
        """
        return self.document.text

    @property
    def document(self) -> TodoDocument:
        """The parent's list: the parent stamped, the subtask added.

        The subtask's description lines go under it.

        The checks run in the order `text` lists them: the list, then
        the fields, then the parent.
        """
        path, written = self.path, self.written
        if self.parent.path != path:
            raise ValueError(
                f'{self.parent.selector!r} names a task in '
                f'{self.parent.path.name}, not {path.name}'
            )
        doc = TodoDocument(self.parent.doc.text)
        if self.stamped:
            doc.set_field(self.node.raw_index, 'ID', self.parent_id)
        title = SuppliedTitle(self.title).checked
        description_lines = self.description_lines
        doc.insert(self.index, f'{self.indent}- [ ] {title}')
        doc.set_fields(self.index, written)
        doc.insert_description(self.index, description_lines)
        return doc

    @property
    def written(self) -> dict[str, str]:
        """The fields the subtask line carries.

        The supplied fields come first, read and in SCHEMA.md order,
        then the id. No `[ADDED:]` is stamped: rank reads the add date,
        and only a top-level task is ranked.

        Raises
        ------
        ValueError
            `fields` names a field only the top-level task carries, or a
            supplied value does not read.
        """
        supplied = self.supplied
        supplied.refuse_root_fields()
        return {**supplied.ordered, 'ID': self.task_id}

    @property
    def supplied(self) -> 'SuppliedFields':
        """The supplied fields, read against the day of the parent."""
        return SuppliedFields(self.fields, self.parent.today)

    @property
    def stamped(self) -> bool:
        """Whether the parent is given an id: it carries none.

        An `[ID:]` with nothing in it names no stream, so it counts as
        none.
        """
        return not self.node.task_id

    @property
    def node(self) -> TaskNode:
        """The parent as the parser reads it.

        Raises
        ------
        ValueError
            The parent is a checklist item. Any field written to one, an
            `[ID:]` included, promotes it to a subtask (SCHEMA.md).
        """
        node = self.parent.node
        node.refuse_checklist_item()
        return node

    @cached_property
    def parent_id(self) -> str:
        """The parent's id, or a new one.

        Cached: a new id is drawn at random, so every read names one.
        """
        return self.node.task_id or new_task_id()

    @property
    def description_lines(self) -> list[str]:
        """The lines of the given description, read; none if none is given.

        Raises
        ------
        ValueError
            A description line is refused.
        """
        if self.description is None:
            return []
        return SuppliedDescription(self.description).lines

    @property
    def index(self) -> int:
        """Where the subtask lands: after every line the parent owns."""
        return max(self.node.block) + 1

    @property
    def indent(self) -> str:
        """The indent of the subtask: one level deeper than the parent."""
        return ' ' * (self.node.indent + SUBTASK_INDENT)

    @cached_property
    def task_id(self) -> str:
        """A new id. Cached: drawn at random, so every read names one."""
        return new_task_id()

    @property
    def entry(self) -> str:
        """The subtask line as written."""
        return self.document.lines[self.index]

    @property
    def block(self) -> str:
        """The subtask line and its description lines, as written."""
        end = self.index + 1 + len(self.description_lines)
        return '\n'.join(self.document.lines[self.index : end])

    @property
    def entries(self) -> list[str]:
        """None: an add logs no completed-log record."""
        return []

    @property
    def events(self) -> list['Event']:
        """The parent's stamp if it has one, then one `TaskAdded`.

        The `TaskAdded` lands on the stream of the subtask, names the
        parent by id and carries the attributes.
        """
        added = AddedLine(self.block, self.written, self.path.stem, self.attrs)
        payload = {**added.payload, 'parent': self.parent_id}
        event = Event(ADDED_EVENT, f'task/{self.task_id}', payload)
        return [self.stamp, event] if self.stamped else [event]

    @property
    def stamp(self) -> 'Event':
        """The `TaskUpdated` that records the parent's new id."""
        return IdAssignment(self.node, self.parent_id, self.path.stem).event


class Update:
    """The update of a task: the named fields, title, description, list.

    Only what the update names is written; the rest of the task, and
    every other line of the file, stays as it was. A task with no `[ID:]` is
    given one, so the caller can name it by id from here on. A top-level
    task that `list_name` moves takes its whole block, last in the open
    section of that list.
    """

    def __init__(
        self,
        task: Task,
        fields: dict[str, str],
        title: str | None = None,
        description: str | None = None,
        attrs: dict[str, str] | None = None,
        list_name: str | None = None,
    ) -> None:
        self.task = task
        self.fields = fields
        self.title = title
        self.description = description
        self.attrs = attrs
        self.list_name = list_name

    def write(self) -> None:
        """Write the list, its log records and its events.

        Every value is read before the first write, so a refused write
        writes nothing.
        """
        lists = self.lists
        changes = Changeset(
            lists,
            self.entries,
            self.events,
            self.path,
            self.source,
        )
        changes.write()

    @property
    def lists(self) -> dict[Path, str]:
        """The text of each list the update writes, by its path.

        A move writes the list the task leaves and the list it joins.
        """
        text = self.text
        if not self.moved:
            return {self.task.path: text}
        return {self.task.path: text, self.path: self.joined.text}

    @property
    def source(self) -> Path:
        """The source directory of the task."""
        return self.task.source

    @cached_property
    def path(self) -> Path:
        """The list file that holds the task once it is written.

        The list `list_name` names, or else the list of the task. Cached:
        discovery reads every list in the source.

        Raises
        ------
        ListError
            `list_name` names no discovered list.
        """
        if self.list_name is None:
            return self.task.path
        return NamedList(self.source, self.list_name).path

    @property
    def moved(self) -> bool:
        """Whether the task moves to another list."""
        return self.path != self.task.path

    @property
    def text(self) -> str:
        """The list with the task rewritten, or without it once it moves.

        Raises
        ------
        ValueError
            Nothing is named to change, or a supplied value does not
            read.
        SelectionError
            The selector does not name exactly one open task.
        ValueError
            The task is a checklist item, a subtask is given a field
            only the top-level task carries or a list, the title holds
            a line break, or a description line is refused.
        ListError
            `list_name` names no discovered list.
        """
        document = self.document
        if self.moved:
            document.drop(self.rewritten.block)
        return document.text

    @property
    def document(self) -> TodoDocument:
        """The task's list, its line rewritten.

        A description given replaces the task's description lines.
        """
        written = self.written
        index = self.node.raw_index
        doc = TodoDocument(self.task.doc.text)
        doc.set_fields(index, written)
        if self.new_title is not None:
            doc.set_title(index, self.new_title)
        new_description = self.new_description
        if new_description is not None:
            doc.drop(set(self.node.note_indices))
            doc.insert_description(index, new_description.lines)
        return doc

    @property
    def rewritten(self) -> TaskNode:
        """The task as the rewritten list reads it."""
        index = self.node.raw_index
        rewritten = TodoDocument(self.document.text)
        return next(
            task
            for task in rewritten.tasks
                if task.raw_index == index
        )  # fmt: skip

    @property
    def block(self) -> list[str]:
        """Every line the rewritten task owns, in file order."""
        lines = self.document.lines
        return [lines[index] for index in sorted(self.rewritten.block)]

    @property
    def joined(self) -> TodoDocument:
        """The list the task moves to, its block last in the open section.

        Raises
        ------
        ListError
            `list_name` names no discovered list.
        """
        doc = TodoDocument(self.path.read_text())
        index = doc.open_end
        for offset, line in enumerate(self.block):
            doc.insert(index + offset, line)
        return doc

    @property
    def written(self) -> dict[str, str]:
        """The fields written: the named ones, then an id if none."""
        checked = self.checked
        if self.node.task_id:
            return checked
        return {**checked, 'ID': self.task_id}

    @property
    def node(self) -> TaskNode:
        """The task as the parser reads it.

        Raises
        ------
        ValueError
            The task is a checklist item, or a subtask is given a list
            or a field only the top-level task carries.
        """
        node = self.task.node
        node.refuse_checklist_item()
        if self.nested:
            if self.list_name is not None:
                raise ValueError(
                    f'{node.title!r} is a subtask: --list moves a '
                    'top-level task, and its subtasks with it'
                )
            self.supplied.refuse_root_fields()
        return node

    @property
    def new_title(self) -> str | None:
        """The title the update writes, or None where it names none.

        Raises
        ------
        ValueError
            The title holds a line break.
        """
        if self.title is None:
            return None
        return SuppliedTitle(self.title).checked

    @property
    def new_description(self) -> 'SuppliedDescription | None':
        """The description the update writes, or None where it names none.

        An empty description clears the description lines.
        """
        if self.description is None:
            return None
        return SuppliedDescription(self.description)

    @property
    def checked(self) -> dict[str, str]:
        """The named fields, read.

        Raises
        ------
        ValueError
            No field, title or description is named and no list moves
            the task, or a supplied value does not read. The list is
            read only when nothing else is named.
        """
        named = (self.title, self.description)
        if (
            not self.fields
            and all(value is None for value in named)
            and not (self.list_name is not None and self.moved)
        ):
            raise ValueError(
                'nothing to update: name a field, a title, a description '
                'or a list'
            )
        return self.supplied.checked

    @property
    def supplied(self) -> 'SuppliedFields':
        """The named fields, read against the day of the task."""
        return SuppliedFields(self.fields, self.task.today)

    @cached_property
    def task_id(self) -> str:
        """The task's id, or a new one.

        Cached: a new id is drawn at random, so every read names one.
        """
        return self.node.task_id or new_task_id()

    @property
    def nested(self) -> bool:
        """Whether the task is a subtask, at any depth."""
        return len(self.task.ancestry) > 1

    @property
    def entry(self) -> str:
        """The task line as written."""
        return self.document.lines[self.node.raw_index]

    @property
    def entries(self) -> list[str]:
        """None: an update logs no completed-log record."""
        return []

    @property
    def events(self) -> list['Event']:
        """One `TaskUpdated`, on the stream of the task."""
        return [Event(UPDATED_EVENT, f'task/{self.task_id}', self.payload)]

    @property
    def payload(self) -> dict[str, Any]:
        """What changed, from what, where a subtask sits, and attributes.

        A top-level task's ancestry is its own title, which the snapshot
        already carries.
        """
        payload: dict[str, Any] = {
            'delta': self.delta,
            'snapshot': self.node.listed_snapshot(self.task.path.stem),
        }
        if self.nested:
            payload['ancestry'] = self.ancestry.path
        if self.attrs:
            payload['attrs'] = self.attrs
        return payload

    @property
    def delta(self) -> dict[str, list[Any]]:
        """Each value written against the one it replaced."""
        fields = self.node.fields
        delta = {
            name: [fields.get(name), value]
            for name, value in self.written.items()
        }
        if self.new_title is not None:
            delta['title'] = [self.node.title, self.new_title]
        new_description = self.new_description
        if new_description is not None:
            delta['description'] = [
                self.node.description,
                new_description.checked,
            ]
        if self.moved:
            delta['list'] = [self.task.path.stem, self.path.stem]
        return delta

    @property
    def ancestry(self) -> Ancestry:
        """The task and every task above it."""
        return Ancestry(self.task.ancestry)


class Reopen:
    """The reopen of a closed task, named by its stream in the journal.

    A completion or a scratch closes a task (ADR 0025). The task comes
    back open, with the fields, the title and the description the reopen
    names. A top-level task comes back last in the open section of its
    list, as the last snapshot of its stream records it, each child
    checked off. A closed subtask opens where its line stands, or comes
    back with the record of its top-level task, and each closed task
    above it opens too.
    """

    def __init__(
        self,
        task: Task,
        zone: tzinfo | None,
        fields: dict[str, str],
        title: str | None = None,
        description: str | None = None,
        attrs: dict[str, str] | None = None,
        list_name: str | None = None,
    ) -> None:
        self.task = task
        self.zone = zone
        self.fields = fields
        self.title = title
        self.description = description
        self.attrs = attrs
        self.list_name = list_name

    def write(self) -> None:
        """Write the list and its events.

        Every value is read before the first write, so a refused write
        writes nothing.
        """
        text = self.text
        changes = Changeset(
            {self.path: text},
            self.entries,
            self.events,
            self.path,
            self.source,
        )
        changes.write()

    @property
    def source(self) -> Path:
        """The source directory of the task."""
        return self.task.source

    @property
    def text(self) -> str:
        """The list with the task open in it.

        Raises
        ------
        ValueError
            A supplied value does not read, the selector names several
            closed tasks or a checklist item, a subtask is given a list
            or a field only the top-level task carries, no list or record
            holds the line of a subtask, no list is named for a record
            that names none, the title holds a line break, or a
            description line is refused.
        SelectionError
            The selector names no open task and no closed task.
        ListError
            The list named is not a discovered list.
        """
        return self.document.text

    @cached_property
    def document(self) -> TodoDocument:
        """The restored list: each closed task of the chain open.

        The task the reopen names takes its fields, title and
        description. Cached: the write changes the list this reads, and
        the echo reads the line after the write.
        """
        written = self.checked
        self.refuse_nested_changes()
        doc = self.restored
        for task in self.opened:
            doc.mark_open(task.raw_index)
            if not task.task_id:
                doc.set_field(task.raw_index, 'ID', self.ids[task.raw_index])
        node = self.node
        doc.set_fields(node.raw_index, written)
        new_title = self.new_title
        if new_title is not None:
            doc.set_title(node.raw_index, new_title)
        new_description = self.new_description
        if new_description is not None:
            doc.drop(set(node.note_indices))
            doc.insert_description(node.raw_index, new_description.lines)
        return doc

    @property
    def checked(self) -> dict[str, str]:
        """The named fields, read.

        Raises
        ------
        ValueError
            A supplied value does not read.
        """
        return self.supplied.checked

    @property
    def supplied(self) -> 'SuppliedFields':
        """The named fields, read against the day of the task."""
        return SuppliedFields(self.fields, self.task.today)

    @cached_property
    def stream(self) -> TaskStream:
        """The closed stream the selector names.

        Cached: the write opens the stream.

        Raises
        ------
        ValueError
            The selector names several closed tasks, or a checklist
            item.
        SelectionError
            The selector names no closed task either.
        """
        closed = [stream for stream in self.streams if stream.closed]
        selection = StreamSelection(closed, self.task.selector)
        if not selection.candidates:
            self.refuse_checklist_item()
            raise SelectionError(
                f'no open task matches {self.task.selector!r}'
            )
        return selection.stream

    @property
    def streams(self) -> list[TaskStream]:
        """Every stream of the journal of the source."""
        journal = Journal(self.source)
        return [
            TaskStream(stream_id, events, self.zone)
            for stream_id, events in journal.streams.items()
        ]

    def refuse_checklist_item(self) -> None:
        """Refuse a selector that names a checklist item in the journal.

        Raises
        ------
        ValueError
            A checklist item's title holds the selector. The refusal
            names the id of each task that owns one.
        """
        part = self.task.selector.lower()
        owners = [
            f'[ID:{stream.task_id}]'
            for stream in self.streams
                if any(part in title.lower() for title in stream.checklist_titles)
        ]  # fmt: skip
        if owners:
            raise ValueError(
                f'{self.task.selector!r} names a checklist item of '
                f'{", ".join(owners)}: a checklist item opens with its '
                'task, not on its own'
            )

    def refuse_nested_changes(self) -> None:
        """Refuse a list, or a field the top-level task owns, on a subtask.

        Raises
        ------
        ValueError
            The stream is a subtask's, and the reopen names a list or
            such a field.
        """
        stream = self.stream
        if not stream.nested:
            return
        if self.list_name is not None:
            raise ValueError(
                f'{stream.title!r} is a subtask: --list moves a top-level '
                'task, and its subtasks with it'
            )
        self.supplied.refuse_root_fields()

    @cached_property
    def path(self) -> Path:
        """The list the task opens in.

        The list that holds the line of a subtask. Otherwise the list
        `list_name` names, or else the list the record names. Cached:
        discovery reads every list in the source.

        Raises
        ------
        ValueError
            Neither names a list.
        ListError
            The name is not a discovered list.
        """
        held = self.held
        if held is not None:
            return held
        record = self.record
        name = self.list_name or record.list_name
        if name is None:
            raise ValueError(
                f'{record.title!r} was closed before btodo recorded its '
                'list: name the list with --list'
            )
        return NamedList(self.source, name).path

    @cached_property
    def held(self) -> Path | None:
        """The list that holds the closed line of a subtask, or None.

        Cached: discovery reads every list in the source.
        """
        stream = self.stream
        if not stream.nested:
            return None
        for path in discover_lists(self.source):
            tasks = list(TodoDocument(path.read_text()).tasks)
            for task in tasks:
                if task.done and task.task_id == stream.task_id:
                    return path
                tasks.extend(task.children)
        return None

    @property
    def record(self) -> TaskStream:
        """The closed top-level stream whose snapshot holds the task.

        The stream itself for a top-level task. Read only where no list
        holds the line of the task.

        Raises
        ------
        ValueError
            No list and no record holds the line of a subtask. The
            refusal names the parent.
        """
        stream = self.stream
        if not stream.nested:
            return stream
        found = [
            record
            for record in self.streams
                if record.closed and not record.nested and record.snapshot
                and stream.task_id in RecordedTask(record.snapshot, 0).ids
        ]  # fmt: skip
        if not found:
            raise ValueError(
                f'{stream.title!r} is a subtask of {self.parent}, and no '
                'list and no record of a closed task holds its line'
            )
        return found[-1]

    @property
    def parent(self) -> str:
        """The parent of a subtask: its `[ID:]`, or else its path."""
        stream = self.stream
        if stream.parent_id:
            return f'[ID:{stream.parent_id}]'
        payload = stream.own[-1]['payload']
        title = payload['snapshot']['title']
        path = payload['ancestry'].removesuffix(f'{ANCESTRY_SEPARATOR}{title}')
        return repr(path)

    @property
    def restored(self) -> TodoDocument:
        """The list as read, the recorded block last in its open section."""
        doc = TodoDocument(self.path.read_text())
        if self.held is not None:
            return doc
        index = doc.open_end
        for offset, line in enumerate(self.recorded.lines):
            doc.insert(index + offset, line)
        return doc

    @property
    def recorded(self) -> 'RecordedTask':
        """The block of the record, with the id of its stream on it."""
        record = self.record
        snapshot = record.snapshot or {}
        fields = dict(snapshot['fields'])
        if not fields.get('ID'):
            fields['ID'] = record.task_id
        return RecordedTask({**snapshot, 'fields': fields}, 0)

    @property
    def ancestry(self) -> list[TaskNode]:
        """The task and every task above it in the restored list."""
        task_id = self.stream.task_id
        return next(
            chain
            for chain in self.chains.values()
                if chain[-1].task_id == task_id
        )  # fmt: skip

    @cached_property
    def chains(self) -> dict[int, list[TaskNode]]:
        """Each task of the restored list and every task above it.

        By the line of the task, outermost first. Cached: the write
        changes the list this reads.
        """
        found = [[task] for task in self.restored.tasks]
        for chain in found:
            found.extend([*chain, child] for child in chain[-1].children)
        return {chain[-1].raw_index: chain for chain in found}

    @property
    def opened(self) -> list[TaskNode]:
        """The closed tasks of the ancestry, outermost first."""
        return [task for task in self.ancestry if task.done]

    @cached_property
    def ids(self) -> dict[int, str]:
        """The id of each task the reopen opens, by its line.

        A task with no id takes a new one. Cached: a new id is drawn at
        random, so every read names one.
        """
        return {
            task.raw_index: task.task_id or new_task_id()
            for task in self.opened
        }

    @property
    def node(self) -> TaskNode:
        """The task the reopen names, in the restored list."""
        return self.ancestry[-1]

    @property
    def new_title(self) -> str | None:
        """The title the reopen writes, or None where it names none.

        Raises
        ------
        ValueError
            The title holds a line break.
        """
        if self.title is None:
            return None
        return SuppliedTitle(self.title).checked

    @property
    def new_description(self) -> 'SuppliedDescription | None':
        """The description the reopen writes, or None where it names none."""
        if self.description is None:
            return None
        return SuppliedDescription(self.description)

    @property
    def entry(self) -> str:
        """The task line as written."""
        return self.document.lines[self.node.raw_index]

    @property
    def entries(self) -> list[str]:
        """None: a reopen logs no completed-log record."""
        return []

    @property
    def events(self) -> list['Event']:
        """One `TaskUpdated` per task the reopen opens, outermost first.

        The event of the task the reopen names carries its changes and
        its attributes.
        """
        named = self.node.raw_index
        events = []
        for task in self.opened:
            path = Ancestry(self.chains[task.raw_index])
            task_id = self.ids[task.raw_index]
            event = OpenedTask(path, task_id, self.list_left).event
            if task.raw_index == named:
                payload = event.payload
                delta = {**self.delta, **payload['delta']}
                payload = {**payload, 'delta': delta}
                if self.attrs:
                    payload['attrs'] = self.attrs
                event = Event(event.type, event.stream, payload)
            events.append(event)
        return events

    @property
    def delta(self) -> dict[str, list[Any]]:
        """Each value the reopen writes against the one it replaced.

        A top-level task that comes back to another list records the
        list it left.
        """
        node = self.node
        delta = {
            name: [node.fields.get(name), value]
            for name, value in self.checked.items()
        }
        new_title = self.new_title
        if new_title is not None:
            delta['title'] = [node.title, new_title]
        new_description = self.new_description
        if new_description is not None:
            delta['description'] = [
                node.description,
                new_description.checked,
            ]
        list_left, list_name = self.list_left, self.path.stem
        if list_left != list_name:
            delta['list'] = [list_left, list_name]
        return delta

    @property
    def list_left(self) -> str | None:
        """The list the task was in before the reopen, by its name.

        None where its record names none.
        """
        held = self.held
        if held is not None:
            return held.stem
        return self.record.list_name


class Completion:
    """The completion of a task and every ancestor it finishes (SCHEMA.md).

    A task is complete when all its children are, so checking the last
    open child completes the parent, and that may complete its own
    parent in turn. Once the top-level task is done its whole block
    goes, unless it repeats: then it stays with a recomputed `DUE`, and
    only its children go.
    """

    def __init__(
        self,
        task: Task,
        attrs: dict[str, str] | None = None,
    ) -> None:
        self.task = task
        self.attrs = attrs

    def write(self) -> None:
        """Write the list, its log records and its events.

        Every value is read before the first write, so a refused write
        writes nothing.
        """
        text = self.text
        changes = Changeset(
            {self.path: text},
            self.entries,
            self.events,
            self.path,
            self.source,
        )
        changes.write()

    @property
    def source(self) -> Path:
        """The source directory of the task."""
        return self.task.source

    @property
    def path(self) -> Path:
        """The list file that holds the task."""
        return self.task.path

    @property
    def text(self) -> str:
        """The list once the completion is written.

        Raises
        ------
        SelectionError
            The selector does not name exactly one open task.
        RepeatError
            A completed recurring task carries a `[REPEAT:]` btodo cannot
            read.
        """
        return self.document.text

    @property
    def document(self) -> TodoDocument:
        """The task's list: lines stamped, checked off, or dropped."""
        stamps = self.stamps
        doc = TodoDocument(self.task.doc.text)
        for index, fields in stamps.items():
            doc.set_fields(index, fields)
        for index in self.checked_off:
            doc.mark_done(index)
        doc.drop(self.dropped)
        return doc

    @property
    def stamps(self) -> dict[int, dict[str, str]]:
        """The fields each line gains, by its index.

        A task still in the list gains the id of its stream. A recurring
        top-level task gains its next due date.
        """
        recurrence = self.recurrence
        if recurrence is None:
            return {
                index: {'ID': task_id} for index, task_id in self.ids.items()
            }
        rescheduled = self.rescheduled
        if rescheduled is None:
            return {}
        index = recurrence.raw_index
        due = rescheduled.isoformat()
        return {index: {'DUE': due, 'ID': self.ids[index]}}

    @property
    def checked_off(self) -> list[int]:
        """The lines whose box is checked: none once the block goes."""
        if self.root_done:
            return []
        return [ancestry.node.raw_index for ancestry in self.ancestries]

    @property
    def dropped(self) -> set[int]:
        """The lines that go: the finished block, a recurrence kept.

        The recurrence is the same task rescheduled, so it keeps its id,
        its notes and its `[ADDED:]`, which ADR 0005 writes once and
        never updates. Its children do not carry over.
        """
        if not self.root_done:
            return set()
        if self.rescheduled is None:
            return self.root.block
        return set().union(*(child.block for child in self.root.children))

    @property
    def root_done(self) -> bool:
        """Whether the completion finishes the top-level task."""
        return len(self.ancestries[-1].tasks) == 1

    @cached_property
    def ids(self) -> dict[int, str]:
        """The id of each stream the completions land on, by its line.

        A stream task with no id takes a new one. Cached: a new id is
        drawn at random, so every read names one.
        """
        ids: dict[int, str] = {}
        for ancestry in self.ancestries:
            stream = ancestry.stream
            if stream.raw_index not in ids:
                ids[stream.raw_index] = stream.task_id or new_task_id()
        return ids

    @property
    def rescheduled(self) -> date | None:
        """The next due date of the recurrence, where it repeats.

        Raises
        ------
        RepeatError
            Its `[REPEAT:]` does not read.
        """
        recurrence = self.recurrence
        repeat = recurrence and recurrence.repeat
        if not repeat:
            return None
        return next_due(repeat, self.completed_on)

    @property
    def recurrence(self) -> TaskNode | None:
        """The task the completion reschedules if it repeats, or None.

        The top-level task, once the completion finishes it.
        """
        return self.root if self.root_done else None

    @property
    def root(self) -> TaskNode:
        """The top-level task of the block."""
        return self.task.ancestry[0]

    @property
    def completed_on(self) -> date:
        """The day the completion is for: the given day, or the clock's."""
        return self.task.today

    @property
    def ancestries(self) -> list[Ancestry]:
        """The ancestry of the task and of each ancestor it finishes.

        Deepest first, which is the order the completions are logged.
        """
        ancestry = self.task.ancestry
        found = [Ancestry(ancestry)]
        for depth in reversed(range(len(ancestry) - 1)):
            parent, child = ancestry[depth], ancestry[depth + 1]
            if not all(c.done or c is child for c in parent.children):
                break
            found.append(Ancestry(ancestry[: depth + 1]))
        return found

    @property
    def entries(self) -> list[str]:
        """The completed-log records, deepest first.

        SCHEMA.md logs no checklist item.
        """
        return [
            LogEntry(self.path, completion).text
            for completion in self.completions
                if not completion.ancestry.node.is_checklist_item
        ]  # fmt: skip

    @property
    def events(self) -> list['Event']:
        """One `TaskCompleted` per completion, deepest first.

        Raises
        ------
        ValueError
            The named task is a checklist item and attributes are given.
        """
        self.task.node.refuse_attributes(self.attrs)
        events = []
        for completion in self.completions:
            stream = self.ids[completion.ancestry.stream.raw_index]
            payload = completion.payload
            events.append(Event(COMPLETED_EVENT, f'task/{stream}', payload))
        return [*self.assignments, *events]

    @property
    def completions(self) -> list['TaskCompletion']:
        """One per task the completion finishes, deepest first.

        A rescheduled task takes its next due date. The attributes go
        to the named task alone.
        """
        recurrence, rescheduled = self.recurrence, self.rescheduled
        day, ancestries = self.completed_on, self.ancestries
        list_name = self.path.stem
        completions = []
        for ancestry in ancestries:
            due = rescheduled if ancestry.node is recurrence else None
            attrs = self.attrs if ancestry is ancestries[0] else None
            completion = TaskCompletion(ancestry, due, day, list_name, attrs)
            completions.append(completion)
        return completions

    @property
    def assignments(self) -> list['Event']:
        """The `TaskUpdated` of each stream task given a new id.

        A block that goes keeps no line to carry an id, so it records
        none.
        """
        streams = {
            ancestry.stream.raw_index: ancestry.stream
            for ancestry in self.ancestries
        }
        return [
            IdAssignment(streams[index], fields['ID'], self.path.stem).event
            for index, fields in self.stamps.items()
                if not streams[index].task_id
        ]  # fmt: skip


class Scratch:
    """The scratch of a task: its block dropped without completing it.

    The whole block goes -- the task, its notes, its children -- and
    nothing cascades: abandoning a child says nothing about its parent.
    btodo cannot tell a task accepted in an earlier session from one
    proposed in this one, so every scratch is logged (SCHEMA.md).
    """

    def __init__(
        self,
        task: Task,
        attrs: dict[str, str] | None = None,
    ) -> None:
        self.task = task
        self.attrs = attrs

    def write(self) -> None:
        """Write the list, its log records and its events.

        Every value is read before the first write, so a refused write
        writes nothing.
        """
        text = self.text
        changes = Changeset(
            {self.path: text},
            self.entries,
            self.events,
            self.path,
            self.source,
        )
        changes.write()

    @property
    def source(self) -> Path:
        """The source directory of the task."""
        return self.task.source

    @property
    def path(self) -> Path:
        """The list file that holds the task."""
        return self.task.path

    @property
    def text(self) -> str:
        """The list without the task's block.

        Raises
        ------
        SelectionError
            The selector does not name exactly one open task.
        """
        return self.document.text

    @property
    def document(self) -> TodoDocument:
        """The task's list: its stream stamped, its block dropped.

        A checklist item cannot hold an id, so its event belongs to the
        stream of an ancestor, and that ancestor's line carries the id.
        """
        doc = TodoDocument(self.task.doc.text)
        if self.stream is not self.node:
            doc.set_field(self.stream.raw_index, 'ID', self.stream_id)
        doc.drop(self.node.block)
        return doc

    @property
    def stream(self) -> TaskNode:
        """The task whose stream records the scratch."""
        return self.ancestry.stream

    @property
    def ancestry(self) -> Ancestry:
        """The task and every task above it."""
        return Ancestry(self.task.ancestry)

    @property
    def node(self) -> TaskNode:
        """The task as the parser reads it."""
        return self.task.node

    @cached_property
    def stream_id(self) -> str:
        """The stream task's id, or a new one.

        Cached: a new id is drawn at random, so every read names one.
        """
        return self.stream.task_id or new_task_id()

    @property
    def entries(self) -> list[str]:
        """The one completed-log record, or none for a checklist item."""
        if self.node.is_checklist_item:
            return []
        return [LogEntry(self.path, self).text]

    @property
    def day(self) -> date:
        """The day the scratch is logged under."""
        return self.task.today

    @property
    def status(self) -> str:
        """The status the log records a scratch under."""
        return SCRATCHED_STATUS

    @property
    def events(self) -> list['Event']:
        """One `TaskScratched`, on the stream task's stream.

        The stream of a checklist item is an ancestor's, so its payload
        marks it as a checklist item. The payload carries the
        attributes.

        Raises
        ------
        ValueError
            The task is a checklist item and attributes are given.
        """
        self.node.refuse_attributes(self.attrs)
        payload: dict[str, Any] = {
            'delta': {'removed': [False, True]},
            'snapshot': self.node.listed_snapshot(self.path.stem),
            'ancestry': self.ancestry.path,
        }
        if self.node.is_checklist_item:
            payload['checklist_item'] = True
        if self.attrs:
            payload['attrs'] = self.attrs
        event = Event(SCRATCHED_EVENT, f'task/{self.stream_id}', payload)
        return [self.stamp, event] if self.stamped else [event]

    @property
    def stamp(self) -> 'Event':
        """The `TaskUpdated` that records the stream task's new id."""
        return IdAssignment(self.stream, self.stream_id, self.path.stem).event

    @property
    def stamped(self) -> bool:
        """Whether the stream task of a checklist item is given an id.

        A task that is its own stream loses its line, so no id stays.
        """
        return self.stream is not self.node and not self.stream.task_id


class Annotation:
    """The note on an open task: its attributes on an event of its own.

    The note changes no task state. A task with no `[ID:]` is given one
    first, on an event of its own, so the note has a stream to land on.
    """

    def __init__(self, task: Task, attrs: dict[str, str]) -> None:
        self.task = task
        self.attrs = attrs

    def write(self) -> None:
        """Write the list, its log records and its events.

        Every value is read before the first write, so a refused write
        writes nothing.
        """
        text = self.text
        changes = Changeset(
            {self.path: text},
            self.entries,
            self.events,
            self.path,
            self.source,
        )
        changes.write()

    @property
    def source(self) -> Path:
        """The source directory of the task."""
        return self.task.source

    @property
    def path(self) -> Path:
        """The list file that holds the task."""
        return self.task.path

    @property
    def text(self) -> str:
        """The list with the task given an id where it carries none.

        Raises
        ------
        ValueError
            The note carries no attribute, or the task is a checklist
            item, which takes no attributes.
        SelectionError
            The selector does not name exactly one open task.
        """
        return self.document.text

    @property
    def document(self) -> TodoDocument:
        """The task's list, its line stamped with an id where it has none.

        The note is checked before the selector is read.
        """
        self.refuse_empty()
        doc = TodoDocument(self.task.doc.text)
        if self.stamped:
            doc.set_field(self.node.raw_index, 'ID', self.task_id)
        return doc

    def refuse_empty(self) -> None:
        """Refuse a note that carries nothing.

        Raises
        ------
        ValueError
            The note holds no attribute, the key `note` included.
        """
        if not self.attrs:
            raise ValueError('nothing to note: give a note or an attribute')

    @property
    def stamped(self) -> bool:
        """Whether the task is given an id: it carries none.

        An `[ID:]` with nothing in it names no stream, so it counts as
        none.
        """
        return not self.node.task_id

    @property
    def node(self) -> TaskNode:
        """The task as the parser reads it.

        Raises
        ------
        ValueError
            The task is a checklist item, which takes no attributes. An
            `[ID:]` stamped on one would promote it to a subtask.
        """
        node = self.task.node
        node.refuse_attributes(self.attrs)
        return node

    @cached_property
    def task_id(self) -> str:
        """The task's id, or a new one.

        Cached: a new id is drawn at random, so every read names one.
        """
        return self.node.task_id or new_task_id()

    @property
    def entry(self) -> str:
        """The task line as written."""
        return self.document.lines[self.node.raw_index]

    @property
    def entries(self) -> list[str]:
        """None: a note logs no completed-log record."""
        return []

    @property
    def events(self) -> list['Event']:
        """The task's stamp if it has no id, then one `TaskAnnotated`."""
        event = Event(ANNOTATED_EVENT, f'task/{self.task_id}', self.payload)
        return [self.stamp, event] if self.stamped else [event]

    @property
    def stamp(self) -> 'Event':
        """The `TaskUpdated` that records the task's new id."""
        return IdAssignment(self.node, self.task_id, self.path.stem).event

    @property
    def payload(self) -> dict[str, Any]:
        """The task, where a subtask sits, and the attributes.

        No delta: a note changes nothing in the task.
        """
        snapshot = self.node.listed_snapshot(self.path.stem)
        payload: dict[str, Any] = {'snapshot': snapshot}
        if self.nested:
            payload['ancestry'] = self.ancestry.path
        payload['attrs'] = self.attrs
        return payload

    @property
    def nested(self) -> bool:
        """Whether the task is a subtask, at any depth."""
        return len(self.task.ancestry) > 1

    @property
    def ancestry(self) -> Ancestry:
        """The task and every task above it."""
        return Ancestry(self.task.ancestry)


class Backfill:
    """The backfill of a source: each open top-level task given a date.

    Parked lists are included: they opt out of views, not of existing,
    and an unparked item should carry an add date.
    """

    def __init__(self, source: Path, today: date) -> None:
        self.source = source
        self.today = today

    def write(self) -> None:
        """Write each list that holds a task to stamp."""
        for listed in self.lists:
            listed.write()

    @cached_property
    def lists(self) -> list['ListBackfill']:
        """The discovered lists that hold a task to stamp, by name.

        Cached: the write changes the lists the report of it reads.
        """
        found = [
            ListBackfill(path, self.today)
            for path in discover_lists(self.source)
        ]
        return [
            backfilled
            for backfilled in found
                if backfilled.tasks
        ]  # fmt: skip


class CompletedLog:
    """The completed log of a source, which is append-only (SCHEMA.md)."""

    def __init__(self, source: Path) -> None:
        self.source = source

    @property
    def path(self) -> Path:
        """The log file in the source directory."""
        return self.source / COMPLETED_LOG

    @property
    def lead(self) -> str:
        """What precedes a new record: a newline if the log ends mid-line."""
        existing = self.path.read_text() if self.path.exists() else ''
        return '\n' if existing and not existing.endswith('\n') else ''

    def append(self, entries: Sequence[str]) -> None:
        """Append `entries`, one per line.

        No entry leaves the log as it was, absent or not.
        """
        if not entries:
            return
        lead = self.lead
        with self.path.open('a', encoding='utf-8') as handle:
            handle.write(lead + '\n'.join(entries) + '\n')


class Changeset:
    """What one write changes in a source: lists, the log, the journal.

    `lists` holds the text of each list the write changes, by its path.
    Each event names `path` as its source file. A write object reads its
    list texts first, so their refusals come first.
    """

    def __init__(
        self,
        lists: dict[Path, str],
        entries: list[str],
        events: list['Event'],
        path: Path,
        source: Path,
    ) -> None:
        self.lists = lists
        self.entries = entries
        self.events = events
        self.path = path
        self.source = source

    def write(self) -> None:
        """Write each list, then the log records, then the events.

        A list that holds its text already is not written, so file sync
        sees no change.
        """
        for path, text in self.lists.items():
            if path.read_text() != text:
                path.write_text(text)
        CompletedLog(self.source).append(self.entries)
        journal = Journal(self.source)
        for event in self.events:
            journal.append(
                event.type,
                event.stream,
                event.payload,
                actor=ACTOR,
                source_file=self.path.name,
            )


class NamedList:
    """The discovered list of a source whose filename stem is a name.

    Parked lists count: parking opts a file out of *views*, not out of
    being written to.
    """

    def __init__(self, source: Path, name: str) -> None:
        self.source = source
        self.name = name

    @property
    def path(self) -> Path:
        """The list file.

        Raises
        ------
        ListError
            No discovered list carries the name.
        """
        found = next(
            (
                path
                for path in self.lists
                    if path.stem == self.name
            ),
            None,
        )  # fmt: skip
        if found is None:
            stems = ', '.join(path.stem for path in self.lists)
            raise ListError(
                f'no list named {self.name!r} in {self.source}; '
                f'available: {stems}'
            )
        return found

    @cached_property
    def lists(self) -> list[Path]:
        """Every list in the source. Cached: discovery reads each one."""
        return discover_lists(self.source)


class SuppliedTitle:
    """A title a caller supplies to a write, read before any write."""

    def __init__(self, text: str) -> None:
        self.text = text

    @property
    def checked(self) -> str:
        """The title, whole on its task line.

        Raises
        ------
        ValueError
            The title holds a line feed or a carriage return. Either
            ends the task line when the list is read again.
        """
        if '\n' in self.text or '\r' in self.text:
            raise ValueError(
                f'title must hold no line break, not {self.text!r}'
            )
        return self.text


class SuppliedDescription:
    """A description a caller supplies to a write, read before any write.

    Each line of the text is one description line. An empty text holds
    no line, so an update that supplies one clears the description.
    """

    def __init__(self, text: str) -> None:
        self.text = text

    @property
    def checked(self) -> str | None:
        """The description as a snapshot stores it, or None if empty."""
        return '\n'.join(self.lines) or None

    @property
    def lines(self) -> list[str]:
        """The description lines, each stripped of its indent.

        Raises
        ------
        ValueError
            A line is blank, reads as a task line, a heading or a
            comment, or holds a carriage return. The parser reads such
            a line back as something other than a description line.
        """
        if not self.text:
            return []
        lines = self.text.split('\n')
        for line in lines:
            stripped = line.strip()
            if not stripped:
                refusal = 'is blank'
            elif CHECKBOX_RE.match(stripped):
                refusal = 'reads as a task line'
            elif stripped.startswith('## '):
                refusal = 'reads as a heading'
            elif stripped.startswith('<!--'):
                refusal = 'reads as a comment'
            elif '\r' in line:
                refusal = 'holds a carriage return'
            else:
                continue
            raise ValueError(f'description line {line!r} {refusal}')
        return [line.strip() for line in lines]


class SuppliedFields:
    """The fields a caller supplies to a write, read before any write.

    Only the values with a grammar btodo depends on are checked: a
    `TAGS` string is free-form and cannot be wrong.
    """

    def __init__(self, fields: dict[str, str], today: date) -> None:
        self.fields = fields
        self.today = today

    @property
    def ordered(self) -> dict[str, str]:
        """The fields as read, in SCHEMA.md order."""
        checked = self.checked
        return {
            name: checked[name]
            for name in SCHEMA_FIELDS
                if name in checked
        }  # fmt: skip

    @property
    def checked(self) -> dict[str, str]:
        """The fields, each value read, a due date in ISO form.

        Raises
        ------
        ValueError
            A `P`, `LOE`, `DUE` or `REPEAT` does not read, checked in
            that order. `RepeatError`, a ValueError, covers `REPEAT`.
        """
        checked = dict(self.fields)
        priority = checked.get('P')
        if priority is not None and not priority.isdigit():
            raise ValueError(f'P must be a whole number, not {priority!r}')

        loe = checked.get('LOE')
        if loe is not None and loe not in LOE_VALUES:
            raise ValueError(
                f'LOE must be one of {", ".join(LOE_VALUES)}, not {loe!r}'
            )

        due = checked.get('DUE')
        if due is not None:
            parsed = parse_date(due)
            if parsed is None:
                raise ValueError(f'DUE must be an ISO date, not {due!r}')
            # Normalised, not passed through: `date.fromisoformat` accepts
            # more spellings on newer interpreters, and a line's meaning
            # must not depend on which one wrote it.
            checked['DUE'] = parsed.isoformat()

        repeat = checked.get('REPEAT')
        if repeat is not None:
            # Validated by scheduling it and throwing the answer away: the
            # repeat parser is the only definition of a readable spec, and
            # an unreadable one must fail before a task carries it.
            next_due(repeat, self.today)
        return checked

    def refuse_root_fields(self) -> None:
        """Refuse a field that only the top-level task carries.

        Raises
        ------
        ValueError
            The fields name one. Nothing reads such a field on a child,
            so writing it would read as a change that never happened.
        """
        for name in ROOT_ONLY_FIELDS:
            if name in self.fields:
                raise ValueError(
                    f'{name} belongs to the top-level task, not to a subtask'
                )


class SuppliedAttributes:
    """The attributes a caller supplies to a write, read before any write.

    `text` holds `key=value` segments. The text of `note` enters as the
    key `note` and never runs through the split.
    """

    def __init__(self, text: str | None, note: str | None) -> None:
        self.text = text
        self.note = note

    @property
    def checked(self) -> dict[str, str]:
        """Each key against its value, in the order given.

        Raises
        ------
        ValueError
            A key is outside the grammar, a value is empty or holds a
            line break, or a key is given twice.
        """
        checked: dict[str, str] = {}
        for key, value in self.pairs:
            if not ATTRIBUTE_KEY.fullmatch(key):
                raise ValueError(
                    f'attribute key must be a lowercase identifier, '
                    f'not {key!r}'
                )
            if not value:
                raise ValueError(f'attribute {key!r} must hold a value')
            if '\n' in value or '\r' in value:
                raise ValueError(
                    f'attribute {key!r} must hold no line break, not {value!r}'
                )
            if key in checked:
                raise ValueError(f'attribute {key!r} is given twice')
            checked[key] = value
        return checked

    @property
    def pairs(self) -> list[tuple[str, str]]:
        """Each segment split at its first `=`, then the note.

        Raises
        ------
        ValueError
            A segment holds no `=`.
        """
        pairs = []
        for segment in self.segments:
            key, sign, value = segment.partition('=')
            if not sign:
                raise ValueError(
                    f'attribute must read key=value, not {segment!r}'
                )
            pairs.append((key, value))
        if self.note is not None:
            pairs.append((NOTE_KEY, self.note))
        return pairs

    @property
    def segments(self) -> list[str]:
        """The `key=value` segments of `text`, or none without it."""
        if self.text is None:
            return []
        return ATTRIBUTE_SEPARATOR.split(self.text)


class Event(NamedTuple):
    """One journal event a write records."""

    type: str
    stream: str
    payload: dict[str, Any]


class AddedLine:
    """A task an add writes, as its `TaskAdded` records it.

    `block` is the task line and its description lines, and `list_name`
    the stem of the list that receives it. `attrs` holds the attributes
    of the add, or None.
    """

    def __init__(
        self,
        block: str,
        written: dict[str, str],
        list_name: str,
        attrs: dict[str, str] | None = None,
    ) -> None:
        self.block = block
        self.written = written
        self.list_name = list_name
        self.attrs = attrs

    @property
    def payload(self) -> dict[str, Any]:
        """Each field written against nothing, the task, the attributes."""
        delta = {name: [None, value] for name, value in self.written.items()}
        payload = {
            'delta': delta,
            # Post-state, unlike every other event here: an add has no
            # prior state for a snapshot to describe. Taken from the block
            # as written, so it records the file, not the intent.
            'snapshot': self.node.listed_snapshot(self.list_name),
        }
        if self.attrs:
            payload['attrs'] = self.attrs
        return payload

    @property
    def node(self) -> TaskNode:
        """The block alone in an open section, as the parser reads it."""
        return TodoDocument(f'{OPEN_HEADING}\n{self.block}').tasks[0]


class IdAssignment:
    """The `TaskUpdated` that records an id given to a task with none."""

    def __init__(self, node: TaskNode, task_id: str, list_name: str) -> None:
        self.node = node
        self.task_id = task_id
        self.list_name = list_name

    @property
    def event(self) -> Event:
        """The new id against nothing, on the stream it names."""
        payload = {
            'delta': {'ID': [None, self.task_id]},
            'snapshot': self.node.listed_snapshot(self.list_name),
        }
        return Event(UPDATED_EVENT, f'task/{self.task_id}', payload)


class TaskCompletion:
    """One task a completion finishes, as its `TaskCompleted` records it.

    `rescheduled` is the next due date of a task the completion
    reschedules, and None for every other task. `day` is the day the
    completion is for, and `list_name` the stem of the list that holds
    the task. `attrs` holds the attributes of the named task, and None
    for every other task. The event of a checklist item lands on the
    stream of an ancestor, so its payload marks it as a checklist item.
    """

    def __init__(
        self,
        ancestry: Ancestry,
        rescheduled: date | None,
        day: date,
        list_name: str,
        attrs: dict[str, str] | None = None,
    ) -> None:
        self.ancestry = ancestry
        self.rescheduled = rescheduled
        self.day = day
        self.list_name = list_name
        self.attrs = attrs

    @property
    def payload(self) -> dict[str, Any]:
        """The done, a new due date beside it, the task, its path, its day.

        A checklist item also carries its mark, and the named task its
        attributes.
        """
        node = self.ancestry.node
        delta: dict[str, list[Any]] = {'done': [False, True]}
        if self.rescheduled is not None:
            delta['DUE'] = [node.due, self.rescheduled.isoformat()]
        payload: dict[str, Any] = {
            'delta': delta,
            'snapshot': node.listed_snapshot(self.list_name),
            'ancestry': self.ancestry.path,
        }
        if node.is_checklist_item:
            payload['checklist_item'] = True
        if self.attrs:
            payload['attrs'] = self.attrs
        payload['completed_on'] = self.day.isoformat()
        return payload

    @property
    def status(self) -> str:
        """The status the log records a completion under."""
        return DONE_STATUS


class RecordedTask:
    """A task as a snapshot records it, closed, as the lines of a list.

    `depth` counts the levels above the task. Each child snapshot comes
    back one level deeper, closed too.
    """

    def __init__(self, snapshot: dict[str, Any], depth: int) -> None:
        self.snapshot = snapshot
        self.depth = depth

    @property
    def lines(self) -> list[str]:
        """The task line, its description lines, then each child's."""
        return [
            self.line,
            *self.description_lines,
            *(line for child in self.children for line in child.lines),
        ]

    @property
    def line(self) -> str:
        """The task line, checked off, its fields in recorded order."""
        fields = ''.join(
            f' [{name}:{value}]'
            for name, value in self.snapshot['fields'].items()
        )
        return f'{self.indent}- [x] {self.snapshot["title"]}{fields}'

    @property
    def indent(self) -> str:
        """The indent of the task line."""
        return ' ' * (self.depth * SUBTASK_INDENT)

    @property
    def description_lines(self) -> list[str]:
        """The description lines, under the title."""
        description = self.snapshot.get('description')
        if not description:
            return []
        lead = self.indent + ' ' * DESCRIPTION_INDENT
        return [f'{lead}{line}' for line in description.split('\n')]

    @property
    def children(self) -> list['RecordedTask']:
        """Each child the snapshot records, one level deeper."""
        return [
            RecordedTask(child, self.depth + 1)
            for child in self.snapshot.get('children', [])
        ]

    @property
    def ids(self) -> set[str]:
        """The id of the task and of each task below it that has one."""
        own = self.snapshot['fields'].get('ID')
        found = {own} if own else set()
        for child in self.children:
            found |= child.ids
        return found


class OpenedTask:
    """One task a reopen opens, as its `TaskUpdated` records it.

    `task_id` names its stream. A task with no `[ID:]` takes it on the
    same event. `list_name` is the list the task was in before the
    reopen, and None where no record names one.
    """

    def __init__(
        self,
        ancestry: Ancestry,
        task_id: str,
        list_name: str | None,
    ) -> None:
        self.ancestry = ancestry
        self.task_id = task_id
        self.list_name = list_name

    @property
    def event(self) -> Event:
        """The `TaskUpdated` on the stream of the task."""
        return Event(UPDATED_EVENT, f'task/{self.task_id}', self.payload)

    @property
    def payload(self) -> dict[str, Any]:
        """The opening, the task as it was, and where a subtask sits."""
        node = self.ancestry.node
        delta: dict[str, list[Any]] = {}
        if not node.task_id:
            delta['ID'] = [None, self.task_id]
        delta['done'] = [True, False]
        payload: dict[str, Any] = {
            'delta': delta,
            'snapshot': {**node.snapshot, 'list': self.list_name},
        }
        if len(self.ancestry.tasks) > 1:
            payload['ancestry'] = self.ancestry.path
        return payload


class LogEntry:
    """One `completed.md` record of a write to one task, in `path`.

    The record reads the object that also builds the event of the
    write, so the log renders what the journal records.
    """

    def __init__(self, path: Path, logged: 'LogSource') -> None:
        self.path = path
        self.logged = logged

    @property
    def text(self) -> str:
        """The record: the path, the SCHEMA.md fields, the attributes."""
        entry = f'{self.day} | {self.category} | {self.status} | {self.title}'
        parts = (entry, self.fields, self.attributes)
        return ' '.join(
            part
            for part in parts
                if part
        )  # fmt: skip

    @property
    def day(self) -> date:
        """The day the record is logged under."""
        return self.logged.day

    @property
    def category(self) -> str:
        """The list that holds the task, by its name."""
        return self.path.stem

    @property
    def status(self) -> str:
        """DONE or SCRATCHED."""
        return self.logged.status

    @property
    def title(self) -> str:
        """The `Parent > Child` path of the task."""
        return self.logged.ancestry.path

    @property
    def fields(self) -> str:
        """The SCHEMA.md fields of the task, in SCHEMA.md order."""
        ordered = self.logged.ancestry.node.schema_fields
        return ' '.join(f'[{name}:{value}]' for name, value in ordered.items())

    @property
    def attributes(self) -> str:
        """The attributes of the write as one block, or none without them.

        The block holds a JSON object in ASCII, so a value can hold no
        line break and no character a reader could take for the end.
        """
        attrs = self.logged.attrs
        if not attrs:
            return ''
        return f'{ATTRIBUTES_MARK}{dumps(attrs)}]'


class LogSource(Protocol):
    """A write to one task, as its completed-log record reads it."""

    @property
    def ancestry(self) -> Ancestry: ...

    @property
    def day(self) -> date: ...

    @property
    def status(self) -> str: ...

    @property
    def attrs(self) -> dict[str, str] | None: ...


class ListBackfill:
    """The backfill of one list: `[ADDED:today]` where a task has none.

    `today` is the migration date, not the real add date: that is not
    recoverable from the files (ADR 0005). Age accrues from here.
    """

    def __init__(self, path: Path, today: date) -> None:
        self.path = path
        self.today = today

    def write(self) -> None:
        """Write the list, its log records and its events.

        Every value is read before the first write, so a refused write
        writes nothing.
        """
        text = self.text
        changes = Changeset(
            {self.path: text},
            self.entries,
            self.events,
            self.path,
            self.source,
        )
        changes.write()

    @property
    def source(self) -> Path:
        """The source directory that holds the list."""
        return self.path.parent

    @property
    def text(self) -> str:
        """The list with every stamp written."""
        return self.document.text

    @property
    def document(self) -> TodoDocument:
        """The list as read, each task to stamp given its date and id."""
        doc = TodoDocument(self.parsed.text)
        for index, fields in self.stamps.items():
            doc.set_fields(index, fields)
        return doc

    @cached_property
    def parsed(self) -> TodoDocument:
        """The list as read.

        Cached: one read of the file answers every property.
        """
        return TodoDocument(self.path.read_text())

    @property
    def stamps(self) -> dict[int, dict[str, str]]:
        """The fields each task to stamp gains, by its line.

        A task with no id gains one beside its add date.
        """
        stamps = {}
        for task in self.tasks:
            fields = {'ADDED': self.today.isoformat()}
            if not task.task_id:
                fields['ID'] = self.ids[task.raw_index]
            stamps[task.raw_index] = fields
        return stamps

    @property
    def tasks(self) -> list[TaskNode]:
        """The open top-level tasks to stamp, in file order."""
        return [
            task
            for task in self.parsed.tasks
                if task.needs_added
        ]  # fmt: skip

    @cached_property
    def ids(self) -> dict[int, str]:
        """The id of each task to stamp, by its line.

        A task with no id takes a new one. Cached: a new id is drawn at
        random, so every read names one.
        """
        return {
            task.raw_index: task.task_id or new_task_id()
            for task in self.tasks
        }

    @property
    def entries(self) -> list[str]:
        """None: a backfill logs no completed-log record."""
        return []

    @property
    def events(self) -> list['Event']:
        """One `TaskAdded` per task stamped.

        The date is the migration's, not the task's, so the payload says
        so: a replay must not read it as an observed fact.
        """
        delta = {'ADDED': [None, self.today.isoformat()]}
        events = []
        for task in self.tasks:
            payload = {
                'delta': delta,
                'snapshot': task.listed_snapshot(self.path.stem),
                'backfilled': True,
            }
            stream = f'task/{self.ids[task.raw_index]}'
            events.append(Event(ADDED_EVENT, stream, payload))
        return events
