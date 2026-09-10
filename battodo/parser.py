"""Read and write SCHEMA.md-format todo lists.

`TodoDocument` keeps every source line verbatim and records only
*indices* into that line list, so its text gives the source back byte
for byte. Every mutation edits one raw line where it stands. Field
order varies from line to line, so a line rebuilt from its parsed
fields would reorder the fields of every line it touched.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from functools import cached_property

FIELD_RE = re.compile(r'\[(P|LOE|DUE|BUMPED|ADDED|REPEAT|TAGS|ID):([^\]]*)\]')
CHECKBOX_RE = re.compile(r'^(\s*)- \[([ xX])\]\s?(.*)$')
OPEN_HEADING = '## Open'


@dataclass
class TaskNode:
    """One `- [ ]` line, plus its children and note lines."""

    raw_index: int
    indent: int
    done: bool
    title: str
    fields: dict[str, str]
    raw: str = ''
    children: list['TaskNode'] = field(default_factory=list)
    note_indices: list[int] = field(default_factory=list)

    @property
    def loe(self) -> int | None:
        value = self.fields.get('LOE')
        return int(value) if value else None

    @property
    def due(self) -> str | None:
        return self.fields.get('DUE')

    @property
    def added(self) -> str | None:
        """When the task entered the list, per ADR 0005.

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
        return [tag for tag in raw.split(',') if tag] if raw else []

    @property
    def is_subtask(self) -> bool:
        """A child carrying at least one field, per SCHEMA.md.

        Children with no fields are checklist items.
        """
        return bool(self.indent) and bool(self.fields)


class TodoDocument:
    """One SCHEMA.md-format todo list, held as the text it was read from.

    Tasks record only indices into `lines`, the document's editable
    state, so `text` gives the source back byte for byte until a write.
    `set_field`, `set_title` and `append_open` are the edits the
    document performs itself, each rewriting one raw line where it
    stands.
    """

    def __init__(self, source: str) -> None:
        self.source = source

    @cached_property
    def lines(self) -> list[str]:
        """The source text, split into verbatim lines."""
        return self.source.split('\n')

    @cached_property
    def tasks(self) -> list[TaskNode]:
        """The open-section task tree, in file order."""
        tasks: list[TaskNode] = []
        in_open = False
        # stack of (indent, task) for the current ancestry
        stack: list[tuple[int, TaskNode]] = []

        for index, raw in enumerate(self.lines):
            stripped = raw.strip()

            if stripped == OPEN_HEADING:
                in_open = True
                stack = []
                continue
            if stripped.startswith('## '):
                in_open = False
                stack = []
                continue
            if not in_open:
                continue

            match = CHECKBOX_RE.match(raw)
            if match is None:
                if stripped and not stripped.startswith('<!--') and stack:
                    stack[-1][1].note_indices.append(index)
                continue

            indent = len(match.group(1))
            body = match.group(3)
            task = TaskNode(
                raw_index=index,
                indent=indent,
                done=match.group(2) in 'xX',
                title=_clean_title(body),
                fields=_parse_fields(body),
                raw=raw,
            )

            while stack and stack[-1][0] >= indent:
                stack.pop()
            if stack:
                stack[-1][1].children.append(task)
            else:
                tasks.append(task)
            stack.append((indent, task))

        return tasks

    @property
    def text(self) -> str:
        """The list as it stands; the source until a method writes."""
        return '\n'.join(self.lines)

    def set_field(self, index: int, name: str, value: str) -> str:
        """Set `name` to `value` on the line at `index`.

        An existing field is replaced where it stands; a new one is
        appended after the last field. Either way every other field
        keeps its position, which is what the round-trip guarantee
        rests on -- field order varies line to line in hand-edited
        files.

        Returns
        -------
        str
            The edited line.
        """
        raw = self.lines[index]
        pattern = rf'\[{name}:[^\]]*\]'
        if re.search(pattern, raw):
            edited = re.sub(pattern, f'[{name}:{value}]', raw, count=1)
        else:
            edited = f'{raw.rstrip()} [{name}:{value}]'
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

        The insertion point is after the last non-blank line of the
        section, so the entry follows whatever the previous item ended
        with -- its notes, its children -- and the blank run before the
        next heading stays where it is.

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
        start = next(
            index
            for index, line in enumerate(self.lines)
            if line.strip() == OPEN_HEADING
        )
        end = next(
            (
                index
                for index in range(start + 1, len(self.lines))
                if self.lines[index].strip().startswith('## ')
            ),
            len(self.lines),
        )
        # `start` is itself non-blank, so an empty section appends
        # directly under the heading rather than falling off the front
        # of the file.
        last = max(
            index for index in range(start, end) if self.lines[index].strip()
        )
        self.lines.insert(last + 1, entry)
        return last + 1


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


def _parse_fields(text: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in FIELD_RE.finditer(text)}


def _clean_title(body: str) -> str:
    return FIELD_RE.sub('', body).strip()
