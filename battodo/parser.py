"""Parse and serialize SCHEMA.md-format todo lists.

The parser keeps every source line verbatim and records only *indices*
into that line list. Serializing rejoins the untouched lines, so
parse -> serialize is byte-identical for any input. Mutations replace a
single line via `set_field`, which edits the raw text in place. Field
order varies from line to line, so a serializer that rebuilt a line
from its parsed fields would rewrite every line it touched.
"""

import re
from dataclasses import dataclass, field
from datetime import date

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


@dataclass
class TodoFile:
    """A parsed list: verbatim lines plus the open-section task tree."""

    lines: list[str]
    tasks: list[TaskNode] = field(default_factory=list)


def set_field(raw: str, name: str, value: str) -> str:
    """Return the task line `raw` with `name` set to `value`.

    An existing field is replaced where it stands; a new one is
    appended after the last field. Either way every other field keeps
    its position, which is what the round-trip guarantee rests on --
    field order varies line to line in hand-edited files.
    """
    pattern = rf'\[{name}:[^\]]*\]'
    if re.search(pattern, raw):
        return re.sub(pattern, f'[{name}:{value}]', raw, count=1)
    return f'{raw.rstrip()} [{name}:{value}]'


def set_title(raw: str, title: str) -> str:
    """Return the task line `raw` with its title replaced.

    Only the text before the first field changes. Every field keeps its
    text and its position, as `set_field` leaves them.

    Raises
    ------
    ValueError
        If `raw` is not a task line. A note or a heading carries no
        title to set.
    """
    match = CHECKBOX_RE.match(raw)
    if match is None:
        raise ValueError(f'not a task line: {raw!r}')
    indent, mark, body = match.groups()
    field = FIELD_RE.search(body)
    tail = body[field.start() :] if field else ''
    text = f'{title} {tail}'.rstrip()
    return f'{indent}- [{mark}] {text}'


def append_open(lines: list[str], entry: str) -> list[str]:
    """Return `lines` with `entry` as the last entry of `## Open`.

    The insertion point is after the last non-blank line of the section,
    so the entry follows whatever the previous item ended with -- its
    notes, its children -- and the blank run before the next heading is
    left where it is. Every existing line keeps its text and its order,
    which is what the round-trip guarantee rests on.

    Parameters
    ----------
    lines : list of str
        A parsed file's verbatim lines.
    entry : str
        The task line to insert, already formatted.

    Returns
    -------
    list of str
        A new list; the argument is not modified.

    Raises
    ------
    StopIteration
        If there is no `## Open` heading. Carrying one is what makes a
        file a todo list at all, so `discover_lists` has already ruled
        this out for every caller that goes through it.
    """
    start = next(
        index
        for index, line in enumerate(lines)
        if line.strip() == OPEN_HEADING
    )
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if lines[index].strip().startswith('## ')
        ),
        len(lines),
    )
    # `start` is itself non-blank, so an empty section appends directly
    # under the heading rather than falling off the front of the file.
    last = max(index for index in range(start, end) if lines[index].strip())
    return [*lines[: last + 1], entry, *lines[last + 1 :]]


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


def parse(text: str) -> TodoFile:
    """Parse `text` into a TodoFile, retaining every line verbatim."""
    lines = text.split('\n')
    doc = TodoFile(lines=lines)
    in_open = False
    # stack of (indent, task) for the current ancestry
    stack: list[tuple[int, TaskNode]] = []

    for index, raw in enumerate(lines):
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
            doc.tasks.append(task)
        stack.append((indent, task))

    return doc


def serialize(doc: TodoFile) -> str:
    """Rejoin the verbatim lines. Inverse of `parse`."""
    return '\n'.join(doc.lines)
