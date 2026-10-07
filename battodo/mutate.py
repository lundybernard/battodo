"""Markdown mutations that also record events (ADR 0004, ADR 0005).

Every mutation edits the raw task line in place and appends an event, so
the markdown stays authoritative while the journal accumulates history.
A file with nothing to change is not rewritten at all, so file sync
sees no change.

`add_task` and `add_subtask` create rather than edit. A new top-level
task lands as the last entry of a named list's `## Open` section,
carrying only the fields the caller gave it plus the `[ADDED:]` and
`[ID:]` btodo owns. A subtask lands last in its parent's block, one
indent level deeper: the markdown states the relation by indentation,
and the event names the parent by id.

`complete` implements SCHEMA.md's completion rules: log the ancestry to
`completed.md`, mark `[x]`, remove the block once the whole thing is
done, and reschedule a recurring task instead of deleting it. `scratch`
is the same plumbing for abandoning a task rather than finishing it:
the block goes, the log records it as SCRATCHED, and nothing cascades
or reschedules. `update_task` edits a task in place: it writes the
fields and the title it is given and touches nothing else. `backfill`
stamps `[ADDED:]` once on every task that lacks it.

Each write to an existing task consumes the `Task` its caller built,
so the write edits the document that selection read.
"""

from collections.abc import Sequence
from datetime import date
from functools import cached_property
from pathlib import Path
from typing import Any, NamedTuple

from .journal import Journal, new_task_id
from .lists import discover_lists
from .parser import (
    ANCESTRY_SEPARATOR,
    DATE_FIELDS,
    OPEN_HEADING,
    SCHEMA_FIELDS,
    Ancestry,
    TaskNode,
    TodoDocument,
    parse_date,
)
from .repeat import next_due
from .task import Task

ADDED_EVENT = 'TaskAdded'
COMPLETED_EVENT = 'TaskCompleted'
SCRATCHED_EVENT = 'TaskScratched'
UPDATED_EVENT = 'TaskUpdated'
COMPLETED_LOG = 'completed.md'
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
    ) -> None:
        self.source = source
        self.list_name = list_name
        self.title = title
        self.fields = fields
        self.today = today

    def write(self) -> None:
        """Write the list, its log records and its events.

        Every value is read before the first write, so a refused write
        writes nothing.
        """
        changes = Changeset(
            self.text,
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
            A supplied `P`, `LOE`, `DUE` or `REPEAT` does not read.
            `RepeatError`, a ValueError, covers `REPEAT`.
        """
        return self.document.text

    @property
    def document(self) -> TodoDocument:
        """The list as read, with the task last in its open section."""
        doc = TodoDocument(self.parsed.text)
        written = self.written
        doc.insert(self.index, f'- [ ] {self.title}')
        doc.set_fields(self.index, written)
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
    def entries(self) -> list[str]:
        """None: an add logs no completed-log record."""
        return []

    @property
    def events(self) -> list['Event']:
        """One `TaskAdded`, on the stream of the new task."""
        payload = AddedLine(self.entry, self.written).payload
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
    ) -> None:
        self.parent = parent
        self.list_name = list_name
        self.title = title
        self.fields = fields

    def write(self) -> None:
        """Write the list, its log records and its events.

        Every value is read before the first write, so a refused write
        writes nothing.
        """
        changes = Changeset(
            self.text,
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
            The parent is a task in another list, or a checklist item.
        """
        return self.document.text

    @property
    def document(self) -> TodoDocument:
        """The parent's list: the parent stamped, the subtask added.

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
        doc.insert(self.index, f'{self.indent}- [ ] {self.title}')
        doc.set_fields(self.index, written)
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
        """Whether the parent is given an id: it carries none."""
        return self.node.task_id is None

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
    def entries(self) -> list[str]:
        """None: an add logs no completed-log record."""
        return []

    @property
    def events(self) -> list['Event']:
        """The parent's stamp if it has one, then one `TaskAdded`.

        The `TaskAdded` lands on the stream of the subtask and names the
        parent by id.
        """
        added = AddedLine(self.entry, self.written).payload
        payload = {**added, 'parent': self.parent_id}
        event = Event(ADDED_EVENT, f'task/{self.task_id}', payload)
        return [self.stamp, event] if self.stamped else [event]

    @property
    def stamp(self) -> 'Event':
        """The `TaskUpdated` that records the parent's new id."""
        payload = {
            'delta': {'ID': [None, self.parent_id]},
            'snapshot': self.node.snapshot,
        }
        return Event(UPDATED_EVENT, f'task/{self.parent_id}', payload)


class Update:
    """The update of a task: the named fields and title over its own.

    Only the fields named are written; the rest of the line, and every
    other line of the file, stays as it was. A task with no `[ID:]` is
    given one, so the caller can name it by id from here on.
    """

    def __init__(
        self,
        task: Task,
        fields: dict[str, str],
        title: str | None = None,
    ) -> None:
        self.task = task
        self.fields = fields
        self.title = title

    def write(self) -> None:
        """Write the list, its log records and its events.

        Every value is read before the first write, so a refused write
        writes nothing.
        """
        changes = Changeset(
            self.text,
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
        """The list with the task rewritten.

        Raises
        ------
        ValueError
            Nothing is named to change, or a supplied value does not
            read.
        SelectionError
            The selector does not name exactly one open task.
        ValueError
            The task is a checklist item, or a subtask is given a field
            only the top-level task carries.
        """
        return self.document.text

    @property
    def document(self) -> TodoDocument:
        """The task's list, its line rewritten."""
        written = self.written
        index = self.node.raw_index
        doc = TodoDocument(self.task.doc.text)
        doc.set_fields(index, written)
        if self.title is not None:
            doc.set_title(index, self.title)
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
            The task is a checklist item, or a subtask is given a field
            only the top-level task carries.
        """
        node = self.task.node
        node.refuse_checklist_item()
        if self.nested:
            self.supplied.refuse_root_fields()
        return node

    @property
    def checked(self) -> dict[str, str]:
        """The named fields, read.

        Raises
        ------
        ValueError
            Neither a field nor a title is named, or a supplied value
            does not read.
        """
        if not self.fields and self.title is None:
            raise ValueError('nothing to update: name a field or a title')
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
        """What changed, from what, and where a subtask sits.

        A top-level task's ancestry is its own title, which the snapshot
        already carries.
        """
        payload: dict[str, Any] = {
            'delta': self.delta,
            'snapshot': self.node.snapshot,
        }
        if self.nested:
            payload['ancestry'] = self.ancestry.path
        return payload

    @property
    def delta(self) -> dict[str, list[Any]]:
        """Each value written against the one it replaced."""
        fields = self.node.fields
        delta = {
            name: [fields.get(name), value]
            for name, value in self.written.items()
        }
        if self.title is not None:
            delta['title'] = [self.node.title, self.title]
        return delta

    @property
    def ancestry(self) -> Ancestry:
        """The task and every task above it."""
        return Ancestry(self.task.ancestry)


class Completion:
    """The completion of a task and every ancestor it finishes (SCHEMA.md).

    A task is complete when all its children are, so checking the last
    open child completes the parent, and that may complete its own
    parent in turn. Once the top-level task is done its whole block
    goes, unless it repeats: then it stays with a recomputed `DUE`, and
    only its children go.
    """

    def __init__(self, task: Task) -> None:
        self.task = task

    def write(self) -> None:
        """Write the list, its log records and its events.

        Every value is read before the first write, so a refused write
        writes nothing.
        """
        changes = Changeset(
            self.text,
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
        if not self.root_done:
            return {
                index: {'ID': task_id} for index, task_id in self.ids.items()
            }
        if self.rescheduled is None:
            return {}
        index = self.root.raw_index
        due = self.rescheduled.isoformat()
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
        """The next due date of a finished recurring top-level task.

        Raises
        ------
        RepeatError
            Its `[REPEAT:]` does not read.
        """
        repeat = self.root.repeat
        if not (self.root_done and repeat):
            return None
        return next_due(repeat, self.task.today)

    @property
    def root(self) -> TaskNode:
        """The top-level task of the block."""
        return self.task.ancestry[0]

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
            LogEntry(self.path, ancestry, DONE_STATUS, self.task.today).text
            for ancestry in self.ancestries
                if not ancestry.node.is_checklist_item
        ]  # fmt: skip

    @property
    def events(self) -> list['Event']:
        """One `TaskCompleted` per completion, deepest first.

        The payload carries the state the task changed from, and a
        rescheduled task records its due date beside the done.
        """
        events = []
        for ancestry in self.ancestries:
            node = ancestry.node
            delta: dict[str, list[Any]] = {'done': [False, True]}
            if node is self.root and self.rescheduled is not None:
                delta['DUE'] = [node.due, self.rescheduled.isoformat()]
            payload = {
                'delta': delta,
                'snapshot': node.snapshot,
                'ancestry': ancestry.path,
            }
            stream = self.ids[ancestry.stream.raw_index]
            events.append(Event(COMPLETED_EVENT, f'task/{stream}', payload))
        return events


class Scratch:
    """The scratch of a task: its block dropped without completing it.

    The whole block goes -- the task, its notes, its children -- and
    nothing cascades: abandoning a child says nothing about its parent.
    btodo cannot tell a task accepted in an earlier session from one
    proposed in this one, so every scratch is logged (SCHEMA.md).
    """

    def __init__(self, task: Task) -> None:
        self.task = task

    def write(self) -> None:
        """Write the list, its log records and its events.

        Every value is read before the first write, so a refused write
        writes nothing.
        """
        changes = Changeset(
            self.text,
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
        entry = LogEntry(
            self.path,
            self.ancestry,
            SCRATCHED_STATUS,
            self.task.today,
        )
        return [entry.text]

    @property
    def events(self) -> list['Event']:
        """One `TaskScratched`, on the stream task's stream."""
        payload = {
            'delta': {'removed': [False, True]},
            'snapshot': self.node.snapshot,
            'ancestry': self.ancestry.path,
        }
        return [Event(SCRATCHED_EVENT, f'task/{self.stream_id}', payload)]


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
    """What one write changes in a source: a list, the log, the journal.

    A write object passes its values in the order the constructor takes
    them, so the text is read first and its refusals come first.
    """

    def __init__(
        self,
        text: str,
        entries: list[str],
        events: list['Event'],
        path: Path,
        source: Path,
    ) -> None:
        self.text = text
        self.entries = entries
        self.events = events
        self.path = path
        self.source = source

    def write(self) -> None:
        """Write the list, then the log records, then the events."""
        self.path.write_text(self.text)
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


class Event(NamedTuple):
    """One journal event a write records."""

    type: str
    stream: str
    payload: dict[str, Any]


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
        changes = Changeset(
            self.text,
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
                'snapshot': task.snapshot,
                'backfilled': True,
            }
            stream = f'task/{self.ids[task.raw_index]}'
            events.append(Event(ADDED_EVENT, stream, payload))
        return events


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


class AddedLine:
    """A task line an add writes, as its `TaskAdded` records it."""

    def __init__(self, entry: str, written: dict[str, str]) -> None:
        self.entry = entry
        self.written = written

    @property
    def payload(self) -> dict[str, Any]:
        """Each field written against nothing, and the line as written."""
        delta = {name: [None, value] for name, value in self.written.items()}
        return {
            'delta': delta,
            # Post-state, unlike every other event here: an add has no
            # prior state for a snapshot to describe. Taken from the line
            # as written, so it records the file, not the intent.
            'snapshot': self.node.snapshot,
        }

    @property
    def node(self) -> TaskNode:
        """The line alone in an open section, as the parser reads it."""
        return TodoDocument(f'{OPEN_HEADING}\n{self.entry}').tasks[0]


class LogEntry:
    """One `completed.md` record: date, category, status, ancestry."""

    def __init__(
        self,
        path: Path,
        ancestry: Ancestry,
        status: str,
        today: date,
    ) -> None:
        self.path = path
        self.ancestry = ancestry
        self.status = status
        self.today = today

    @property
    def text(self) -> str:
        """The record, the SCHEMA.md fields of the task after its path."""
        entry = (
            f'{self.today.isoformat()} | {self.path.stem} | {self.status} | '
            f'{self.ancestry.path}'
        )
        fields = self.fields
        return f'{entry} {fields}' if fields else entry

    @property
    def fields(self) -> str:
        """The SCHEMA.md fields of the task, in SCHEMA.md order."""
        ordered = self.ancestry.node.schema_fields
        return ' '.join(f'[{name}:{value}]' for name, value in ordered.items())


def task_snapshot(task: TaskNode) -> dict[str, Any]:
    """The task's full state at event time.

    Snapshots are what make a later authority flip replayable despite
    hand-edits that never reached the journal.
    """
    return {
        'title': task.title,
        'done': task.done,
        'fields': dict(task.fields),
    }


def _set_fields(
    doc: TodoDocument,
    index: int,
    updates: dict[str, str],
) -> str:
    """Apply several field edits to one line of `doc`, in order."""
    for name, value in updates.items():
        doc.set_field(index, name, value)
    return doc.lines[index]


def _is_checklist_item(task: TaskNode) -> bool:
    """A child carrying no fields: plain text, not an entity of its own.

    SCHEMA.md keeps these out of `completed.md`, and they must never be
    given an `[ID:]` -- carrying a field is exactly what distinguishes a
    subtask from a checklist item, so injecting one would silently
    promote the line.
    """
    return bool(task.indent) and not task.fields


def _stream_task(ancestry: list[TaskNode]) -> TaskNode:
    """The task whose event stream owns a mutation on `ancestry`'s target.

    Usually the target itself. A checklist item cannot hold an `[ID:]`,
    so its events are recorded against the nearest ancestor that can --
    at worst the top-level task, which never is one.
    """
    return next(
        task for task in reversed(ancestry) if not _is_checklist_item(task)
    )


def _block_indices(task: TaskNode) -> set[int]:
    """Every line the task owns: its own, its notes, its children's."""
    indices = {task.raw_index, *task.note_indices}
    for child in task.children:
        indices |= _block_indices(child)
    return indices


def _identify(task: TaskNode, ids: dict[int, str]) -> str:
    """The task's `[ID:]`, allocating one on first mediated mutation."""
    return ids.setdefault(task.raw_index, task.task_id or new_task_id())


# --- Creation -------------------------------------------------------


def _resolve_list(directory: Path, name: str) -> Path:
    """The discovered list whose filename stem is `name`.

    Parked lists count: parking opts a file out of *views*, not out of
    being written to.

    Raises
    ------
    ListError
        If no discovered list carries that stem.
    """
    lists = discover_lists(directory)
    found = next((path for path in lists if path.stem == name), None)
    if found is None:
        stems = ', '.join(path.stem for path in lists)
        raise ListError(
            f'no list named {name!r} in {directory}; available: {stems}'
        )
    return found


def _checked_values(fields: dict[str, str]) -> dict[str, str]:
    """The supplied fields, validated and normalised.

    Runs before anything is written, so a bad value costs nothing. Only
    the values with a grammar btodo actually depends on are checked --
    a `TAGS` string is free-form and cannot be wrong. `REPEAT` is left
    to `_checked_fields`, which has the day a schedule needs.
    """
    checked = dict(fields)
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
    return checked


def _checked_fields(fields: dict[str, str], today: date) -> dict[str, str]:
    """`_checked_values`, and a `REPEAT` the scheduler reads."""
    checked = _checked_values(fields)
    repeat = checked.get('REPEAT')
    if repeat is not None:
        # Validated by scheduling it and throwing the answer away: the
        # repeat parser is the only definition of a readable spec, and
        # an unreadable one must fail before a task carries it.
        next_due(repeat, today)
    return checked


def _added_payload(entry: str, written: dict[str, str]) -> dict[str, Any]:
    """The `TaskAdded` payload for a line btodo has just created."""
    return {
        'delta': {name: [None, value] for name, value in written.items()},
        # Post-state, unlike every other event here: an add has no
        # prior state for a snapshot to describe. Taken from the line
        # as written, so it records the file, not the intent.
        'snapshot': task_snapshot(
            TodoDocument(f'{OPEN_HEADING}\n{entry}').tasks[0]
        ),
    }


def _refuse_checklist_item(task: TaskNode) -> None:
    """Reject a task that carries no field of its own.

    Raises
    ------
    ValueError
        If `task` is a checklist item. Any field written to one, an
        `[ID:]` included, promotes it to a subtask (SCHEMA.md).
    """
    if _is_checklist_item(task):
        raise ValueError(
            f'{task.title!r} is a checklist item: a field written to it '
            'would promote it to a subtask'
        )


def _refuse_root_fields(fields: dict[str, str]) -> None:
    """Reject the fields a child line must not carry.

    Raises
    ------
    ValueError
        If `fields` names one. Nothing reads such a field on a child,
        so writing it would read as a change that never happened.
    """
    for name in ROOT_ONLY_FIELDS:
        if name in fields:
            raise ValueError(
                f'{name} belongs to the top-level task, not to a subtask'
            )


def add_task(
    directory: Path,
    list_name: str,
    title: str,
    fields: dict[str, str],
    today: date,
) -> tuple[Path, str]:
    """Add a top-level task to `list_name`. Returns the path and line.

    The task is appended as the last entry of the list's `## Open`
    section; every other line is left exactly as it was. Only the fields
    the caller supplied are written -- an absent `P` means 0 to the
    parser, so inventing a default would silently rank the task.
    `[ADDED:]` and `[ID:]` are always stamped: rank is computed from the
    add date (ADR 0005), and a task btodo created has no reason to wait
    for the lazy id injection the hand-written ones get.

    Parameters
    ----------
    directory : Path
        The source directory: its lists and its journal.
    list_name : str
        A list's filename stem, e.g. `chores` for `chores.md`.
    title : str
        The task title, without fields.
    fields : dict
        SCHEMA.md field names to values, as strings. Any of `P`, `LOE`,
        `DUE`, `REPEAT`, `TAGS`; all optional.
    today : date
        The add date, in the user's local day.

    Returns
    -------
    tuple of (Path, str)
        The list written to, and the task line as written.

    Raises
    ------
    ListError
        If `list_name` names no discovered list.
    ValueError
        If a supplied `P`, `LOE` or `DUE` is unreadable. `RepeatError`,
        a ValueError, covers `REPEAT`. Raised before anything is
        written.
    """
    path = _resolve_list(directory, list_name)
    checked = _checked_fields(fields, today)
    written = {
        **{name: checked[name] for name in SCHEMA_FIELDS if name in checked},
        'ADDED': today.isoformat(),
        'ID': new_task_id(),
    }
    doc = TodoDocument(path.read_text())
    # Built by the same field-append path every other mutation uses, on
    # a line that starts out carrying none.
    entry = _set_fields(doc, doc.append_open(f'- [ ] {title}'), written)
    path.write_text(doc.text)

    Journal(directory).append(
        ADDED_EVENT,
        f'task/{written["ID"]}',
        _added_payload(entry, written),
        actor='agent',
        source_file=path.name,
    )
    return path, entry


def add_subtask(
    parent: Task,
    list_name: str,
    title: str,
    fields: dict[str, str],
) -> tuple[Path, str]:
    """Add a subtask under `parent`. Returns the path and the line.

    The child lands last in its parent's block, one indent level
    deeper, and carries an `[ID:]` of its own. Indentation is the
    file's only statement of the relation; the `TaskAdded` payload
    names the parent by id. A parent carrying no `[ID:]` is stamped
    first, on an event of its own, so no line this writes goes
    unrecorded in a completed run.

    Parameters
    ----------
    parent : Task
        The parent task. It must be a task in `list_name`, and its
        source directory holds the lists and the journal.
    list_name : str
        A list's filename stem, e.g. `chores` for `chores.md`.
    title : str
        The subtask title, without fields.
    fields : dict
        SCHEMA.md field names to values, as strings. Any of `LOE`,
        `DUE`, `TAGS`; all optional. No `[ADDED:]` is stamped: rank
        reads the add date, and only a top-level task is ranked.

    Returns
    -------
    tuple of (Path, str)
        The list written to, and the subtask line as written.

    Raises
    ------
    ListError
        If `list_name` names no discovered list.
    SelectionError
        If the parent's selector does not name exactly one open task.
    ValueError
        If a supplied value is unreadable, if `fields` carries a field
        the top-level task owns, or if `parent` names a checklist item
        or a task in another list. Raised before anything is written.
    """
    directory = parent.source
    path = _resolve_list(directory, list_name)
    _refuse_root_fields(fields)
    # `REPEAT` is refused above, so no supplied value needs a day.
    checked = _checked_values(fields)

    if parent.path != path:
        raise ValueError(
            f'{parent.selector!r} names a task in {parent.path.name}, '
            f'not {path.name}'
        )

    task = parent.node
    _refuse_checklist_item(task)
    stamped = task.task_id is None
    parent_id = task.task_id or new_task_id()
    written = {
        **{name: checked[name] for name in SCHEMA_FIELDS if name in checked},
        'ID': new_task_id(),
    }
    indent = ' ' * (task.indent + SUBTASK_INDENT)

    doc = parent.doc
    if stamped:
        doc.set_field(task.raw_index, 'ID', parent_id)
    # After every line the parent owns -- its notes, its children and
    # theirs -- which makes the new child the last of them.
    index = max(_block_indices(task)) + 1
    doc.lines.insert(index, f'{indent}- [ ] {title}')
    entry = _set_fields(doc, index, written)
    path.write_text(doc.text)

    journal = Journal(directory)
    if stamped:
        journal.append(
            UPDATED_EVENT,
            f'task/{parent_id}',
            {
                'delta': {'ID': [None, parent_id]},
                'snapshot': task_snapshot(task),
            },
            actor='agent',
            source_file=path.name,
        )
    journal.append(
        ADDED_EVENT,
        f'task/{written["ID"]}',
        {**_added_payload(entry, written), 'parent': parent_id},
        actor='agent',
        source_file=path.name,
    )
    return path, entry


# --- Completion -----------------------------------------------------


def _completed_ancestries(ancestry: list[TaskNode]) -> list[list[TaskNode]]:
    """Ancestries for the target and each ancestor it finishes.

    A task is complete when all its children are checked (SCHEMA.md), so
    checking the last open child completes the parent, and that may
    complete its parent in turn. Deepest first, which is the order the
    completions get logged.
    """
    ancestries = [ancestry]
    for depth in reversed(range(len(ancestry) - 1)):
        parent, child = ancestry[depth], ancestry[depth + 1]
        if not all(c.done or c is child for c in parent.children):
            break
        ancestries.append(ancestry[: depth + 1])
    return ancestries


def _drop_lines(lines: list[str], drop: set[int]) -> list[str]:
    """Remove lines, collapsing the blank run a removed block leaves.

    Items are separated by a blank line in some lists and not in
    others, so the rule is symmetric rather than positional: only when
    the removal would leave two blanks adjacent does one of them go.
    """
    if not drop:
        return lines
    before, after = min(drop) - 1, max(drop) + 1
    if (
        before >= 0
        and after < len(lines)
        and not lines[before].strip()
        and not lines[after].strip()
    ):
        drop = drop | {after}
    return [line for index, line in enumerate(lines) if index not in drop]


def _format_ancestry(ancestry: list[TaskNode]) -> str:
    """The `Parent > Child` path SCHEMA.md logs a nested task under."""
    return ANCESTRY_SEPARATOR.join(task.title for task in ancestry)


def _log_entry(
    path: Path,
    ancestry: list[TaskNode],
    status: str,
    today: date,
) -> str:
    """One `completed.md` record: date, category, status, ancestry."""
    task = ancestry[-1]
    fields = ' '.join(
        f'[{name}:{task.fields[name]}]'
        for name in SCHEMA_FIELDS
        if name in task.fields
    )
    entry = (
        f'{today.isoformat()} | {path.stem} | {status} | '
        f'{_format_ancestry(ancestry)}'
    )
    return f'{entry} {fields}' if fields else entry


def _append_log(directory: Path, entries: list[str]) -> None:
    """Append to `completed.md`, which is append-only (SCHEMA.md)."""
    if not entries:
        return
    path = directory / COMPLETED_LOG
    existing = path.read_text() if path.exists() else ''
    lead = '' if not existing or existing.endswith('\n') else '\n'
    with path.open('a', encoding='utf-8') as handle:
        handle.write(lead + '\n'.join(entries) + '\n')


def _mark_done(raw: str) -> str:
    """Check the box on a raw line, leaving the rest of it alone."""
    return raw.replace('- [ ]', '- [x]', 1)


def complete(task: Task) -> list[str]:
    """Complete the task. Returns the log entries.

    Follows SCHEMA.md: the completion is logged to `completed.md` with
    its full `Parent > Child` ancestry, the item is checked off, and the
    whole block goes once the top-level task is done -- unless it
    repeats, in which case it stays with a recomputed `DUE`. Completing
    the last open child completes its parent too, so a finished block
    never lingers half-checked.

    Parameters
    ----------
    task : Task
        The task a selector names. Its source directory holds the
        lists, `completed.md` and the journal, and its day is the
        completion date, in the user's local day.

    Returns
    -------
    list of str
        The `completed.md` entries written, deepest task first. Empty
        when the target was a checklist item, which SCHEMA.md does not
        log.

    Raises
    ------
    SelectionError
        If the task's selector does not name exactly one open task.
    RepeatError
        If a completed recurring task carries a `[REPEAT:]` btodo
        cannot read. Raised before anything is written.
    """
    directory, today = task.source, task.today
    ancestries = _completed_ancestries(task.ancestry)
    root = task.ancestry[0]
    root_done = len(ancestries[-1]) == 1
    rescheduled = (
        next_due(root.repeat, today) if root_done and root.repeat else None
    )

    ids: dict[int, str] = {}
    streams = [
        _identify(_stream_task(ancestry), ids) for ancestry in ancestries
    ]
    doc = task.doc

    if root_done:
        drop = _block_indices(root)
        if rescheduled is not None:
            # The recurrence is the same task rescheduled, so it keeps
            # its id, its notes and its `[ADDED:]`, which ADR 0005
            # writes once and never updates. Children do not carry
            # over.
            drop -= {root.raw_index, *root.note_indices}
            _set_fields(
                doc,
                root.raw_index,
                {
                    'DUE': rescheduled.isoformat(),
                    'ID': ids[root.raw_index],
                },
            )
        doc.lines = _drop_lines(doc.lines, drop)
    else:
        for index, task_id in ids.items():
            doc.set_field(index, 'ID', task_id)
        for ancestry in ancestries:
            index = ancestry[-1].raw_index
            doc.lines[index] = _mark_done(doc.lines[index])

    entries = [
        _log_entry(task.path, ancestry, DONE_STATUS, today)
        for ancestry in ancestries
        if not _is_checklist_item(ancestry[-1])
    ]

    task.path.write_text(doc.text)
    _append_log(directory, entries)

    journal = Journal(directory)
    for ancestry, stream in zip(ancestries, streams):
        node = ancestry[-1]
        delta: dict[str, list[Any]] = {'done': [False, True]}
        if node is root and rescheduled is not None:
            delta['DUE'] = [root.due, rescheduled.isoformat()]
        journal.append(
            COMPLETED_EVENT,
            f'task/{stream}',
            {
                'delta': delta,
                # Pre-state, as everywhere here: the delta says what
                # changed, the snapshot says what it changed from.
                'snapshot': task_snapshot(node),
                'ancestry': _format_ancestry(ancestry),
            },
            actor='agent',
            source_file=task.path.name,
        )

    return entries


def scratch(task: Task) -> list[str]:
    """Drop the task without completing it.

    The whole block goes -- the task, its notes, its children -- and
    nothing cascades: abandoning one child says nothing about its
    parent, which stays open.

    SCHEMA.md logs a scratch only for a task genuinely accepted in an
    earlier session, and silently drops proposals culled in the session
    that produced them. btodo cannot see that difference; by the time an
    item is written to a list it can only be treated as accepted, so
    every scratch is logged.

    Parameters
    ----------
    task : Task
        The task a selector names. Its source directory holds the
        lists, `completed.md` and the journal, and its day is the date
        the task was abandoned, in the user's local day.

    Returns
    -------
    list of str
        The one `completed.md` entry written, or none for a checklist
        item, which SCHEMA.md does not log.

    Raises
    ------
    SelectionError
        If the task's selector does not name exactly one open task.
    """
    directory, today = task.source, task.today
    node = task.node
    stream = _stream_task(task.ancestry)
    stream_id = stream.task_id or new_task_id()

    doc = task.doc
    if stream is not node:
        # A checklist item cannot hold an id, so the event belongs to
        # the ancestor's stream and the ancestor's line is the one that
        # has to carry it.
        doc.set_field(stream.raw_index, 'ID', stream_id)
    doc.lines = _drop_lines(doc.lines, _block_indices(node))

    entries = (
        []
        if _is_checklist_item(node)
        else [_log_entry(task.path, task.ancestry, SCRATCHED_STATUS, today)]
    )

    task.path.write_text(doc.text)
    _append_log(directory, entries)

    Journal(directory).append(
        SCRATCHED_EVENT,
        f'task/{stream_id}',
        {
            'delta': {'removed': [False, True]},
            'snapshot': task_snapshot(node),
            'ancestry': _format_ancestry(task.ancestry),
        },
        actor='agent',
        source_file=task.path.name,
    )
    return entries


# --- Update ---------------------------------------------------------


def update_task(
    task: Task,
    fields: dict[str, str],
    title: str | None = None,
) -> tuple[Path, str]:
    """Rewrite the task. Returns the path and line.

    Only the fields named are written; the rest of the line, and every
    other line in the file, is left exactly as it was. An `[ID:]` is
    stamped where the task has none, so the caller can address it by id
    from here on.

    Subtasks are reached at any depth, and the event then carries the
    `Parent > Child` ancestry. A checklist item is refused: writing a
    field to one promotes it to a subtask (SCHEMA.md).

    Parameters
    ----------
    task : Task
        The task a selector names. Its source directory holds the
        lists and the journal, and its day validates a `REPEAT`.
    fields : dict
        SCHEMA.md field names to values, as strings.
    title : str, optional
        A new title. The fields on the line keep their positions.

    Returns
    -------
    tuple of (Path, str)
        The list written to, and the task line as written.

    Raises
    ------
    SelectionError
        If the task's selector does not name exactly one open task.
    ValueError
        If nothing was named to change, if the task is a checklist
        item, if `fields` carries a field the top-level task owns, or
        if a supplied value is unreadable. Raised before anything is
        written.
    """
    if not fields and title is None:
        raise ValueError('nothing to update: name a field or a title')
    checked = _checked_fields(fields, task.today)

    node = task.node
    nested = len(task.ancestry) > 1
    _refuse_checklist_item(node)
    if nested:
        _refuse_root_fields(fields)

    task_id = node.task_id or new_task_id()
    written = dict(checked)
    if not node.task_id:
        written['ID'] = task_id
    doc = task.doc
    entry = _set_fields(doc, node.raw_index, written)
    if title is not None:
        entry = doc.set_title(node.raw_index, title)

    delta: dict[str, list[Any]] = {
        name: [node.fields.get(name), value] for name, value in written.items()
    }
    if title is not None:
        delta['title'] = [node.title, title]

    payload: dict[str, Any] = {
        'delta': delta,
        # Pre-state, as everywhere but an add: the delta says what
        # changed, the snapshot says what it changed from.
        'snapshot': task_snapshot(node),
    }
    if nested:
        # Only a child needs it. A top-level task's ancestry is its own
        # title, which the snapshot already carries.
        payload['ancestry'] = _format_ancestry(task.ancestry)

    task.path.write_text(doc.text)

    Journal(task.source).append(
        UPDATED_EVENT,
        f'task/{task_id}',
        payload,
        actor='agent',
        source_file=task.path.name,
    )
    return task.path, entry


# --- Backfill -------------------------------------------------------


def _needs_added(task: TaskNode) -> bool:
    """Open top-level tasks with no `[ADDED:]`, whose dates all parse.

    A task whose date fields cannot be read is never touched. Template
    files carry placeholders like `[DUE:YYYY-MM-DD]`, and rewriting a
    line btodo cannot interpret is exactly the corruption the round-trip
    guarantee exists to prevent.
    """
    if task.done or task.indent or task.added:
        return False
    return all(
        parse_date(task.fields[name]) is not None
        for name in DATE_FIELDS
        if name in task.fields
    )


def backfill_file(path: Path, today: date, journal: Journal) -> list[str]:
    """Stamp `[ADDED:today]` where it is missing. Returns the titles.

    `today` is the migration date, not the real add date -- that is not
    recoverable from the files (ADR 0005). Age accrues from here.
    """
    doc = TodoDocument(path.read_text())
    stamped: list[str] = []

    for task in doc.tasks:
        if not _needs_added(task):
            continue

        snapshot = task_snapshot(task)
        task_id = task.task_id or new_task_id()
        updates = {'ADDED': today.isoformat()}
        if not task.task_id:
            updates['ID'] = task_id

        _set_fields(doc, task.raw_index, updates)
        stamped.append(task.title)

        journal.append(
            ADDED_EVENT,
            f'task/{task_id}',
            {
                'delta': {'ADDED': [None, today.isoformat()]},
                'snapshot': snapshot,
                # The date is the migration's, not the task's. A replay
                # must not read it as an observed fact.
                'backfilled': True,
            },
            actor='agent',
            source_file=path.name,
        )

    if stamped:
        path.write_text(doc.text)
    return stamped


def backfill_all(directory: Path, today: date) -> dict[str, list[str]]:
    """Backfill every discovered list in `directory`.

    Parked lists are included: they opt out of views, not of existing,
    and an unparked item should carry an add date.
    """
    journal = Journal(directory)
    result = {}
    for path in discover_lists(directory):
        stamped = backfill_file(path, today, journal)
        if stamped:
            result[path.name] = stamped
    return result
