"""Read and write SCHEMA.md-format todo lists.

`TodoDocument` keeps every source line verbatim and records only
*indices* into that line list, so its text gives the source back byte
for byte. A field edit rewrites one raw line where it stands. Field
order varies from line to line, so a line rebuilt from its parsed
fields would reorder the fields of every line it touched.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from functools import cached_property
from itertools import pairwise
from typing import Any

FIELD_NAMES: tuple[str, ...] = (
    'P',
    'LOE',
    'DUE',
    'BUMPED',
    'ADDED',
    'REPEAT',
    'TAGS',
    'ID',
)
FIELD_RE = re.compile(rf'\[({"|".join(FIELD_NAMES)}):([^\]]*)\]')
CHECKBOX_RE = re.compile(r'^(\s*)- \[([ xX])\]\s?(.*)$')
OPEN_HEADING = '## Open'
# SCHEMA.md's own field grammar, in SCHEMA.md's order. `BUMPED` is
# retired; `ADDED` and `ID` are btodo extensions and so are not in it.
# Whatever btodo authors -- a `completed.md` record, a brand new task
# line -- is written in this order, which is what makes those lines
# canonical where hand-written ones keep whatever order they came with.
SCHEMA_FIELDS = ('P', 'LOE', 'DUE', 'REPEAT', 'TAGS')
DATE_FIELDS = ('DUE',)
# How far a description line indents past its task line: under the
# title, clear of the checkbox.
DESCRIPTION_INDENT = len('- [ ] ')
ANCESTRY_SEPARATOR = ' > '


@dataclass
class TaskNode:
    """One `- [ ]` line, plus its children and note lines.

    A note line is a description line: its text, stripped, is one line
    of the task's description.
    """

    raw_index: int
    indent: int
    done: bool
    title: str
    fields: dict[str, str]
    raw: str = ''
    children: list['TaskNode'] = field(default_factory=list)
    note_indices: list[int] = field(default_factory=list)
    description_lines: list[str] = field(default_factory=list)

    @property
    def loe(self) -> int | None:
        """The level of effort, or None when the value is unreadable."""
        value = self.fields.get('LOE')
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    @property
    def due(self) -> str | None:
        return self.fields.get('DUE')

    @property
    def added(self) -> str | None:
        """The task's entry day, rewritten on a reschedule (ADR 0026).

        Absent on every hand-written task and on everything predating
        the field, so readers must tolerate None.
        """
        return self.fields.get('ADDED')

    @property
    def repeat(self) -> str | None:
        return self.fields.get('REPEAT')

    @property
    def task_id(self) -> str | None:
        return self.fields.get('ID')

    @property
    def tags(self) -> list[str]:
        raw = self.fields.get('TAGS')
        if not raw:
            return []
        return [
            tag
            for tag in raw.split(',')
                if tag
        ]  # fmt: skip

    @property
    def is_subtask(self) -> bool:
        """A child carrying at least one field, per SCHEMA.md.

        Children with no fields are checklist items.
        """
        return bool(self.indent) and bool(self.fields)

    @property
    def is_checklist_item(self) -> bool:
        """A child carrying no fields: plain text, not an entity of its own.

        SCHEMA.md keeps these out of `completed.md`, and they must never
        be given an `[ID:]` -- carrying a field is exactly what
        distinguishes a subtask from a checklist item, so injecting one
        would silently promote the line.
        """
        return bool(self.indent) and not self.fields

    @property
    def block(self) -> set[int]:
        """Every line the task owns: its own, its notes, its children's."""
        owned = {self.raw_index, *self.note_indices}
        for child in self.children:
            owned |= child.block
        return owned

    @property
    def ancestries(self) -> list[list['TaskNode']]:
        """The task, then each task below it, each with its ancestry.

        In file order. Each ancestry runs from this task down.
        """
        found = [[self]]
        for child in self.children:
            found.extend([self, *below] for below in child.ancestries)
        return found

    @property
    def repeating_subtasks(self) -> list['TaskNode']:
        """The open tasks below this one that repeat, at any depth.

        In file order. A `[REPEAT:]` with nothing in it is no repeat.
        """
        found = []
        for child in self.children:
            if child.repeat and not child.done:
                found.append(child)
            found.extend(child.repeating_subtasks)
        return found

    @property
    def description(self) -> str | None:
        """The description lines joined by newlines, or None if none."""
        return join_description(self.description_lines)

    @property
    def snapshot(self) -> dict[str, Any]:
        """The task's full state, as a journal event records it.

        Each child nests in it as its own snapshot. Snapshots are what
        make a later authority flip replayable despite hand-edits that
        never reached the journal.
        """
        snapshot: dict[str, Any] = {
            'title': self.title,
            'done': self.done,
            'fields': dict(self.fields),
        }
        description = self.description
        if description is not None:
            snapshot['description'] = description
        if self.children:
            snapshot['children'] = [child.snapshot for child in self.children]
        return snapshot

    def listed_snapshot(self, list_name: str) -> dict[str, Any]:
        """The snapshot of the task and the list that holds it.

        A journal event names the list of its task by the filename stem.
        """
        return {**self.snapshot, 'list': list_name}

    @property
    def schema_fields(self) -> dict[str, str]:
        """The fields SCHEMA.md names, in its order."""
        return {
            name: self.fields[name]
            for name in SCHEMA_FIELDS
                if name in self.fields
        }  # fmt: skip

    @property
    def needs_added(self) -> bool:
        """Whether an open top-level task with no `[ADDED:]` takes one.

        A task whose date fields cannot be read is never touched.
        Template files carry placeholders like `[DUE:YYYY-MM-DD]`, and
        rewriting a line btodo cannot interpret is exactly the
        corruption the round-trip guarantee exists to prevent.
        """
        if self.done or self.indent or self.added:
            return False
        return all(
            parse_date(self.fields[name]) is not None
            for name in DATE_FIELDS
                if name in self.fields
        )  # fmt: skip

    def refuse_checklist_item(self) -> None:
        """Refuse a field written to the task if it is a checklist item.

        Raises
        ------
        ValueError
            The task is a checklist item. Any field written to one, an
            `[ID:]` included, promotes it to a subtask (SCHEMA.md).
        """
        if self.is_checklist_item:
            raise ValueError(
                f'{self.title!r} is a checklist item: a field written to it '
                'would promote it to a subtask'
            )

    def refuse_attributes(self, attrs: dict[str, str] | None) -> None:
        """Refuse attributes given to the task if it is a checklist item.

        Raises
        ------
        ValueError
            The task is a checklist item and `attrs` holds any. A
            checklist item takes no attributes (ADR 0020).
        """
        if attrs and self.is_checklist_item:
            raise ValueError('a checklist item takes no attributes')


class Ancestry:
    """A task and every task above it, outermost first."""

    def __init__(self, tasks: list[TaskNode]) -> None:
        self.tasks = tasks

    @property
    def node(self) -> TaskNode:
        """The task the ancestry ends at."""
        return self.tasks[-1]

    @property
    def nested(self) -> bool:
        """Whether the task sits below another task, at any depth."""
        return len(self.tasks) > 1

    @property
    def path(self) -> str:
        """The `Parent > Child` path SCHEMA.md logs a nested task under."""
        return ANCESTRY_SEPARATOR.join(task.title for task in self.tasks)

    @property
    def stream(self) -> TaskNode:
        """The task whose event stream owns a write to the last task.

        Usually that task itself. A checklist item cannot hold an
        `[ID:]`, so its events are recorded against the nearest ancestor
        that can -- at worst the top-level task, which never is one.
        """
        return next(
            task
            for task in reversed(self.tasks)
                if not task.is_checklist_item
        )  # fmt: skip


class TodoDocument:
    """One SCHEMA.md-format todo list, held as the text it was read from.

    Tasks record only indices into `lines`, the document's editable
    state, so `text` gives the source back byte for byte until a write.
    The document performs every edit of a list itself: `set_fields`,
    `set_field`, `set_title` and `mark_done` rewrite one raw line where
    it stands, `append_open` and `insert` add a line,
    `insert_description` adds description lines, `set_description`
    replaces them, and `drop` removes lines. An edit leaves `tasks` as it
    was read.
    """

    def __init__(self, source: str) -> None:
        self.source = source

    @cached_property
    def lines(self) -> list[str]:
        """The source text, split into verbatim lines."""
        return self.source.split('\n')

    @cached_property
    def tasks(self) -> list[TaskNode]:
        """The open-section task tree, in file order.

        Each node goes under the nearest earlier node of its section
        with a lower indent. A node with none is a top-level task.
        """
        tasks: list[TaskNode] = []
        for nodes in self.section_nodes:
            for position, node in enumerate(nodes):
                above = reversed(nodes[:position])
                parent = next(
                    (
                        earlier
                        for earlier in above
                            if earlier.indent < node.indent
                    ),
                    None,
                )  # fmt: skip
                siblings = tasks if parent is None else parent.children
                siblings.append(node)
        return tasks

    @property
    def section_nodes(self) -> list[list[TaskNode]]:
        """A node per task line, one list per `## Open` section.

        Each list is flat and in file order. A note line goes on the
        nearest task line above it in its section; a note line with no
        task above it is dropped.
        """
        return [section.nodes for section in self.sections]

    @property
    def sections(self) -> list['Section']:
        """A `Section` per `## Open` heading, in file order."""
        return [Section(self.lines, indices) for indices in self.open_sections]

    @property
    def open_sections(self) -> list[list[int]]:
        """The line indices under each `## Open` heading, in file order.

        A section ends at the next `## ` heading or at the end of the
        file.
        """
        bounds = [*self.heading_indices, len(self.lines)]
        return [
            list(range(start + 1, stop))
            for start, stop in pairwise(bounds)
                if self.lines[start].strip() == OPEN_HEADING
        ]  # fmt: skip

    @property
    def heading_indices(self) -> list[int]:
        """The index of every `## ` heading line, in file order."""
        return [
            index
            for index, line in enumerate(self.lines)
                if line.strip().startswith('## ')
        ]  # fmt: skip

    @property
    def ancestries(self) -> list[list[TaskNode]]:
        """Every open task at any depth, each with its ancestry.

        In file order. Each ancestry runs from a top-level task down.
        """
        return [
            ancestry
            for task in self.tasks
            for ancestry in task.ancestries
        ]  # fmt: skip

    @property
    def text(self) -> str:
        """The list as it stands; the source until a method writes."""
        return '\n'.join(self.lines)

    def set_fields(self, index: int, fields: Mapping[str, str | None]) -> str:
        """Set each of `fields` on the line at `index`, in order.

        Returns
        -------
        str
            The edited line.
        """
        for name, value in fields.items():
            self.set_field(index, name, value)
        return self.lines[index]

    def set_field(self, index: int, name: str, value: str | None) -> str:
        """Set `name` to `value` on the line at `index`.

        An existing field is replaced where it stands; a new one is
        appended after the last field. Either way every other field
        keeps its position, which is what the round-trip guarantee
        rests on -- field order varies line to line in hand-edited
        files. A None value removes each copy of the field and the space
        before it.

        Returns
        -------
        str
            The edited line.
        """
        raw = self.lines[index]
        field = rf'\[{name}:[^\]]*\]'
        if value is None:
            edited = re.sub(f' ?{field}', '', raw)
        else:
            written = f'[{name}:{value}]'
            found = re.search(field, raw)
            if found:
                edited = f'{raw[: found.start()]}{written}{raw[found.end() :]}'
            else:
                edited = f'{raw.rstrip()} {written}'
        self.lines[index] = edited
        return edited

    def set_title(self, index: int, title: str) -> str:
        """Replace the title of the task line at `index`.

        Only the text before the first field changes.

        Returns
        -------
        str
            The edited line.

        Raises
        ------
        ValueError
            The line is not a task line. A note or a heading carries no
            title to set.
        """
        raw = self.lines[index]
        match = CHECKBOX_RE.match(raw)
        if match is None:
            raise ValueError(f'not a task line: {raw!r}')
        indent, mark, body = match.groups()
        found = FIELD_RE.search(body)
        tail = body[found.start() :] if found else ''
        edited = f'{indent}- [{mark}] {f"{title} {tail}".rstrip()}'
        self.lines[index] = edited
        return edited

    def append_open(self, entry: str) -> int:
        """Insert `entry` as the last entry of the `## Open` section.

        Returns
        -------
        int
            The index `entry` now occupies.

        Raises
        ------
        StopIteration
            There is no `## Open` heading. Carrying one is what makes a
            file a todo list at all, so `discover_lists` has already
            ruled this out for every caller that goes through it.
        """
        index = self.open_end
        self.insert(index, entry)
        return index

    @property
    def open_end(self) -> int:
        """Where an entry appended to the `## Open` section goes.

        After the last non-blank line of the section, so the entry
        follows whatever the previous item ended with -- its notes, its
        children -- and the blank run before the next heading stays
        where it is.

        Raises
        ------
        StopIteration
            There is no `## Open` heading.
        """
        start = next(
            index
            for index, line in enumerate(self.lines)
                if line.strip() == OPEN_HEADING
        )  # fmt: skip
        stop = len(self.lines)
        end = next(
            (
                index
                for index in range(start + 1, stop)
                    if self.lines[index].strip().startswith('## ')
            ),
            stop,
        )  # fmt: skip
        # `start` is itself non-blank, so an empty section appends
        # directly under the heading rather than falling off the front
        # of the file.
        last = max(
            index
            for index in range(start, end)
                if self.lines[index].strip()
        )  # fmt: skip
        return last + 1

    def insert(self, index: int, line: str) -> None:
        """Insert `line` at `index`. Every later line moves down one."""
        self.lines.insert(index, line)

    def insert_description(self, index: int, lines: list[str]) -> None:
        """Insert `lines` as description lines of the task line at `index`.

        They go directly under the task line, in order, each indented
        DESCRIPTION_INDENT past the task line's own indent.
        """
        raw = self.lines[index]
        indent = raw[: len(raw) - len(raw.lstrip())]
        lead = indent + ' ' * DESCRIPTION_INDENT
        for offset, line in enumerate(lines, start=1):
            self.insert(index + offset, f'{lead}{line}')

    def set_description(self, node: TaskNode, lines: list[str]) -> None:
        """Replace the description lines of `node` with `lines`.

        `node` is a task as this document read it.
        """
        self.drop(set(node.note_indices))
        self.insert_description(node.raw_index, lines)

    def drop(self, indices: set[int]) -> None:
        """Remove the lines at `indices`.

        Items are separated by a blank line in some lists and not in
        others, so only when the removal would leave two blank lines
        together does the one after the removed span go too.
        """
        if not indices:
            return
        before, after = min(indices) - 1, max(indices) + 1
        blank_pair = (
            before >= 0
            and after < len(self.lines)
            and not self.lines[before].strip()
            and not self.lines[after].strip()
        )
        gone = indices | {after} if blank_pair else indices
        self.lines[:] = [
            line
            for index, line in enumerate(self.lines)
                if index not in gone
        ]  # fmt: skip

    def mark_done(self, index: int) -> None:
        """Check the box of the task line at `index`."""
        self.lines[index] = self.lines[index].replace('- [ ]', '- [x]', 1)

    def mark_open(self, index: int) -> None:
        """Clear the box of the task line at `index`, either case of x."""
        self.lines[index] = re.sub(
            r'^(\s*- \[)[xX]\]', r'\1 ]', self.lines[index]
        )


@dataclass
class Section:
    """The lines under one `## Open` heading.

    `lines` holds every line of the document, and `indices` addresses
    the lines of the section.
    """

    lines: list[str]
    indices: list[int]

    @property
    def nodes(self) -> list[TaskNode]:
        """A node per task line, with the note lines below it.

        In file order. A note line before the first task line of the
        section belongs to no node.
        """
        return [
            TaskNode(
                raw_index=line.index,
                indent=line.indent,
                done=line.done,
                title=line.title,
                fields=line.fields,
                raw=line.raw,
                note_indices=notes,
                description_lines=description,
            )
            for line, notes, description in zip(
                self.task_lines, self.notes, self.descriptions
            )
        ]

    @property
    def task_lines(self) -> list['TaskLine']:
        """A `TaskLine` per checkbox line of the section, in file order."""
        return [
            TaskLine(index, self.lines[index])
            for index in self.indices
                if CHECKBOX_RE.match(self.lines[index])
        ]  # fmt: skip

    @property
    def notes(self) -> list[list[int]]:
        """The note line indices below each task line, in file order.

        The notes of a task line run up to its stop. A line with text
        there is a note.
        """
        texts = self.texts
        return [
            [
                index
                for index in range(line.index + 1, stop)
                    if index in texts
            ]
            for line, stop in zip(self.task_lines, self.stops)
        ]  # fmt: skip

    @property
    def texts(self) -> dict[int, str]:
        """The stripped text of each section line, by index.

        A blank line and a `<!--` comment line hold no text.
        """
        stripped = {index: self.lines[index].strip() for index in self.indices}
        return {
            index: text
            for index, text in stripped.items()
                if text and not text.startswith('<!--')
        }  # fmt: skip

    @property
    def stops(self) -> list[int]:
        """Where the note range of each task line stops.

        At the next task line, or at the end of the section for the last
        one.
        """
        starts = [line.index for line in self.task_lines]
        return [stop for _, stop in pairwise([*starts, self.end])]

    @property
    def end(self) -> int:
        """The index after the last line of the section, 0 if it is empty."""
        return max(self.indices, default=-1) + 1

    @property
    def descriptions(self) -> list[list[str]]:
        """The text of the notes of each task line, in file order."""
        texts = self.texts
        return [[texts[index] for index in notes] for notes in self.notes]


@dataclass
class TaskLine:
    """One checkbox line: its index in the document and its raw text."""

    index: int
    raw: str

    @property
    def checkbox(self) -> re.Match[str]:
        """The `CHECKBOX_RE` match of the line.

        Raises
        ------
        ValueError
            The line is not a task line.
        """
        found = CHECKBOX_RE.match(self.raw)
        if found is None:
            raise ValueError(f'not a task line: {self.raw!r}')
        return found

    @property
    def indent(self) -> int:
        """The width of the indent before the checkbox."""
        return len(self.checkbox.group(1))

    @property
    def done(self) -> bool:
        """Whether the box carries an x, in either case."""
        return self.checkbox.group(2) in 'xX'

    @property
    def body(self) -> str:
        """The text after the checkbox: the title and the fields."""
        return self.checkbox.group(3)

    @property
    def title(self) -> str:
        """The body without its fields."""
        return _clean_title(self.body)

    @property
    def fields(self) -> dict[str, str]:
        """The fields of the body, by name."""
        return _parse_fields(self.body)


def parse_date(value: str | None) -> date | None:
    """Parse an ISO date field, tolerating placeholders.

    Hand-edited files and templates carry literal placeholder text such
    as `[DUE:YYYY-MM-DD]`. Reading one must never raise: btodo operates
    on files people type into by hand.
    """
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def join_description(lines: list[str]) -> str | None:
    """The description `lines` hold, joined by newlines, or None if none."""
    return '\n'.join(lines) or None


def _parse_fields(text: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in FIELD_RE.finditer(text)}


def _clean_title(body: str) -> str:
    return FIELD_RE.sub('', body).strip()
