"""Parse and serialize SCHEMA.md-format todo lists.

The parser keeps every source line verbatim and records only *indices*
into that line list. Serializing rejoins the untouched lines, so
parse -> serialize is byte-identical for any input. Mutations replace a
single line via `Task.replace_field`, which edits the raw text in place
rather than rebuilding it from parsed fields -- field order varies from
line to line in real files, so a canonical-order serializer would
rewrite every line it touched.
"""

import re
from dataclasses import dataclass, field
from datetime import date

FIELD_RE = re.compile(r'\[(P|LOE|DUE|BUMPED|ADDED|REPEAT|TAGS|ID):([^\]]*)\]')
CHECKBOX_RE = re.compile(r'^(\s*)- \[([ xX])\]\s?(.*)$')
OPEN_HEADING = '## Open'


@dataclass
class Task:
    """One `- [ ]` line, plus its children and note lines."""

    raw_index: int
    indent: int
    done: bool
    title: str
    fields: dict[str, str]
    raw: str = ''
    children: list['Task'] = field(default_factory=list)
    note_indices: list[int] = field(default_factory=list)

    @property
    def priority(self) -> int:
        return int(self.fields.get('P', 0))

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

    def replace_field(self, name: str, value: str) -> str:
        """Return this task's line with `name` set to `value`.

        An existing field is replaced where it stands; a new one is
        appended after the last field so nothing else shifts.
        """
        if name in self.fields:
            return re.sub(
                rf'\[{name}:[^\]]*\]',
                f'[{name}:{value}]',
                self.raw,
                count=1,
            )
        return f'{self.raw.rstrip()} [{name}:{value}]'


@dataclass
class TodoFile:
    """A parsed list: verbatim lines plus the open-section task tree."""

    lines: list[str]
    tasks: list[Task] = field(default_factory=list)


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
    stack: list[tuple[int, Task]] = []

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
        task = Task(
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
