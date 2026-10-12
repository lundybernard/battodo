"""Read the history of one task from the journal (ADR 0022).

`TaskHistory` resolves a selector against the journal, not the lists,
so a finished task stays in reach. `HistoryEntry` holds one entry of
the history.
"""

from datetime import date, datetime, tzinfo
from typing import Any

from batconf import Configuration

from .journal import Journal


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
        raise NotImplementedError

    @property
    def task_id(self) -> str:
        """The id of the task: its stream, without the stream prefix."""
        raise NotImplementedError

    @property
    def stream_id(self) -> str:
        """The stream the selector names.

        A stream id narrows out every title match.

        Raises
        ------
        ValueError
            The selector names no stream, or several.
        """
        raise NotImplementedError

    @property
    def titles(self) -> dict[str, str]:
        """The current title of each stream, by stream id.

        The snapshot title, with the title delta applied, of the last
        event of the task's own. A checklist item's event carries the
        snapshot of the item, so it gives no title.
        """
        raise NotImplementedError

    @property
    def title(self) -> str | None:
        """The current title of the task.

        None when the stream holds no event of the task's own.
        """
        raise NotImplementedError

    @property
    def entries(self) -> list['HistoryEntry']:
        """Each completion, and each other event that carries attributes.

        Newest first: by day, then the later event in the journal first.
        """
        raise NotImplementedError

    @property
    def events(self) -> list[dict[str, Any]]:
        """The events of the task's stream, in journal order."""
        raise NotImplementedError


class HistoryEntry:
    """One event of a history: its kind, its day and its attributes."""

    def __init__(self, event: dict[str, Any], zone: tzinfo | None) -> None:
        self.event = event
        self.zone = zone

    @property
    def kind(self) -> str:
        """The event type."""
        raise NotImplementedError

    @property
    def checklist_item(self) -> bool:
        """Whether the event is the completion of a checklist item."""
        raise NotImplementedError

    @property
    def day(self) -> date:
        """The day the event is for.

        A completion's `completed_on`. The local day of `occurred_at`
        for any other event, and for a completion that predates
        `completed_on`.
        """
        raise NotImplementedError

    @property
    def attrs(self) -> dict[str, str]:
        """The attributes, in recorded order. Absent reads as none."""
        raise NotImplementedError
