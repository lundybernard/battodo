"""Contract tests for the history read, against a real journal.

The journal is written and read back from a temporary directory. This
layer asserts state; interaction checks stay in the isolation tests
beside the code.
"""

import json
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import TestCase
from unittest.mock import Mock

from battodo.history import (
    HistoryEntry,
    HistoryJsonView,
    HistoryView,
    StreamSelection,
    TaskHistory,
    TaskStream,
)
from battodo.journal import Journal
from tests.environment import TZ

NOW = datetime(2026, 10, 5, 10, 30, tzinfo=TZ)
# Each event of the history fixture: type, stream, payload, occurred_at.
# Every stream but the last holds an event of the task's own.
HISTORY = (
    (
        'TaskAdded',
        'task/ab12cd',
        {'delta': {}, 'snapshot': {'title': 'Renew the permit'}},
        '2026-09-01T16:00:00+00:00',
    ),
    (
        'TaskUpdated',
        'task/ab12cd',
        {
            'delta': {
                'title': ['Renew the permit', 'Renew the parking permit']
            },
            'snapshot': {'title': 'Renew the permit'},
            'attrs': {'note': 'Renamed'},
        },
        '2026-09-02T16:00:00+00:00',
    ),
    (
        'TaskCompleted',
        'task/ab12cd',
        {
            'delta': {'done': [False, True]},
            'snapshot': {'title': 'Renew the parking permit'},
            'completed_on': '2026-09-30',
            'attrs': {'cost': '45.00', 'note': 'Renewed online'},
        },
        '2026-10-01T16:00:00+00:00',
    ),
    (
        'TaskCompleted',
        'task/zz99yy',
        {'delta': {'done': [False, True]}, 'snapshot': {'title': 'Water'}},
        '2026-08-01T03:00:00+00:00',
    ),
    (
        'TaskCompleted',
        'task/ab12cd',
        {
            'delta': {'done': [False, True]},
            'snapshot': {'title': 'Print the receipt'},
            'checklist_item': True,
            'completed_on': '2026-10-01',
        },
        '2026-10-01T17:00:00+00:00',
    ),
    (
        'TaskAnnotated',
        'task/ab12cd',
        {
            'snapshot': {'title': 'Renew the parking permit'},
            'attrs': {'note': 'Sticker on the car'},
        },
        '2026-10-02T05:30:00+00:00',
    ),
    (
        'TaskUpdated',
        'task/zz99yy',
        {
            'delta': {'title': ['Water', 'Water the plants']},
            'snapshot': {'title': 'Water'},
        },
        '2026-08-02T16:00:00+00:00',
    ),
    (
        'TaskAdded',
        'task/qq11rr',
        {'delta': {}, 'snapshot': {'title': 'Sweep the deck'}},
        '2026-08-03T16:00:00+00:00',
    ),
    (
        'TaskAdded',
        'task/ee55ff',
        {'delta': {}, 'snapshot': {'title': 'Follow up on ab12cd'}},
        '2026-08-03T16:00:00+00:00',
    ),
    (
        'TaskScratched',
        'task/dd44ee',
        {
            'delta': {'removed': [False, True]},
            'snapshot': {'title': 'Buy nails'},
            'checklist_item': True,
        },
        '2026-08-04T16:00:00+00:00',
    ),
    (
        'TaskAdded',
        'task/pf11pf',
        {'delta': {}, 'snapshot': {'title': 'Paint a fence'}},
        '2026-08-05T16:00:00+00:00',
    ),
    (
        'TaskAdded',
        'task/bp22bp',
        {
            'delta': {},
            'snapshot': {'title': 'Buy paint'},
            'parent': 'pf11pf',
        },
        '2026-08-05T16:00:00+00:00',
    ),
    (
        'TaskCompleted',
        'task/bp22bp',
        {
            'delta': {'done': [False, True]},
            'snapshot': {'title': 'Buy paint', 'list': 'chores'},
            'ancestry': 'Paint a fence > Buy paint',
            'completed_on': '2026-08-06',
        },
        '2026-08-06T16:00:00+00:00',
    ),
    (
        'TaskScratched',
        'task/pf11pf',
        {
            'delta': {'removed': [False, True]},
            'snapshot': {'title': 'Paint a fence', 'list': 'chores'},
            'ancestry': 'Paint a fence',
        },
        '2026-08-07T16:00:00+00:00',
    ),
    (
        'TaskCompleted',
        'task/rx33rx',
        {
            'delta': {'done': [False, True]},
            'snapshot': {'title': 'Rx refill', 'list': 'chores'},
            'completed_on': '2026-08-08',
        },
        '2026-08-08T16:00:00+00:00',
    ),
    (
        'TaskUpdated',
        'task/rx33rx',
        {
            'delta': {'DUE': [None, '2026-09-08'], 'done': [True, False]},
            'snapshot': {'title': 'Rx refill', 'list': 'chores'},
        },
        '2026-08-09T16:00:00+00:00',
    ),
    (
        'TaskUpdated',
        'task/rx33rx',
        {
            'delta': {'DUE': ['2026-09-08', '2026-09-09']},
            'snapshot': {'title': 'Rx refill', 'list': 'chores'},
        },
        '2026-08-10T16:00:00+00:00',
    ),
)

# The history of task/ab12cd, as each form lays it out.
PERMIT_TEXT = """Renew the parking permit [ID:ab12cd]
  2026-10-01  TaskAnnotated
    note=Sticker on the car
  2026-10-01  TaskCompleted (checklist item)
  2026-09-30  TaskCompleted
    cost=45.00
    note=Renewed online
  2026-09-02  TaskUpdated
    note=Renamed"""
PERMIT_DATA = {
    'id': 'ab12cd',
    'title': 'Renew the parking permit',
    'entries': [
        {
            'kind': 'TaskAnnotated',
            'checklist_item': False,
            'day': '2026-10-01',
            'attrs': {'note': 'Sticker on the car'},
        },
        {
            'kind': 'TaskCompleted',
            'checklist_item': True,
            'day': '2026-10-01',
            'attrs': {},
        },
        {
            'kind': 'TaskCompleted',
            'checklist_item': False,
            'day': '2026-09-30',
            'attrs': {'cost': '45.00', 'note': 'Renewed online'},
        },
        {
            'kind': 'TaskUpdated',
            'checklist_item': False,
            'day': '2026-09-02',
            'attrs': {'note': 'Renamed'},
        },
    ],
}


class TaskHistoryTests(TestCase):
    """Contract tests for battodo.history.TaskHistory."""

    maxDiff = None

    def setUp(t) -> None:
        t.dir = history_source(t)

    def test_from_config(t) -> None:
        conf = Mock(spec=['view'])
        conf.view = Mock(spec=['source_dir'])
        conf.view.source_dir = str(t.dir)

        ret = TaskHistory.from_config(conf, NOW, selector='parking')

        t.assertEqual(ret.task_id, 'ab12cd')
        t.assertEqual(ret.zone, TZ)

    def test_task_id(t) -> None:
        cases = {
            'an id names its stream, over the titles that quote it': (
                'ab12cd',
                'ab12cd',
            ),
            'part of the current title, in any case': ('PARKING', 'ab12cd'),
            'a title from the last title delta': ('the plants', 'zz99yy'),
            'a stream with no event of its own, by id': ('dd44ee', 'dd44ee'),
        }
        for name, (selector, expected) in cases.items():
            with t.subTest(name):
                ret = history_of(t.dir, selector).task_id
                t.assertEqual(ret, expected)

        refused = {
            'a title the task no longer carries': (
                'Renew the permit',
                "no task in the journal matches 'Renew the permit'",
            ),
            'the title of a checklist item': (
                'Buy nails',
                "no task in the journal matches 'Buy nails'",
            ),
            'a task with no stream': (
                'Legacy priority',
                "no task in the journal matches 'Legacy priority'",
            ),
            'a part of several titles, each named': (
                'the',
                (
                    "'the' matches 3 tasks in the journal:\n"
                    'ab12cd  2026-10-01  Renew the parking permit\n'
                    'qq11rr  2026-08-03  Sweep the deck\n'
                    'zz99yy  2026-08-02  Water the plants'
                ),
            ),
        }
        for name, (selector, message) in refused.items():
            with t.subTest(name):
                with t.assertRaises(ValueError) as caught:
                    _ = history_of(t.dir, selector).task_id

                t.assertEqual(str(caught.exception), message)

    def test_title(t) -> None:
        cases = {
            'the snapshot title of the last event of its own': (
                'ab12cd',
                'Renew the parking permit',
            ),
            'with its title delta applied': ('zz99yy', 'Water the plants'),
            'none where no event of its own records one': ('dd44ee', None),
        }
        for name, (selector, expected) in cases.items():
            with t.subTest(name):
                ret = history_of(t.dir, selector).title
                t.assertEqual(ret, expected)

    def test_entries(t) -> None:
        cases = {
            'newest first, the later event first in a tie': (
                'ab12cd',
                [
                    (
                        'TaskAnnotated',
                        False,
                        date(2026, 10, 1),
                        {'note': 'Sticker on the car'},
                    ),
                    ('TaskCompleted', True, date(2026, 10, 1), {}),
                    (
                        'TaskCompleted',
                        False,
                        date(2026, 9, 30),
                        {'cost': '45.00', 'note': 'Renewed online'},
                    ),
                    (
                        'TaskUpdated',
                        False,
                        date(2026, 9, 2),
                        {'note': 'Renamed'},
                    ),
                ],
            ),
            'a completion with no completed_on, on its local day': (
                'zz99yy',
                [('TaskCompleted', False, date(2026, 7, 31), {})],
            ),
            'a stream with no entries': ('qq11rr', []),
            'a scratch with no attributes': (
                'pf11pf',
                [('TaskScratched', False, date(2026, 8, 7), {})],
            ),
            'a reopen, beside its completion; a plain update is no entry': (
                'rx33rx',
                [
                    ('TaskUpdated', False, date(2026, 8, 9), {}),
                    ('TaskCompleted', False, date(2026, 8, 8), {}),
                ],
            ),
        }
        for name, (selector, expected) in cases.items():
            with t.subTest(name):
                ret = history_of(t.dir, selector).entries
                t.assertEqual([described(entry) for entry in ret], expected)


class StreamSelectionTests(TestCase):
    """Contract tests for battodo.history.StreamSelection."""

    def setUp(t) -> None:
        t.dir = history_source(t)

    def test_stream(t) -> None:
        cases = {
            'an id names its stream, over the titles that quote it': (
                'ab12cd',
                'ab12cd',
            ),
            'part of the current title, in any case': ('PLANTS', 'zz99yy'),
            'a stream with no event of its own, by id': ('dd44ee', 'dd44ee'),
        }
        for name, (selector, expected) in cases.items():
            with t.subTest(name):
                ret = selection_of(t.dir, selector).stream
                t.assertEqual(ret.task_id, expected)

        refused = {
            'the title of a checklist item': (
                'Buy nails',
                "no task in the journal matches 'Buy nails'",
            ),
            'a part of several titles, each named': (
                'the',
                (
                    "'the' matches 3 tasks in the journal:\n"
                    'ab12cd  2026-10-01  Renew the parking permit\n'
                    'qq11rr  2026-08-03  Sweep the deck\n'
                    'zz99yy  2026-08-02  Water the plants'
                ),
            ),
        }
        for name, (selector, message) in refused.items():
            with t.subTest(name):
                with t.assertRaises(ValueError) as caught:
                    _ = selection_of(t.dir, selector).stream

                t.assertEqual(str(caught.exception), message)


class TaskStreamTests(TestCase):
    """Contract tests for battodo.history.TaskStream."""

    def setUp(t) -> None:
        streams = Journal(history_source(t)).streams
        t.permit = TaskStream('task/ab12cd', streams['task/ab12cd'], TZ)
        t.nails = TaskStream('task/dd44ee', streams['task/dd44ee'], TZ)
        t.fence = TaskStream('task/pf11pf', streams['task/pf11pf'], TZ)
        t.paint = TaskStream('task/bp22bp', streams['task/bp22bp'], TZ)

    def test_task_id(t) -> None:
        ret = t.permit.task_id
        t.assertEqual(ret, 'ab12cd')

    def test_title(t) -> None:
        with t.subTest('the title of the last event of its own'):
            ret = t.permit.title
            t.assertEqual(ret, 'Renew the parking permit')

        with t.subTest('none without an event of its own'):
            ret = t.nails.title
            t.assertIsNone(ret)

    def test_day(t) -> None:
        ret = t.permit.day
        # The note of 2026-10-02 05:30 UTC, on its local day.
        t.assertEqual(ret, date(2026, 10, 1))

    def test_seq(t) -> None:
        ret = t.permit.seq
        t.assertEqual(ret, 6)

    def test_closed(t) -> None:
        cases = {
            'a note after the completion: open': (t.permit, False),
            'a scratch closes the task': (t.fence, True),
            'and so does a completion': (t.paint, True),
            'no event of its own: open': (t.nails, False),
        }
        for name, (stream, expected) in cases.items():
            with t.subTest(name):
                ret = stream.closed
                t.assertIs(ret, expected)

    def test_snapshot(t) -> None:
        ret = t.fence.snapshot
        t.assertEqual(ret, {'title': 'Paint a fence', 'list': 'chores'})

    def test_list_name(t) -> None:
        ret = t.fence.list_name
        t.assertEqual(ret, 'chores')

    def test_nested(t) -> None:
        with t.subTest('a subtask'):
            ret = t.paint.nested
            t.assertTrue(ret)

        with t.subTest('a top-level task'):
            ret = t.fence.nested
            t.assertFalse(ret)

    def test_parent_id(t) -> None:
        with t.subTest('the parent its add names'):
            ret = t.paint.parent_id
            t.assertEqual(ret, 'pf11pf')

        with t.subTest('none for a top-level task'):
            ret = t.fence.parent_id
            t.assertIsNone(ret)

    def test_checklist_titles(t) -> None:
        ret = t.permit.checklist_titles
        t.assertEqual(ret, ['Print the receipt'])

    def test_own(t) -> None:
        ret = t.permit.own
        # The checklist item's completion is not the task's own.
        t.assertEqual(
            [event['type'] for event in ret],
            ['TaskAdded', 'TaskUpdated', 'TaskCompleted', 'TaskAnnotated'],
        )


class HistoryViewTests(TestCase):
    """Contract tests for battodo.history.HistoryView.text."""

    maxDiff = None

    def setUp(t) -> None:
        t.dir = history_source(t)

    def test_text(t) -> None:
        cases = {
            'the header, then each entry and its attributes': (
                'ab12cd',
                PERMIT_TEXT,
            ),
            'a stream with no entries is its header': (
                'qq11rr',
                'Sweep the deck [ID:qq11rr]',
            ),
            'no title recorded: the id alone heads it': (
                'dd44ee',
                '[ID:dd44ee]\n  2026-08-04  TaskScratched (checklist item)',
            ),
        }
        for name, (selector, expected) in cases.items():
            with t.subTest(name):
                ret = HistoryView(history_of(t.dir, selector)).text
                t.assertEqual(ret, expected)


class HistoryJsonViewTests(TestCase):
    """Contract tests for battodo.history.HistoryJsonView.json."""

    maxDiff = None

    def setUp(t) -> None:
        t.dir = history_source(t)

    def test_json(t) -> None:
        cases = {
            'the document the text form lays out': ('ab12cd', PERMIT_DATA),
            'no title recorded: null': (
                'dd44ee',
                {
                    'id': 'dd44ee',
                    'title': None,
                    'entries': [
                        {
                            'kind': 'TaskScratched',
                            'checklist_item': True,
                            'day': '2026-08-04',
                            'attrs': {},
                        },
                    ],
                },
            ),
        }
        for name, (selector, expected) in cases.items():
            with t.subTest(name):
                ret = HistoryJsonView(history_of(t.dir, selector)).json
                t.assertEqual(json.loads(ret), expected)


def history_source(t: TestCase) -> Path:
    """A source whose journal holds HISTORY, removed when the test ends."""
    tmp = TemporaryDirectory()
    t.addCleanup(tmp.cleanup)
    source = Path(tmp.name)
    journal = Journal(source)
    for event_type, stream_id, payload, occurred_at in HISTORY:
        journal.append(
            event_type,
            stream_id,
            payload,
            actor='agent',
            source_file='a-list.md',
            occurred_at=occurred_at,
        )
    return source


def history_of(source: Path, selector: str) -> TaskHistory:
    """The history `selector` names in `source`, read in TZ."""
    return TaskHistory(Journal(source), selector, TZ)


def selection_of(source: Path, selector: str) -> StreamSelection:
    """The selection `selector` makes of every stream in `source`."""
    streams = [
        TaskStream(stream_id, events, TZ)
        for stream_id, events in Journal(source).streams.items()
    ]
    return StreamSelection(streams, selector)


def described(entry: HistoryEntry) -> tuple[str, bool, date, dict[str, Any]]:
    """The kind, the checklist mark, the day and the attributes."""
    return (entry.kind, entry.checklist_item, entry.day, entry.attrs)
