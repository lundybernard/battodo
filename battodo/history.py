"""Read the history of one task from the journal (ADR 0022).

`TaskHistory` resolves a selector against the journal, not the lists,
so a finished task stays in reach. `StreamSelection` finds the stream a
selector names among the `TaskStream`s of the journal, one per task.
`HistoryEntry` holds one entry of the history.

Each form is a view that reads the history through its attributes:
`HistoryView` lays it out as text, and `HistoryJsonView` as JSON.
"""

from datetime import date, datetime, tzinfo
from json import dumps
from operator import attrgetter
from pathlib import Path
from typing import Any

from batconf import Configuration

from .journal import COMPLETED_EVENT, SCRATCHED_EVENT, Journal

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
        return self.stream.task_id

    @property
    def stream(self) -> 'TaskStream':
        """The stream the selector names.

        Raises
        ------
        ValueError
            The selector names no stream, or several.
        """
        return StreamSelection(self.streams, self.selector).stream

    @property
    def streams(self) -> list['TaskStream']:
        """Every stream of the journal, read in the zone of the history."""
        return [
            TaskStream(stream_id, events, self.zone)
            for stream_id, events in self.journal.streams.items()
        ]

    @property
    def title(self) -> str | None:
        """The current title of the task.

        None when the stream holds no event of the task's own.
        """
        return self.stream.title

    @property
    def entries(self) -> list['HistoryEntry']:
        """Each completion, and each other event that carries attributes.

        Newest first: by day, then the later event in the journal first.
        """
        read = [HistoryEntry(event, self.zone) for event in self.stream.events]
        listed = [
            entry
            for entry in read
                if entry.kind == COMPLETED_EVENT or entry.attrs
        ]  # fmt: skip
        newest = reversed(listed)
        return sorted(newest, key=attrgetter('day'), reverse=True)


class StreamSelection:
    """The stream of the journal a selector names (ADR 0022).

    A stream id narrows out every title match. Otherwise a
    case-insensitive part of the current title names each stream whose
    title holds it.
    """

    def __init__(self, streams: list['TaskStream'], selector: str) -> None:
        self.streams = streams
        self.selector = selector

    @property
    def stream(self) -> 'TaskStream':
        """The one stream the selector names.

        Raises
        ------
        ValueError
            The selector names no stream, or several. Several are named
            one per line: the id, the day of the last event and the
            title, newest first.
        """
        found = self.candidates
        if not found:
            raise ValueError(
                f'no task in the journal matches {self.selector!r}'
            )
        if len(found) > 1:
            newest = sorted(found, key=attrgetter('day', 'seq'), reverse=True)
            lines = '\n'.join(
                f'{stream.task_id}{INDENT}{stream.day}{INDENT}{stream.title}'
                for stream in newest
            )
            raise ValueError(
                f'{self.selector!r} matches {len(found)} tasks in the '
                f'journal:\n{lines}'
            )
        return found[0]

    @property
    def candidates(self) -> list['TaskStream']:
        """Every stream the selector names, in journal order."""
        named = [
            stream
            for stream in self.streams
                if stream.task_id == self.selector
        ]  # fmt: skip
        part = self.selector.lower()
        return named or [
            stream
            for stream in self.streams
                if stream.title is not None and part in stream.title.lower()
        ]  # fmt: skip


class TaskStream:
    """One task's stream: its events, in journal order (ADR 0014).

    The events of a checklist item go on the stream of its owner, marked
    as such. Every other event of the stream is the task's own.
    """

    def __init__(
        self,
        stream_id: str,
        events: list[dict[str, Any]],
        zone: tzinfo | None,
    ) -> None:
        self.stream_id = stream_id
        self.events = events
        self.zone = zone

    @property
    def task_id(self) -> str:
        """The id of the task: the stream id after `task/`."""
        return self.stream_id.removeprefix('task/')

    @property
    def title(self) -> str | None:
        """The current title of the task.

        The snapshot title, with the title delta applied, of the last
        event of the task's own. None when the stream holds none.
        """
        own = self.own
        if not own:
            return None
        payload = own[-1]['payload']
        renamed = payload.get('delta', {}).get('title')
        return renamed[1] if renamed else payload['snapshot']['title']

    @property
    def day(self) -> date:
        """The day of the last event, as a history entry reads it."""
        return HistoryEntry(self.events[-1], self.zone).day

    @property
    def seq(self) -> int:
        """The place of the last event in the journal."""
        return self.events[-1]['seq']

    @property
    def closed(self) -> bool:
        """Whether the last event of the task's own closes the task.

        A scratch closes it, and so does a completion that does not
        reschedule it.
        """
        own = self.own
        if not own:
            return False
        last = own[-1]
        if last['type'] == SCRATCHED_EVENT:
            return True
        delta = last['payload'].get('delta', {})
        return last['type'] == COMPLETED_EVENT and 'DUE' not in delta

    @property
    def snapshot(self) -> dict[str, Any] | None:
        """The snapshot of the last event of the task's own, or None."""
        own = self.own
        return own[-1]['payload']['snapshot'] if own else None

    @property
    def list_name(self) -> str | None:
        """The list the snapshot names, or None where it names none."""
        snapshot = self.snapshot
        return snapshot.get('list') if snapshot else None

    @property
    def nested(self) -> bool:
        """Whether the last event of the task's own places it under another.

        Its ancestry is a path longer than its own title.
        """
        own = self.own
        if not own:
            return False
        payload = own[-1]['payload']
        ancestry = payload.get('ancestry')
        title = payload['snapshot']['title']
        return ancestry is not None and ancestry != title

    @property
    def parent_id(self) -> str | None:
        """The id of the parent its add names, or None."""
        return next(
            (
                event['payload']['parent']
                for event in self.own
                    if 'parent' in event['payload']
            ),
            None,
        )  # fmt: skip

    @property
    def checklist_titles(self) -> list[str]:
        """The title of each checklist item event on the stream."""
        return [
            event['payload']['snapshot']['title']
            for event in self.events
                if event['payload'].get('checklist_item')
        ]  # fmt: skip

    @property
    def own(self) -> list[dict[str, Any]]:
        """The events of the task's own, in journal order."""
        return [
            event
            for event in self.events
                if not event['payload'].get('checklist_item')
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
