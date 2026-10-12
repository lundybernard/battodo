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
    StreamSelection,
    TaskHistory,
    TaskStream,
)

SRC = 'battodo.history'
# A zone ten hours behind UTC, which reads from no disk.
ZONE = timezone(timedelta(hours=-10))
# A zone thirteen hours ahead of UTC, on the next day from ZONE.
AHEAD = timezone(timedelta(hours=13))


class TaskHistoryTests(TestCase):
    """Unit tests for battodo.history.TaskHistory."""

    def setUp(t) -> None:
        t.journal = Mock(spec=['streams'])
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

    @patch.object(TaskHistory, 'stream', new_callable=PropertyMock)
    def test_task_id(t, stream: PropertyMock) -> None:
        stream.return_value = Mock(spec=['task_id'], task_id='ab12cd')
        ret = t.th.task_id
        t.assertEqual(ret, 'ab12cd')

    @patch(f'{SRC}.StreamSelection', autospec=True)
    @patch.object(TaskHistory, 'streams', new_callable=PropertyMock)
    def test_stream(
        t,
        streams: PropertyMock,
        stream_selection: MagicMock,
    ) -> None:
        streams.return_value = sentinel.streams

        ret = t.th.stream

        stream_selection.assert_called_once_with(
            sentinel.streams, 'a selector'
        )
        t.assertIs(ret, stream_selection.return_value.stream)

    @patch(f'{SRC}.TaskStream', autospec=True)
    def test_streams(t, task_stream: MagicMock) -> None:
        t.journal.streams = {
            'task/aa': sentinel.aa_events,
            'task/bb': sentinel.bb_events,
        }
        task_stream.side_effect = [sentinel.aa, sentinel.bb]

        ret = t.th.streams

        t.assertEqual(ret, [sentinel.aa, sentinel.bb])
        t.assertEqual(
            task_stream.call_args_list,
            [
                call('task/aa', sentinel.aa_events, sentinel.zone),
                call('task/bb', sentinel.bb_events, sentinel.zone),
            ],
        )

    @patch.object(TaskHistory, 'stream', new_callable=PropertyMock)
    def test_title(t, stream: PropertyMock) -> None:
        stream.return_value = Mock(spec=['title'], title='A task title')
        ret = t.th.title
        t.assertEqual(ret, 'A task title')

    @patch(f'{SRC}.HistoryEntry', autospec=True)
    @patch.object(TaskHistory, 'stream', new_callable=PropertyMock)
    def test_entries(
        t, stream: PropertyMock, history_entry: MagicMock
    ) -> None:
        stream.return_value = Mock(spec=['events'])
        stream.return_value.events = [
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


class StreamSelectionTests(TestCase):
    """Unit tests for battodo.history.StreamSelection."""

    def setUp(t) -> None:
        t.permit = a_stream('ab12cd', 'Renew the permit', 1)
        t.follow_up = a_stream('zz99yy', 'Follow up on ab12cd', 2)
        # The later event of a tie on 2026-09-30 is the sweep's.
        t.water = a_stream('qq11rr', 'Water the plants', 30)
        t.sweep = a_stream('dd44ee', 'Sweep the plants', 30)
        t.water.seq, t.sweep.seq = 5, 6
        t.untitled = a_stream('ee55ff', None, 3)
        t.streams = [t.permit, t.follow_up, t.water, t.sweep, t.untitled]
        t.ss = StreamSelection(t.streams, 'a selector')

    @patch.object(StreamSelection, 'candidates', new_callable=PropertyMock)
    def test_stream(t, candidates: PropertyMock) -> None:
        with t.subTest('the one stream the selector names'):
            candidates.return_value = [t.water]
            ret = t.ss.stream
            t.assertIs(ret, t.water)

        refused = {
            'no stream': (
                [],
                "no task in the journal matches 'a selector'",
            ),
            'several streams, each on a line, newest first': (
                [t.permit, t.water, t.sweep],
                (
                    "'a selector' matches 3 tasks in the journal:\n"
                    'dd44ee  2026-09-30  Sweep the plants\n'
                    'qq11rr  2026-09-30  Water the plants\n'
                    'ab12cd  2026-09-01  Renew the permit'
                ),
            ),
        }
        for name, (found, message) in refused.items():
            with t.subTest(name):
                candidates.return_value = found

                with t.assertRaises(ValueError) as caught:
                    _ = t.ss.stream

                t.assertEqual(str(caught.exception), message)

    def test_candidates(t) -> None:
        cases = {
            'an id names its stream, over the titles that quote it': (
                'ab12cd',
                [t.permit],
            ),
            'a stream with no title, by id': ('ee55ff', [t.untitled]),
            'part of a title, in any case': ('WATER', [t.water]),
            'part of several titles, in journal order': (
                'plants',
                [t.water, t.sweep],
            ),
            'no title holds it': ('nothing', []),
        }
        for name, (selector, expected) in cases.items():
            with t.subTest(name):
                t.ss.selector = selector
                ret = t.ss.candidates
                t.assertEqual(ret, expected)


def a_stream(task_id: str, title: str | None, day: int) -> Any:
    """A stand-in for one stream whose last event falls on a September day.

    Its last event is the `day`-th of the journal.
    """
    stream = Mock(spec=['task_id', 'title', 'day', 'seq'])
    stream.task_id, stream.title = task_id, title
    stream.day, stream.seq = date(2026, 9, day), day
    return stream


class TaskStreamTests(TestCase):
    """Unit tests for battodo.history.TaskStream."""

    def setUp(t) -> None:
        t.events: list[dict[str, Any]] = [
            {'payload': {'delta': {}, 'snapshot': {'title': 'A first'}}},
            {
                'payload': {
                    'delta': {'title': ['A second', 'A third']},
                    'snapshot': {'title': 'A second'},
                },
            },
            {
                'payload': {
                    'snapshot': {'title': 'A checklist item'},
                    'checklist_item': True,
                },
            },
        ]
        t.ts = TaskStream('task/ab12cd', t.events, ZONE)

    def test_task_id(t) -> None:
        ret = t.ts.task_id
        t.assertEqual(ret, 'ab12cd')

    @patch.object(TaskStream, 'own', new_callable=PropertyMock)
    def test_title(t, own: PropertyMock) -> None:
        cases = {
            'the snapshot title of the last event of its own': (
                [{'payload': {'snapshot': {'title': 'A first'}}}],
                'A first',
            ),
            'with its title delta applied': (
                [t.events[0], t.events[1]],
                'A third',
            ),
            'none without an event of its own': ([], None),
        }
        for name, (events, expected) in cases.items():
            with t.subTest(name):
                own.return_value = events
                ret = t.ts.title
                t.assertEqual(ret, expected)

    @patch(f'{SRC}.HistoryEntry', autospec=True)
    def test_day(t, history_entry: MagicMock) -> None:
        ret = t.ts.day
        history_entry.assert_called_once_with(t.events[-1], ZONE)
        t.assertIs(ret, history_entry.return_value.day)

    def test_seq(t) -> None:
        t.events[-1]['seq'] = 7
        ret = t.ts.seq
        t.assertEqual(ret, 7)

    @patch.object(TaskStream, 'own', new_callable=PropertyMock)
    def test_closed(t, own: PropertyMock) -> None:
        cases = {
            'a stream with no event of its own': ([], False),
            'a completion closes the task': (
                [{'type': 'TaskCompleted', 'payload': {'delta': {}}}],
                True,
            ),
            'a scratch closes it too': (
                [{'type': 'TaskScratched', 'payload': {'delta': {}}}],
                True,
            ),
            'a completion that reschedules leaves it open': (
                [
                    {
                        'type': 'TaskCompleted',
                        'payload': {'delta': {'DUE': ['a', 'b']}},
                    },
                ],
                False,
            ),
            'a later event of its own reopens it': (
                [
                    {'type': 'TaskCompleted', 'payload': {'delta': {}}},
                    {'type': 'TaskUpdated', 'payload': {'delta': {}}},
                ],
                False,
            ),
        }
        for name, (events, expected) in cases.items():
            with t.subTest(name):
                own.return_value = events
                ret = t.ts.closed
                t.assertIs(ret, expected)

    @patch.object(TaskStream, 'own', new_callable=PropertyMock)
    def test_snapshot(t, own: PropertyMock) -> None:
        with t.subTest('the snapshot of the last event of its own'):
            own.return_value = t.events[:2]
            ret = t.ts.snapshot
            t.assertEqual(ret, {'title': 'A second'})

        with t.subTest('none without an event of its own'):
            own.return_value = []
            ret = t.ts.snapshot
            t.assertIsNone(ret)

    @patch.object(TaskStream, 'snapshot', new_callable=PropertyMock)
    def test_list_name(t, snapshot: PropertyMock) -> None:
        cases = {
            'the list the snapshot names': ({'list': 'chores'}, 'chores'),
            'none where it names none': ({'title': 'A task'}, None),
            'none without a snapshot': (None, None),
        }
        for name, (found, expected) in cases.items():
            with t.subTest(name):
                snapshot.return_value = found
                ret = t.ts.list_name
                t.assertEqual(ret, expected)

    @patch.object(TaskStream, 'own', new_callable=PropertyMock)
    def test_nested(t, own: PropertyMock) -> None:
        cases = {
            'a path past its own title': (
                'A subtask',
                'A task > A subtask',
                True,
            ),
            'its own title alone': ('A subtask', 'A subtask', False),
            'a title that holds the separator': ('A > B', 'A > B', False),
            'no ancestry recorded': ('A subtask', None, False),
        }
        for name, (title, ancestry, expected) in cases.items():
            with t.subTest(name):
                payload: dict[str, Any] = {'snapshot': {'title': title}}
                if ancestry is not None:
                    payload['ancestry'] = ancestry
                own.return_value = [{'payload': payload}]

                ret = t.ts.nested

                t.assertIs(ret, expected)

        with t.subTest('a stream with no event of its own'):
            own.return_value = []
            ret = t.ts.nested
            t.assertFalse(ret)

    @patch.object(TaskStream, 'own', new_callable=PropertyMock)
    def test_parent_id(t, own: PropertyMock) -> None:
        with t.subTest('the parent its add names'):
            own.return_value = [
                {'payload': {'snapshot': {}, 'parent': 'pf11pf'}},
                {'payload': {'snapshot': {}}},
            ]
            ret = t.ts.parent_id
            t.assertEqual(ret, 'pf11pf')

        with t.subTest('none where no event names one'):
            own.return_value = [{'payload': {'snapshot': {}}}]
            ret = t.ts.parent_id
            t.assertIsNone(ret)

    def test_checklist_titles(t) -> None:
        ret = t.ts.checklist_titles
        t.assertEqual(ret, ['A checklist item'])

    def test_own(t) -> None:
        ret = t.ts.own
        # A checklist item's event belongs to the item, not the task.
        t.assertEqual(ret, t.events[:2])


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
