from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest import TestCase
from unittest.mock import MagicMock, Mock, PropertyMock, call, patch, sentinel

from ..history import (
    HistoryEntry,
    HistoryEntryJsonView,
    HistoryEntryView,
    HistoryJsonView,
    HistoryView,
    TaskHistory,
)

SRC = 'battodo.history'
# A zone ten hours behind UTC, which reads from no disk.
ZONE = timezone(timedelta(hours=-10))
# A zone thirteen hours ahead of UTC, on the next day from ZONE.
AHEAD = timezone(timedelta(hours=13))


class TaskHistoryTests(TestCase):
    """Unit tests for battodo.history.TaskHistory."""

    def setUp(t) -> None:
        t.journal = Mock(spec=['events'])
        t.th = TaskHistory(t.journal, 'a selector', sentinel.zone)

    @patch(f'{SRC}.Journal', autospec=True)
    def test_from_config(t, journal: MagicMock) -> None:
        conf = Mock(spec=['view'])
        conf.view = Mock(spec=['source_dir'])
        conf.view.source_dir = '~/a-source-dir'
        now = Mock(spec=datetime)
        now.tzinfo = sentinel.zone

        ret = TaskHistory.from_config(conf, now, selector='a selector')

        journal.assert_called_once_with(Path('~/a-source-dir'))
        t.assertIs(ret.journal, journal.return_value)
        t.assertEqual(ret.selector, 'a selector')
        t.assertIs(ret.zone, sentinel.zone)

    @patch.object(TaskHistory, 'stream_id', new_callable=PropertyMock)
    def test_task_id(t, stream_id: PropertyMock) -> None:
        stream_id.return_value = 'task/ab12cd'
        ret = t.th.task_id
        t.assertEqual(ret, 'ab12cd')

    @patch.object(TaskHistory, 'titles', new_callable=PropertyMock)
    @patch.object(TaskHistory, 'stream_id', new_callable=PropertyMock)
    def test_title(t, stream_id: PropertyMock, titles: PropertyMock) -> None:
        stream_id.return_value = 'task/ab12cd'

        with t.subTest('the current title of the stream'):
            titles.return_value = {'task/ab12cd': 'A task title'}
            ret = t.th.title
            t.assertEqual(ret, 'A task title')

        with t.subTest('none where the stream records no title'):
            titles.return_value = {'task/zz99yy': 'Another task title'}
            ret = t.th.title
            t.assertIsNone(ret)

    @patch(f'{SRC}.HistoryEntry', autospec=True)
    @patch.object(TaskHistory, 'events', new_callable=PropertyMock)
    def test_entries(
        t, events: PropertyMock, history_entry: MagicMock
    ) -> None:
        events.return_value = [
            sentinel.added,
            sentinel.updated,
            sentinel.completed,
            sentinel.annotated,
        ]
        added = an_entry('TaskAdded', date(2026, 9, 1), {})
        updated = an_entry('TaskUpdated', date(2026, 9, 2), {'k': 'v'})
        completed = an_entry('TaskCompleted', date(2026, 9, 30), {})
        annotated = an_entry('TaskAnnotated', date(2026, 9, 30), {'k': 'v'})
        history_entry.side_effect = [added, updated, completed, annotated]

        ret = t.th.entries

        with t.subTest('each event is read in the zone of the history'):
            history_entry.assert_has_calls(
                [
                    call(sentinel.added, sentinel.zone),
                    call(sentinel.updated, sentinel.zone),
                    call(sentinel.completed, sentinel.zone),
                    call(sentinel.annotated, sentinel.zone),
                ]
            )

        with t.subTest('a completion, and another event with attributes'):
            # Newest first by day. In a tie, the later event comes first.
            t.assertEqual(ret, [annotated, completed, updated])

    @patch.object(TaskHistory, 'stream_id', new_callable=PropertyMock)
    def test_events(t, stream_id: PropertyMock) -> None:
        stream_id.return_value = 'task/aa'
        t.journal.events = [
            {'seq': 1, 'stream_id': 'task/aa'},
            {'seq': 2, 'stream_id': 'task/bb'},
            {'seq': 3, 'stream_id': 'task/aa'},
        ]

        ret = t.th.events

        t.assertEqual(
            ret,
            [
                {'seq': 1, 'stream_id': 'task/aa'},
                {'seq': 3, 'stream_id': 'task/aa'},
            ],
        )

    @patch.object(TaskHistory, 'titles', new_callable=PropertyMock)
    def test_stream_id(t, titles: PropertyMock) -> None:
        t.journal.events = [
            {'stream_id': 'task/ab12cd'},
            {'stream_id': 'task/zz99yy'},
        ]
        titles.return_value = {
            'task/zz99yy': 'Follow up on ab12cd',
            'task/qq11rr': 'Water the plants',
            'task/dd44ee': 'Sweep the plants',
        }
        cases = {
            'an id names its stream, over the titles that quote it': (
                'ab12cd',
                'task/ab12cd',
            ),
            'part of one title, in any case': ('WATER', 'task/qq11rr'),
        }
        for name, (selector, expected) in cases.items():
            with t.subTest(name):
                t.th.selector = selector
                ret = t.th.stream_id
                t.assertEqual(ret, expected)

        refused = {
            'no title holds it': (
                'nothing',
                "no task in the journal matches 'nothing'",
            ),
            'two do, each named': (
                'plants',
                (
                    "'plants' matches 2 tasks in the journal: "
                    "'Water the plants', 'Sweep the plants'"
                ),
            ),
        }
        for name, (selector, message) in refused.items():
            with t.subTest(name):
                t.th.selector = selector

                with t.assertRaises(ValueError) as caught:
                    _ = t.th.stream_id

                t.assertEqual(str(caught.exception), message)

    def test_titles(t) -> None:
        t.journal.events = [
            {
                'stream_id': 'task/aa',
                'payload': {'delta': {}, 'snapshot': {'title': 'A first'}},
            },
            {
                'stream_id': 'task/aa',
                'payload': {'snapshot': {'title': 'A second'}},
            },
            {
                'stream_id': 'task/bb',
                'payload': {
                    'delta': {'title': ['B before', 'B after']},
                    'snapshot': {'title': 'B before'},
                },
            },
            {
                'stream_id': 'task/aa',
                'payload': {
                    'snapshot': {'title': 'A checklist item'},
                    'checklist_item': True,
                },
            },
            {
                'stream_id': 'task/cc',
                'payload': {
                    'snapshot': {'title': 'C checklist item'},
                    'checklist_item': True,
                },
            },
        ]

        ret = t.th.titles

        # The last own event of aa, the delta of bb, no title for cc.
        t.assertEqual(ret, {'task/aa': 'A second', 'task/bb': 'B after'})


def an_entry(kind: str, day: date, attrs: dict[str, str]) -> Mock:
    """A stand-in for one entry of a history."""
    entry = Mock(spec=['kind', 'day', 'attrs'])
    entry.kind, entry.day, entry.attrs = kind, day, attrs
    return entry


class HistoryEntryTests(TestCase):
    """Unit tests for battodo.history.HistoryEntry."""

    def setUp(t) -> None:
        t.payload: dict[str, Any] = {}
        event = {
            'type': 'TaskCompleted',
            'occurred_at': '2026-10-02T08:30:00+00:00',
            'payload': t.payload,
        }
        t.he = HistoryEntry(event, ZONE)

    def test_kind(t) -> None:
        ret = t.he.kind
        t.assertEqual(ret, 'TaskCompleted')

    def test_checklist_item(t) -> None:
        with t.subTest('an event with no mark'):
            ret = t.he.checklist_item
            t.assertFalse(ret)

        with t.subTest('the event of a checklist item'):
            t.payload['checklist_item'] = True
            ret = t.he.checklist_item
            t.assertTrue(ret)

    def test_day(t) -> None:
        with t.subTest('the local day of occurred_at, in the zone'):
            ret = t.he.day
            t.assertEqual(ret, date(2026, 10, 1))

        with t.subTest('the same instant falls on another day elsewhere'):
            t.he.zone = AHEAD
            ret = t.he.day
            t.assertEqual(ret, date(2026, 10, 2))

        with t.subTest('the day the completion is for'):
            t.payload['completed_on'] = '2026-09-30'
            ret = t.he.day
            t.assertEqual(ret, date(2026, 9, 30))

    def test_attrs(t) -> None:
        with t.subTest('absent reads as none'):
            ret = t.he.attrs
            t.assertEqual(ret, {})

        with t.subTest('the attributes in recorded order'):
            t.payload['attrs'] = {'k': 'v', 'a': 'b'}
            ret = t.he.attrs
            t.assertEqual(list(ret.items()), [('k', 'v'), ('a', 'b')])


class HistoryViewTests(TestCase):
    """Unit tests for battodo.history.HistoryView."""

    def setUp(t) -> None:
        t.history = Mock(spec=['task_id', 'title', 'entries'])
        t.history.task_id = 'ab12cd'
        t.history.title = 'A task title'
        t.hv = HistoryView(t.history)

    @patch.object(HistoryView, 'entries', new_callable=PropertyMock)
    @patch.object(HistoryView, 'header', new_callable=PropertyMock)
    def test_text(t, header: PropertyMock, entries: PropertyMock) -> None:
        header.return_value = 'A header'

        with t.subTest('the header, then the lines of each entry'):
            entries.return_value = [
                Mock(spec=['lines'], lines=['  a day', '    k=v']),
                Mock(spec=['lines'], lines=['  another day']),
            ]

            ret = t.hv.text

            t.assertEqual(ret, 'A header\n  a day\n    k=v\n  another day')

        with t.subTest('a history with no entries is its header'):
            entries.return_value = []
            ret = t.hv.text
            t.assertEqual(ret, 'A header')

    def test_header(t) -> None:
        with t.subTest('the title, then the id'):
            ret = t.hv.header
            t.assertEqual(ret, 'A task title [ID:ab12cd]')

        with t.subTest('the id alone where no title is recorded'):
            t.history.title = None
            ret = t.hv.header
            t.assertEqual(ret, '[ID:ab12cd]')

    @patch(f'{SRC}.HistoryEntryView', autospec=True)
    def test_entries(t, history_entry_view: MagicMock) -> None:
        t.history.entries = [sentinel.first, sentinel.second]
        history_entry_view.side_effect = [sentinel.shown, sentinel.next]

        ret = t.hv.entries

        t.assertEqual(ret, [sentinel.shown, sentinel.next])
        history_entry_view.assert_has_calls(
            [call(sentinel.first), call(sentinel.second)]
        )


class HistoryEntryViewTests(TestCase):
    """Unit tests for battodo.history.HistoryEntryView."""

    def setUp(t) -> None:
        t.entry = Mock(spec=['kind', 'checklist_item', 'day', 'attrs'])
        t.entry.kind = 'TaskCompleted'
        t.entry.checklist_item = False
        t.entry.day = date(2026, 9, 30)
        t.entry.attrs = {}
        t.hev = HistoryEntryView(t.entry)

    @patch.object(HistoryEntryView, 'label', new_callable=PropertyMock)
    def test_lines(t, label: PropertyMock) -> None:
        label.return_value = 'A label'

        with t.subTest('the day and the label'):
            ret = t.hev.lines
            t.assertEqual(ret, ['  2026-09-30  A label'])

        with t.subTest('then each attribute, in recorded order'):
            t.entry.attrs = {'place': 'Main St, Suite 4', 'cost': '45.00'}

            ret = t.hev.lines

            t.assertEqual(
                ret,
                [
                    '  2026-09-30  A label',
                    '    place=Main St, Suite 4',
                    '    cost=45.00',
                ],
            )

    def test_label(t) -> None:
        with t.subTest('the kind'):
            ret = t.hev.label
            t.assertEqual(ret, 'TaskCompleted')

        with t.subTest('marked on the event of a checklist item'):
            t.entry.checklist_item = True
            ret = t.hev.label
            t.assertEqual(ret, 'TaskCompleted (checklist item)')


class HistoryJsonViewTests(TestCase):
    """Unit tests for battodo.history.HistoryJsonView."""

    def setUp(t) -> None:
        t.history = Mock(spec=['task_id', 'title', 'entries'])
        t.history.task_id = 'ab12cd'
        t.history.title = 'A task title'
        t.hjv = HistoryJsonView(t.history)

    @patch.object(HistoryJsonView, 'data', new_callable=PropertyMock)
    def test_json(t, data: PropertyMock) -> None:
        data.return_value = {'id': 'ab12cd', 'entries': []}
        ret = t.hjv.json
        t.assertEqual(ret, '{\n  "id": "ab12cd",\n  "entries": []\n}')

    @patch.object(HistoryJsonView, 'entries', new_callable=PropertyMock)
    def test_data(t, entries: PropertyMock) -> None:
        entries.return_value = [Mock(spec=['data'], data={'k': 'v'})]

        with t.subTest('the id, the title and the entries'):
            ret = t.hjv.data
            t.assertEqual(
                ret,
                {
                    'id': 'ab12cd',
                    'title': 'A task title',
                    'entries': [{'k': 'v'}],
                },
            )

        with t.subTest('a title that is not recorded is null'):
            t.history.title = None
            ret = t.hjv.data
            t.assertIsNone(ret['title'])

    @patch(f'{SRC}.HistoryEntryJsonView', autospec=True)
    def test_entries(t, history_entry_json_view: MagicMock) -> None:
        t.history.entries = [sentinel.first, sentinel.second]
        history_entry_json_view.side_effect = [sentinel.shown, sentinel.next]

        ret = t.hjv.entries

        t.assertEqual(ret, [sentinel.shown, sentinel.next])
        history_entry_json_view.assert_has_calls(
            [call(sentinel.first), call(sentinel.second)]
        )


class HistoryEntryJsonViewTests(TestCase):
    """Unit tests for battodo.history.HistoryEntryJsonView."""

    def setUp(t) -> None:
        t.entry = Mock(spec=['kind', 'checklist_item', 'day', 'attrs'])
        t.entry.kind = 'TaskCompleted'
        t.entry.checklist_item = True
        t.entry.day = date(2026, 9, 30)
        t.entry.attrs = {'cost': '45.00'}
        t.hejv = HistoryEntryJsonView(t.entry)

    def test_data(t) -> None:
        ret = t.hejv.data
        t.assertEqual(
            ret,
            {
                'kind': 'TaskCompleted',
                'checklist_item': True,
                'day': '2026-09-30',
                'attrs': {'cost': '45.00'},
            },
        )
