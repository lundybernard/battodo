"""Property tests for the history read, driven by Hypothesis.

Each case writes a journal drawn in the shapes the writes record, then
asserts what `battodo.lib.get_history` answers for a drawn selector in
each format: the document, the text, or the error. The expected answer
derives from the drawn events and the zone of the clock, never from the
code under test.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, time, timezone
from json import loads
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, NamedTuple
from unittest import TestCase
from unittest.mock import Mock

from hypothesis import given
from hypothesis import strategies as st

from battodo.conf import TZ
from battodo.journal import Journal
from battodo.lib import get_history

from .mutate_test import refusal

# The clock every read runs at. Its zone decides each local day.
NOW = datetime(2026, 10, 5, 10, 30, tzinfo=TZ)
# The streams a drawn journal spreads its events over.
STREAM_IDS = ('aa11aa', 'bb22bb', 'cc33cc')
# The characters a drawn title holds: few, so titles share parts.
TITLE_ALPHABET = 'abAB '
COMPLETED = 'TaskCompleted'
# The writes that record a checklist item on its ancestor's stream.
CHECKLIST_WRITES = (COMPLETED, 'TaskScratched')
WRITES = ('TaskAdded', 'TaskUpdated', 'TaskAnnotated', *CHECKLIST_WRITES)
# Any character a JSON journal holds, a line break excluded.
VALUE_CHARACTERS = st.characters(codec='utf-8', exclude_characters='\n\r')
INDENT = '  '
# The span the drawn days and instants fall in: a few days, so that
# entries often share a day, and some instants cross local midnight.
EARLIEST = date(2026, 9, 28)
LATEST = date(2026, 10, 2)


class GetHistoryTests(TestCase):
    """Property tests for battodo.lib.get_history."""

    maxDiff = None

    @given(st.data())
    def test_json(t, data: st.DataObject) -> None:
        events = data.draw(journals())
        selector = data.draw(history_selectors(events))
        expected = foreseen(published, events, selector)

        with journaled(events) as directory:
            ret = observed(directory, selector, 'json')

        t.assertEqual(ret, expected)

    @given(st.data())
    def test_text(t, data: st.DataObject) -> None:
        events = data.draw(journals())
        selector = data.draw(history_selectors(events))
        expected = foreseen(rendered, events, selector)

        with journaled(events) as directory:
            ret = observed(directory, selector, 'text')

        t.assertEqual(ret, expected)


def journals() -> st.SearchStrategy[list['Recorded']]:
    """The events of a journal, in the order it holds them."""
    return st.lists(recorded_events(), max_size=8)


class Recorded(NamedTuple):
    """One drawn event: its type, its task id, payload and instant."""

    type: str
    task_id: str
    payload: dict[str, Any]
    occurred_at: datetime


@st.composite
def recorded_events(draw: st.DrawFn) -> Recorded:
    """One event in the shape a write records it.

    An update may rename the task. A completion or a scratch may be a
    checklist item's, which carries no attributes. A completion may
    predate `completed_on`. A note always carries attributes.
    """
    kind = draw(st.sampled_from(WRITES))
    title = draw(titles())
    payload: dict[str, Any] = {'snapshot': {'title': title}}
    if kind == 'TaskUpdated' and draw(st.booleans()):
        payload['delta'] = {'title': [title, draw(titles())]}
    checklist = kind in CHECKLIST_WRITES and draw(st.booleans())
    if checklist:
        payload['checklist_item'] = True
    if kind == COMPLETED and draw(st.booleans()):
        payload['completed_on'] = draw(st.dates(EARLIEST, LATEST)).isoformat()
    noted = 1 if kind == 'TaskAnnotated' else 0
    attrs = {} if checklist else draw(attribute_maps(noted))
    if attrs:
        payload['attrs'] = attrs
    instants = st.datetimes(
        datetime.combine(EARLIEST, time()),
        datetime.combine(LATEST, time()),
        timezones=st.just(timezone.utc),
    )
    occurred_at = draw(instants)
    task_id = draw(st.sampled_from(STREAM_IDS))
    return Recorded(kind, task_id, payload, occurred_at)


def titles() -> st.SearchStrategy[str]:
    """A title from a few characters, so that titles share parts."""
    return st.text(TITLE_ALPHABET, min_size=1, max_size=4)


def attribute_maps(least: int) -> st.SearchStrategy[dict[str, str]]:
    """At least `least` attributes: a lowercase key against any value."""
    return st.dictionaries(
        st.from_regex(r'[a-z][a-z0-9_]{0,3}', fullmatch=True),
        st.text(VALUE_CHARACTERS, min_size=1, max_size=6),
        min_size=least,
        max_size=3,
    )


def history_selectors(events: list[Recorded]) -> st.SearchStrategy[str]:
    """An id, a part of a drawn title, or other text of the alphabet."""
    named = [title for event in events for title in event_titles(event)]
    parts = st.sampled_from(named or ['a']).flatmap(title_parts)
    return st.one_of(
        st.sampled_from(STREAM_IDS),
        parts,
        st.text(TITLE_ALPHABET, min_size=1, max_size=3),
    )


def event_titles(event: Recorded) -> list[str]:
    """Every title an event names: its snapshot's, and a new one."""
    found = [event.payload['snapshot']['title']]
    found.extend(event.payload.get('delta', {}).get('title', [])[1:])
    return found


@st.composite
def title_parts(draw: st.DrawFn, title: str) -> str:
    """A part of `title`, in either case."""
    start = draw(st.integers(0, len(title) - 1))
    end = draw(st.integers(start + 1, len(title)))
    part = title[start:end]
    return part.swapcase() if draw(st.booleans()) else part


def foreseen(
    model: Any,
    events: list[Recorded],
    selector: str,
) -> Any:
    """What `model` answers, or the error a selector is refused with."""
    try:
        return model(events, selector)
    except ValueError as error:
        return refusal(error)


def published(events: list[Recorded], selector: str) -> dict[str, Any]:
    """The history as the JSON form publishes it."""
    task_id = stream_of(events, selector)
    return {
        'id': task_id,
        'title': current_title(events, task_id),
        'entries': [
            {
                'kind': event.type,
                'checklist_item': 'checklist_item' in event.payload,
                'day': day_of(event).isoformat(),
                'attrs': event.payload.get('attrs', {}),
            }
            for event in entries_of(events, task_id)
        ],
    }


def rendered(events: list[Recorded], selector: str) -> str:
    """The history as the text form lays it out."""
    task_id = stream_of(events, selector)
    title = current_title(events, task_id)
    header = f'[ID:{task_id}]'
    lines = [f'{title} {header}' if title else header]
    for event in entries_of(events, task_id):
        label = event.type
        if 'checklist_item' in event.payload:
            label += ' (checklist item)'
        lines.append(f'{INDENT}{day_of(event).isoformat()}{INDENT}{label}')
        attrs = event.payload.get('attrs', {})
        lines.extend(
            f'{INDENT * 2}{key}={value}' for key, value in attrs.items()
        )
    return '\n'.join(lines)


def stream_of(events: list[Recorded], selector: str) -> str:
    """The task id the selector names.

    Raises
    ------
    ValueError
        The selector names no task in the journal, or several.
    """
    if any(event.task_id == selector for event in events):
        return selector
    # Each task with a title, in the order the journal first titles it.
    titled: list[str] = []
    for event in events:
        own = 'checklist_item' not in event.payload
        if own and event.task_id not in titled:
            titled.append(event.task_id)
    titles = {
        task_id: current_title(events, task_id) or '' for task_id in titled
    }
    matched = [
        (task_id, title)
        for task_id, title in titles.items()
            if selector.lower() in title.lower()
    ]  # fmt: skip
    if not matched:
        raise ValueError(f'no task in the journal matches {selector!r}')
    if len(matched) > 1:
        named = ', '.join(repr(title) for _, title in matched)
        raise ValueError(
            f'{selector!r} matches {len(matched)} tasks in the journal: '
            f'{named}'
        )
    return matched[0][0]


def current_title(events: list[Recorded], task_id: str) -> str | None:
    """The title the last event of the task's own leaves it with."""
    for event in reversed(events):
        if event.task_id != task_id or 'checklist_item' in event.payload:
            continue
        renamed = event.payload.get('delta', {}).get('title')
        return renamed[1] if renamed else event.payload['snapshot']['title']
    return None


def entries_of(events: list[Recorded], task_id: str) -> list[Recorded]:
    """The completions and the events with attributes, newest first.

    A later event in the journal comes before an earlier one of its day.
    """
    listed = [
        (position, event)
        for position, event in enumerate(events)
            if event.task_id == task_id
            if event.type == COMPLETED or event.payload.get('attrs')
    ]  # fmt: skip
    ordered = sorted(
        listed,
        key=lambda pair: (-day_of(pair[1]).toordinal(), -pair[0]),
    )
    return [event for _, event in ordered]


def day_of(event: Recorded) -> date:
    """The day the completion is for, or the local day of the event."""
    completed_on = event.payload.get('completed_on')
    if completed_on:
        return date.fromisoformat(completed_on)
    return event.occurred_at.astimezone(TZ).date()


@contextmanager
def journaled(events: list[Recorded]) -> Iterator[Path]:
    """A source directory whose journal holds `events`, in order."""
    with TemporaryDirectory() as tmp:
        directory = Path(tmp)
        journal = Journal(directory)
        for event in events:
            journal.append(
                event.type,
                f'task/{event.task_id}',
                event.payload,
                actor='agent',
                source_file='a-list.md',
                occurred_at=event.occurred_at.isoformat(),
            )
        yield directory


def observed(directory: Path, selector: str, form: str) -> Any:
    """What `get_history` answers in `form`: JSON read back, or text."""
    conf = Mock(spec=['view', 'format'])
    conf.view = Mock(spec=['source_dir'])
    conf.view.source_dir = str(directory)
    conf.format = form
    try:
        answer = get_history(conf, NOW, selector=selector)
    except ValueError as error:
        return refusal(error)
    return loads(answer) if form == 'json' else answer
