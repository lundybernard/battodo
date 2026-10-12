"""Read the history of one task from the journal (ADR 0022).

`TaskHistory` resolves a selector against the journal, not the lists,
so a finished task stays in reach. `HistoryEntry` holds one entry of
the history.
"""

from datetime import date, datetime, tzinfo
from operator import attrgetter
from pathlib import Path
from typing import Any

from batconf import Configuration

from .journal import COMPLETED_EVENT, Journal


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
