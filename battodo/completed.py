"""Digest the completed log for a period: today, the week, the month.

`completed.md` is append-only and holds no todo lists, so the list
parser never reaches it. Its records are `DATE | CATEGORY | STATUS |
TITLE` lines, one per completion, and only DONE records reach a digest:
a SCRATCHED record reports an abandonment, not work done.

A record with attributes ends with one `[attrs:{...}]` block, which
holds them as a JSON object of text values. The block starts at the
first `[attrs:` from which the rest of the line reads as such an object
and a `]`. JSON escapes every quote in a value, so no `|`, `=` or comma
in a title or a value moves the block. A line without a block reads as
before; only a title that ends with a block of its own reads otherwise.

A title keeps the `Parent > Child` ancestry the log stores, and loses
its `[FIELD:]` markup. Categories sort in the view's order, so a
category leads in both.

`Digest` decides what one digest holds. Each form reads it through its
attributes: `DigestView` lays it out as aligned text, with the record
attributes as `key=value` after the title, and `DigestJsonView` as
JSON, with an `attrs` object on each entry. `lib.get_completed`
composes them.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import cached_property
from json import dumps, loads
from pathlib import Path
from typing import Any

from batconf import Configuration

from .lists import category_order
from .mutate import ATTRIBUTES_MARK, COMPLETED_LOG, DONE_STATUS
from .parser import FIELD_RE, parse_date
from .table import Table, column_widths, page_text

# The field separator a completion is written with. The log's name and
# its statuses come from `mutate`, which writes them.
SEPARATOR = ' | '
# date, category, status, title: the fields one record carries. A
# separator inside a title belongs to the title.
RECORD_FIELDS = 4
# Where an attribute block can start.
ATTRIBUTES_MARK_RE = re.compile(re.escape(ATTRIBUTES_MARK))
# How many days a week covers, today included.
WEEK_DAYS = 7
PERIOD_STARTS: dict[str, Callable[[date], date]] = {
    'today': lambda today: today,
    'week': lambda today: today - timedelta(days=WEEK_DAYS - 1),
    'month': lambda today: today.replace(day=1),
}
PERIODS = tuple(PERIOD_STARTS)
DEFAULT_PERIOD = 'week'
# Layout. Both columns are as wide as their widest value; the titles
# come last, so nothing is ever clipped away from an ancestry.
COLUMNS = ('DATE', 'TASK')
ALIGN = ('<', '<')


class CompletedError(Exception):
    """The source directory holds no completed log.

    Raised rather than reporting an empty period: pointed at the wrong
    directory, a digest would read as "nothing done". The message
    always carries the resolved path.
    """


class Digest:
    """What one digest holds: one period of one log, by category."""

    def __init__(self, directory: Path, now: datetime, *, period: str) -> None:
        self._directory = directory
        self._now = now
        self.period = period

    @classmethod
    def from_config(
        cls,
        conf: Configuration,
        now: datetime,
        *,
        period: str,
    ) -> 'Digest':
        """Build the digest of `period` from a resolved configuration."""
        return cls(Path(conf.view.source_dir), now, period=period)

    @property
    def _today(self) -> date:
        return self._now.date()

    @cached_property
    def start(self) -> date:
        """The first day the digest covers.

        Raises
        ------
        ValueError
            The period has no definition.
        """
        if self.period not in PERIOD_STARTS:
            raise ValueError(
                f'unknown period {self.period!r}; '
                f'choose one of {", ".join(PERIODS)}'
            )
        return PERIOD_STARTS[self.period](self._today)

    @property
    def end(self) -> date:
        return self._today

    @cached_property
    def _path(self) -> Path:
        """The log this reads.

        Raises
        ------
        CompletedError
            The log is not there.
        """
        found = self._directory.expanduser() / COMPLETED_LOG
        if not found.is_file():
            raise CompletedError(f'completed log not found: {found}')
        return found

    @cached_property
    def _text(self) -> str:
        return self._path.read_text(encoding='utf-8')

    @cached_property
    def records(self) -> list['Record']:
        """The period's DONE records, oldest first.

        Sorted here rather than trusted from the file: the log is
        appended to as tasks complete, and a hand-edited one is in no
        order at all. A line feed alone ends a line: a title may hold
        any other line break, as the list it came from does.
        """
        found = [
            record
            for line in self._text.split('\n')
                if (record := read_record(line)) is not None
                if self.start <= record.day <= self.end
        ]  # fmt: skip
        return sorted(found, key=lambda record: record.day)

    @cached_property
    def groups(self) -> list['Group']:
        """The records by category, in the order a view shows them."""
        names = sorted(
            {record.category for record in self.records},
            key=category_order,
        )
        return [
            Group(
                name,
                [
                    record
                    for record in self.records
                        if record.category == name
                ],
            )
            for name in names
        ]  # fmt: skip


@dataclass(frozen=True)
class Record:
    """One DONE line of the log: when, which list, what, its attributes."""

    day: date
    category: str
    title: str
    attrs: dict[str, str] = field(default_factory=dict)


def read_record(line: str) -> Record | None:
    """One log line as a record, or None where it is not one.

    Comments, blank lines and SCRATCHED records all read as None, as
    does any line the four fields cannot be read from. The log is
    hand-edited, so a line btodo cannot parse is skipped rather than
    raised on.
    """
    parts = line.split(SEPARATOR, RECORD_FIELDS - 1)
    if len(parts) != RECORD_FIELDS:
        return None
    stamp, category, status, rest = (part.strip() for part in parts)
    day = parse_date(stamp)
    if day is None or status != DONE_STATUS:
        return None
    title, attrs = split_attributes(rest)
    return Record(day, category, clean_title(title), attrs)


def split_attributes(text: str) -> tuple[str, dict[str, str]]:
    """The text before its attribute block, and the attributes in it.

    The block starts at the first mark from which the rest of the text
    reads as attributes. A text without one keeps all of it.
    """
    for found in ATTRIBUTES_MARK_RE.finditer(text):
        attrs = read_attributes(text[found.end() :])
        if attrs is not None:
            return text[: found.start()], attrs
    return text, {}


def read_attributes(block: str) -> dict[str, str] | None:
    """A JSON object of text values, then `]`, or None where it is not."""
    if not block.endswith(']'):
        return None
    try:
        found = loads(block[:-1])
    except ValueError:
        return None
    if not isinstance(found, dict):
        return None
    if not all(isinstance(value, str) for value in found.values()):
        return None
    return found


def clean_title(title: str) -> str:
    """The title as a digest shows it: no fields, no double spaces."""
    return ' '.join(FIELD_RE.sub('', title).split())


class Group:
    """One category's records within a digest."""

    def __init__(self, name: str, records: list[Record]) -> None:
        self.name = name
        self.records = records


class DigestView:
    """A digest rendered for a terminal: a header, then a table each."""

    def __init__(self, digest: Digest) -> None:
        self._digest = digest

    @property
    def _span(self) -> str:
        """The days covered: the first and the last, or the one day."""
        start, end = self._digest.start, self._digest.end
        if start == end:
            return start.isoformat()
        return f'{start.isoformat()} to {end.isoformat()}'

    @property
    def _header(self) -> str:
        return (
            f'Completed {self._digest.period}: {self._span} '
            f'— {len(self._digest.records)} done'
        )

    @cached_property
    def _widths(self) -> list[int]:
        """Each column's width: its widest cell, the name included.

        Sized against every record at once, so one set of widths serves
        all of the tables and the columns line up down the whole page.
        """
        cells = [RecordView(record).cells for record in self._digest.records]
        return column_widths(COLUMNS, cells)

    @cached_property
    def _tables(self) -> list[Table]:
        return [
            Table(
                group.name,
                COLUMNS,
                ALIGN,
                [RecordView(record).cells for record in group.records],
                self._widths,
            )
            for group in self._digest.groups
        ]

    @cached_property
    def text(self) -> str:
        return page_text(self._header, self._tables)

    def __str__(self) -> str:
        return self.text


class RecordView:
    """One record of a digest laid out as the cells of a table line."""

    def __init__(self, record: Record) -> None:
        self._record = record

    @property
    def cells(self) -> tuple[str, ...]:
        """The record's two values, in COLUMNS order.

        The attributes follow the title in its cell.
        """
        title = self._record.title
        attributes = self._attributes
        task = f'{title} {attributes}' if attributes else title
        return (self._record.day.isoformat(), task)

    @property
    def _attributes(self) -> str:
        """Each attribute as `key=value`, in the order logged."""
        pairs = (f'{key}={value}' for key, value in self._record.attrs.items())
        return ', '.join(pairs)


class DigestJsonView:
    """A digest laid out as JSON, for an agent to read."""

    def __init__(self, digest: Digest) -> None:
        self._digest = digest

    @property
    def json(self) -> str:
        """`_data` as a JSON document, indented for a person to read too.

        The schema is a contract for agents; see `_data` for its shape.
        """
        return dumps(self._data, indent=2)

    @property
    def _data(self) -> dict[str, Any]:
        """The machine-readable form of the digest.

        Shaped as::

            {"period": "week", "start": "2026-07-30",
             "end": "2026-08-05", "total": 6,
             "categories": [{"name": "work", "entries": [
                 {"date": "2026-08-05", "title": "Deck > Chip it",
                  "attrs": {"cost": "45.00"}}]}]}

        `total` counts every record the period holds, which is the sum
        of the entries: a digest abridges nothing.
        """
        return {
            'period': self._digest.period,
            'start': self._digest.start.isoformat(),
            'end': self._digest.end.isoformat(),
            'total': len(self._digest.records),
            'categories': [group.data for group in self._groups],
        }

    @property
    def _groups(self) -> list['GroupJsonView']:
        """The digest's groups, each laid out as JSON."""
        return [GroupJsonView(group) for group in self._digest.groups]


class GroupJsonView:
    """One category's records within a digest, laid out as JSON."""

    def __init__(self, group: Group) -> None:
        self._group = group

    @property
    def data(self) -> dict[str, Any]:
        """The group as `DigestJsonView._data` records it."""
        return {
            'name': self._group.name,
            'entries': [record.data for record in self._records],
        }

    @property
    def _records(self) -> list['RecordJsonView']:
        """The group's records, each laid out as JSON."""
        return [RecordJsonView(record) for record in self._group.records]


class RecordJsonView:
    """One record of a digest laid out as JSON."""

    def __init__(self, record: Record) -> None:
        self._record = record

    @property
    def data(self) -> dict[str, Any]:
        """The record as `GroupJsonView.data` records it.

        `attrs` is an empty object where the record carries none.
        """
        return {
            'date': self._record.day.isoformat(),
            'title': self._record.title,
            'attrs': self._record.attrs,
        }
