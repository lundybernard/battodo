"""Read the history of one task from the journal (ADR 0022).

`TaskHistory` resolves a selector against the journal, not the lists,
so a finished task stays in reach. `HistoryEntry` holds one entry of
the history.

Each form is a view that reads the history through its attributes:
`HistoryView` lays it out as text, and `HistoryJsonView` as JSON.
"""

from datetime import date, datetime, tzinfo
from json import dumps
from operator import attrgetter
from pathlib import Path
from typing import Any

from batconf import Configuration

from .journal import COMPLETED_EVENT, Journal

# The text form of a history indents each level by two spaces.
INDENT = '  '
# The label the text form gives the event of a checklist item.
CHECKLIST_LABEL = '(checklist item)'


class TaskHistory:
    """One task's history, read from the journal (ADR 0022).

    The selector names one stream: its id, or a case-insensitive part of
    the current title of the task. The journal keeps a finished task
    after its block leaves the list, so a history still reaches it.
    """

    def __init__(
        self,
        journal: Journal,
        selector: str,
        zone: tzinfo | None,
    ) -> None:
        self.journal = journal
        self.selector = selector
        self.zone = zone

    @classmethod
    def from_config(
        cls,
        conf: Configuration,
        now: datetime,
        *,
        selector: str,
    ) -> 'TaskHistory':
        """Build the history `selector` names from a configuration.

        The zone of the clock decides the local day of each event.
        """
        journal = Journal(Path(conf.view.source_dir))
        return cls(journal, selector, now.tzinfo)

    @property
    def task_id(self) -> str:
        """The id of the task: its stream id after `task/`."""
        return self.stream_id.removeprefix('task/')

    @property
    def stream_id(self) -> str:
        """The stream the selector names.

        A stream id narrows out every title match.

        Raises
        ------
        ValueError
            The selector names no stream, or several.
        """
        named = f'task/{self.selector}'
        if any(event['stream_id'] == named for event in self.journal.events):
            return named
        part = self.selector.lower()
        found = {
            stream_id: title
            for stream_id, title in self.titles.items()
                if part in title.lower()
        }  # fmt: skip
        if not found:
            raise ValueError(
                f'no task in the journal matches {self.selector!r}'
            )
        if len(found) > 1:
            named = ', '.join(repr(title) for title in found.values())
            raise ValueError(
                f'{self.selector!r} matches {len(found)} tasks in the '
                f'journal: {named}'
            )
        (stream_id,) = found
        return stream_id

    @property
    def titles(self) -> dict[str, str]:
        """The current title of each stream, by stream id.

        The snapshot title, with the title delta applied, of the last
        event of the task's own. A checklist item's event carries the
        snapshot of the item, so it gives no title.
        """
        titles: dict[str, str] = {}
        for event in self.journal.events:
            payload = event['payload']
            if payload.get('checklist_item'):
                continue
            renamed = payload.get('delta', {}).get('title')
            title = renamed[1] if renamed else payload['snapshot']['title']
            titles[event['stream_id']] = title
        return titles

    @property
    def title(self) -> str | None:
        """The current title of the task.

        None when the stream holds no event of the task's own.
        """
        return self.titles.get(self.stream_id)

    @property
    def entries(self) -> list['HistoryEntry']:
        """Each completion, and each other event that carries attributes.

        Newest first: by day, then the later event in the journal first.
        """
        read = [HistoryEntry(event, self.zone) for event in self.events]
        listed = [
            entry
            for entry in read
                if entry.kind == COMPLETED_EVENT or entry.attrs
        ]  # fmt: skip
        newest = reversed(listed)
        return sorted(newest, key=attrgetter('day'), reverse=True)

    @property
    def events(self) -> list[dict[str, Any]]:
        """The events of the task's stream, in journal order."""
        stream_id = self.stream_id
        return [
            event
            for event in self.journal.events
                if event['stream_id'] == stream_id
        ]  # fmt: skip


class HistoryEntry:
    """One event of a history: its kind, its day and its attributes."""

    def __init__(self, event: dict[str, Any], zone: tzinfo | None) -> None:
        self.event = event
        self.zone = zone

    @property
    def kind(self) -> str:
        """The event type."""
        return self.event['type']

    @property
    def checklist_item(self) -> bool:
        """Whether the event belongs to a checklist item."""
        return bool(self.event['payload'].get('checklist_item'))

    @property
    def day(self) -> date:
        """The day the event is for.

        A completion's `completed_on`. The local day of `occurred_at`
        for any other event, and for a completion that predates
        `completed_on`.
        """
        completed_on = self.event['payload'].get('completed_on')
        if completed_on is not None:
            return date.fromisoformat(completed_on)
        occurred = datetime.fromisoformat(self.event['occurred_at'])
        return occurred.astimezone(self.zone).date()

    @property
    def attrs(self) -> dict[str, str]:
        """The attributes, in recorded order. Absent reads as none."""
        return self.event['payload'].get('attrs', {})


class HistoryView:
    """A history rendered for a terminal: a header, then the entries."""

    def __init__(self, history: TaskHistory) -> None:
        self.history = history

    @property
    def text(self) -> str:
        """The header, then each entry. Without a trailing newline."""
        lines = [self.header]
        for entry in self.entries:
            lines.extend(entry.lines)
        return '\n'.join(lines)

    @property
    def header(self) -> str:
        """The title of the task and its `[ID:]`, or the `[ID:]` alone."""
        marker = f'[ID:{self.history.task_id}]'
        title = self.history.title
        return f'{title} {marker}' if title else marker

    @property
    def entries(self) -> list['HistoryEntryView']:
        """The entries of the history, each laid out as text."""
        return [HistoryEntryView(entry) for entry in self.history.entries]


class HistoryEntryView:
    """One entry of a history: its day and kind, then its attributes."""

    def __init__(self, entry: HistoryEntry) -> None:
        self.entry = entry

    @property
    def lines(self) -> list[str]:
        """The day and the label, then one `key=value` line each."""
        day = self.entry.day.isoformat()
        return [
            f'{INDENT}{day}{INDENT}{self.label}',
            *(
                f'{INDENT * 2}{key}={value}'
                for key, value in self.entry.attrs.items()
            ),
        ]

    @property
    def label(self) -> str:
        """The kind. The checklist marker labels a checklist item's."""
        kind = self.entry.kind
        return (
            f'{kind} {CHECKLIST_LABEL}' if self.entry.checklist_item else kind
        )


class HistoryJsonView:
    """A history laid out as JSON, for an agent to read."""

    def __init__(self, history: TaskHistory) -> None:
        self.history = history

    @property
    def json(self) -> str:
        """`data` as a JSON document, indented for a person to read too.

        The schema is a contract for agents; see `data` for its shape.
        """
        return dumps(self.data, indent=2)

    @property
    def data(self) -> dict[str, Any]:
        """The machine-readable form of the history.

        Shaped as::

            {"id": "ab12cd", "title": "Renew the parking permit",
             "entries": [{"kind": "TaskCompleted",
                          "checklist_item": false, "day": "2026-09-30",
                          "attrs": {"cost": "45.00"}}]}

        `title` is null when no event of the task's own records one.
        """
        return {
            'id': self.history.task_id,
            'title': self.history.title,
            'entries': [entry.data for entry in self.entries],
        }

    @property
    def entries(self) -> list['HistoryEntryJsonView']:
        """The entries of the history, each laid out as JSON."""
        return [HistoryEntryJsonView(entry) for entry in self.history.entries]


class HistoryEntryJsonView:
    """One entry of a history laid out as JSON."""

    def __init__(self, entry: HistoryEntry) -> None:
        self.entry = entry

    @property
    def data(self) -> dict[str, Any]:
        """The entry as `HistoryJsonView.data` records it."""
        return {
            'kind': self.entry.kind,
            'checklist_item': self.entry.checklist_item,
            'day': self.entry.day.isoformat(),
            'attrs': self.entry.attrs,
        }
