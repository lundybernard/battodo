"""Digest the completed log for a period: today, the week, the month.

`completed.md` is append-only and holds no todo lists, so the list
parser never reaches it. Its records are `DATE | CATEGORY | STATUS |
TITLE` lines, one per completion, and only DONE records reach a digest:
a SCRATCHED record reports an abandonment, not work done.

A title keeps the `Parent > Child` ancestry the log stores, and loses
its `[FIELD:]` markup. Categories sort in the view's order, so a
category leads in both.

`Digest` decides what one digest holds; `DigestView` lays the same
digest out as aligned text. The two `build_` functions are what a
consumer calls.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import cached_property
from json import dumps
from pathlib import Path
from typing import Any

from .mutate import COMPLETED_LOG, DONE_STATUS
from .parser import FIELD_RE, parse_date
from .view import category_order

# The field separator a completion is written with. The log's name and
# its statuses come from `mutate`, which writes them.
SEPARATOR = ' | '
# date, category, status, title: the fields one record carries. A
# separator inside a title belongs to the title.
RECORD_FIELDS = 4
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
INDENT = '  '
GAP = '  '
RULE = '─'


class CompletedError(Exception):
    """The source directory holds no completed log.

    Raised rather than reporting an empty period: pointed at the wrong
    directory, a digest would read as "nothing done". The message
    always carries the resolved path.
    """


def clean_title(title: str) -> str:
    """The title as a digest shows it: no fields, no double spaces."""
    return ' '.join(FIELD_RE.sub('', title).split())


def table_width(widths: list[int]) -> int:
    """How wide a table laid out to `widths` comes out."""
    return len(INDENT) + sum(widths) + len(GAP) * (len(COLUMNS) - 1)


@dataclass(frozen=True)
class Record:
    """One DONE line of the log: when, which list, what."""

    day: date
    category: str
    title: str

    @property
    def cells(self) -> tuple[str, ...]:
        """The record's two values, in COLUMNS order."""
        return (self.day.isoformat(), self.title)

    @property
    def entry(self) -> dict[str, str]:
        """The record as `Digest.data` publishes it."""
        return {'date': self.day.isoformat(), 'title': self.title}


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
    stamp, category, status, title = (part.strip() for part in parts)
    day = parse_date(stamp)
    if day is None or status != DONE_STATUS:
        return None
    return Record(day, category, clean_title(title))


class Group:
    """One category's records within a digest."""

    def __init__(self, name: str, records: list[Record]) -> None:
        self.name = name
        self.records = records

    @property
    def title(self) -> str:
        return self.name.replace('-', ' ').capitalize()

    @property
    def entries(self) -> list[dict[str, str]]:
        """The records as `Digest.data` publishes them."""
        return [record.entry for record in self.records]


class Digest:
    """What one digest holds: one period of one log, by category."""

    def __init__(self, directory: Path, now: datetime, *, period: str) -> None:
        self.directory = directory
        self.now = now
        self.period = period

    @cached_property
    def today(self) -> date:
        return self.now.date()

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
        return PERIOD_STARTS[self.period](self.today)

    @property
    def end(self) -> date:
        return self.today

    @cached_property
    def path(self) -> Path:
        """The log this reads.

        Raises
        ------
        CompletedError
            The log is not there.
        """
        found = self.directory.expanduser() / COMPLETED_LOG
        if not found.is_file():
            raise CompletedError(f'completed log not found: {found}')
        return found

    @cached_property
    def text(self) -> str:
        return self.path.read_text(encoding='utf-8')

    @cached_property
    def records(self) -> list[Record]:
        """The period's DONE records, oldest first.

        Sorted here rather than trusted from the file: the log is
        appended to as tasks complete, and a hand-edited one is in no
        order at all.
        """
        found = [
            record
            for line in self.text.splitlines()
            if (record := read_record(line)) is not None
            if self.start <= record.day <= self.end
        ]
        return sorted(found, key=lambda record: record.day)

    @cached_property
    def groups(self) -> list[Group]:
        """The records by category, in the order a view shows them."""
        names = sorted(
            {record.category for record in self.records}, key=category_order
        )
        return [
            Group(
                name,
                [record for record in self.records if record.category == name],
            )
            for name in names
        ]

    @cached_property
    def data(self) -> dict[str, Any]:
        """The machine-readable form of this digest.

        Shaped as::

            {"period": "week", "start": "2026-07-30",
             "end": "2026-08-05", "total": 6,
             "categories": [{"name": "work", "entries": [
                 {"date": "2026-08-05", "title": "Deck > Chip it"}]}]}

        `total` counts every record the period holds, which is the sum
        of the entries: a digest abridges nothing.
        """
        return {
            'period': self.period,
            'start': self.start.isoformat(),
            'end': self.end.isoformat(),
            'total': len(self.records),
            'categories': [
                {'name': group.name, 'entries': group.entries}
                for group in self.groups
            ],
        }

    @cached_property
    def json(self) -> str:
        """`data` as a JSON document, indented for a person to read too.

        The schema is a contract for agents; see `data` for its shape.
        """
        return dumps(self.data, indent=2)


class Table:
    """One group's records, at a width the whole digest shares."""

    def __init__(self, group: Group, widths: list[int]) -> None:
        self.group = group
        self.widths = widths

    @property
    def heading(self) -> str:
        """A titled rule spanning the table, e.g. `── Work ────`."""
        prefix = f'{RULE * 2} {self.group.title} '
        return prefix + RULE * max(0, table_width(self.widths) - len(prefix))

    def line(self, cells: tuple[str, ...]) -> str:
        """Pad one row's cells. Trailing space is stripped."""
        laid = (f'{cell:<{size}}' for cell, size in zip(cells, self.widths))
        return f'{INDENT}{GAP.join(laid)}'.rstrip()

    @property
    def lines(self) -> list[str]:
        """Everything under the heading: the column names, then the rows."""
        out = [self.line(COLUMNS)]
        out.extend(self.line(record.cells) for record in self.group.records)
        return out


class DigestView:
    """A digest rendered for a terminal: a header, then a table each."""

    def __init__(self, digest: Digest) -> None:
        self.digest = digest

    @property
    def span(self) -> str:
        """The days covered: the first and the last, or the one day."""
        start, end = self.digest.start, self.digest.end
        if start == end:
            return start.isoformat()
        return f'{start.isoformat()} to {end.isoformat()}'

    @property
    def header(self) -> str:
        return (
            f'Completed {self.digest.period}: {self.span} '
            f'— {len(self.digest.records)} done'
        )

    @cached_property
    def widths(self) -> list[int]:
        """Each column's width: its widest cell, the name included.

        Sized against every record at once, so one set of widths serves
        all of the tables and the columns line up down the whole page.
        """
        records = self.digest.records
        return [
            max([len(name), *(len(record.cells[index]) for record in records)])
            for index, name in enumerate(COLUMNS)
        ]

    @cached_property
    def tables(self) -> list[Table]:
        return [Table(group, self.widths) for group in self.digest.groups]

    @cached_property
    def text(self) -> str:
        out = [self.header]
        for table in self.tables:
            out.append('')
            out.append(table.heading)
            out.extend(table.lines)
        return '\n'.join(out)

    def __str__(self) -> str:
        return self.text


def build_digest(directory: Path, now: datetime, *, period: str) -> str:
    """Render the completed records `period` covers.

    Parameters
    ----------
    directory : Path
        The source directory, `~` unexpanded.
    now : datetime
        The clock, whose local day ends every period.
    period : str
        One of `PERIODS`.

    Returns
    -------
    str
        The rendered digest, without a trailing newline.

    Raises
    ------
    CompletedError
        The source directory holds no completed log.
    ValueError
        The period has no definition.
    """
    return DigestView(Digest(directory, now, period=period)).text


def build_digest_json(directory: Path, now: datetime, *, period: str) -> str:
    """Serialize the same digest `build_digest` renders.

    Parameters
    ----------
    directory : Path
        The source directory, `~` unexpanded.
    now : datetime
        The clock, whose local day ends every period.
    period : str
        One of `PERIODS`.

    Returns
    -------
    str
        A JSON document; see `Digest.data` for its shape.

    Raises
    ------
    CompletedError
        The source directory holds no completed log.
    ValueError
        The period has no definition.
    """
    return Digest(directory, now, period=period).json
