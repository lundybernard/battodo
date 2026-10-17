import json
from io import TextIOWrapper
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch, sentinel

from ..journal import (
    JOURNAL_DIRNAME,
    JOURNAL_FILENAME,
    LOCK_EX,
    LOCK_UN,
    SCHEMA_VERSION,
    Journal,
    new_task_id,
)

SRC = 'battodo.journal'
# The instant the mocked clock reports.
STAMP = '2026-08-05T17:30:00+00:00'


class NewTaskIdTests(TestCase):
    """Unit tests for battodo.journal.new_task_id."""

    def test_shape(t) -> None:
        for _ in range(20):
            value = new_task_id()

            t.assertEqual(len(value), 6)
            t.assertTrue(
                all(c in '0123456789abcdefghijklmnopqrstuvwxyz' for c in value)
            )

    def test_varies(t) -> None:
        ids = {new_task_id() for _ in range(20)}
        another = {new_task_id()}
        t.assertNotEqual(ids, another)


class JournalTests(TestCase):
    """Unit tests for battodo.journal.Journal.

    The journal with its file, its lock and its clock stood in for.
    """

    Path: MagicMock
    flock: MagicMock
    fsync: MagicMock
    uuid4: MagicMock
    datetime: MagicMock

    def setUp(t) -> None:
        for target in ('Path', 'flock', 'fsync', 'uuid4', 'datetime'):
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        t.uuid4.return_value = 'ffff-1'
        t.datetime.now.return_value.isoformat.return_value = STAMP

        t.file = MagicMock(spec=Path)
        t.source = t.Path.return_value.expanduser.return_value
        t.journal_dir = MagicMock(spec=Path)
        t.source.__truediv__.return_value = t.journal_dir
        t.journal_dir.__truediv__.return_value = t.file
        t.handle = MagicMock(spec=TextIOWrapper)
        t.file.open.return_value.__enter__.return_value = t.handle

        t.journal = Journal(sentinel.source_dir)

    def test_path(t) -> None:
        with t.subTest('the constructor derives nothing'):
            t.Path.assert_not_called()

        with t.subTest('the log sits in the journal directory of the source'):
            ret = t.journal.path

            t.assertEqual(ret, t.file)
            t.source.__truediv__.assert_called_once_with(JOURNAL_DIRNAME)
            t.journal_dir.__truediv__.assert_called_once_with(JOURNAL_FILENAME)

        with t.subTest('a ~ in the source expands to the home directory'):
            t.Path.return_value.expanduser.assert_called_once_with()

    def test_text(t) -> None:
        with t.subTest('a journal that is not there is empty text'):
            t.file.exists.return_value = False

            ret = t.journal.text

            t.assertEqual(ret, '')
            t.file.read_text.assert_not_called()

        with t.subTest('otherwise the file it points at'):
            t.journal.__dict__.pop('text', None)
            t.file.exists.return_value = True
            t.file.read_text.return_value = sentinel.text

            ret = t.journal.text

            t.assertEqual(ret, sentinel.text)
            t.file.read_text.assert_called_once_with(encoding='utf-8')

    def test_events(t) -> None:
        with t.subTest('every non-blank line is one event, in order'):
            t.journal.text = '{"seq": 1}\n\n{"seq": 2}\n'
            ret = t.journal.events
            t.assertEqual(ret, [{'seq': 1}, {'seq': 2}])

        with t.subTest('empty text holds no events'):
            t.journal.__dict__.pop('events', None)
            t.journal.text = ''

            ret = t.journal.events

            t.assertEqual(ret, [])

    def test_streams(t) -> None:
        t.journal.events = [
            {'seq': 1, 'stream_id': 'task/bb'},
            {'seq': 2, 'stream_id': 'task/aa'},
            {'seq': 3, 'stream_id': 'task/bb'},
        ]

        ret = t.journal.streams

        # In the order of its first event, each in journal order.
        t.assertEqual(
            list(ret.items()),
            [
                (
                    'task/bb',
                    [
                        {'seq': 1, 'stream_id': 'task/bb'},
                        {'seq': 3, 'stream_id': 'task/bb'},
                    ],
                ),
                ('task/aa', [{'seq': 2, 'stream_id': 'task/aa'}]),
            ],
        )

    def test_append(t) -> None:
        # A stale read: the file has gained an event since.
        t.journal.events = [{'stream_id': 'task/aa'}]
        t.file.exists.return_value = True
        t.file.read_text.return_value = (
            '{"stream_id": "task/aa"}\n{"stream_id": "task/bb"}\n'
        )

        ret = t.journal.append(
            'TaskUpdated',
            'task/aa',
            {'delta': {}},
            actor='agent',
            source_file='a-list.md',
            occurred_at='2026-08-05T09:00:00+00:00',
        )

        with t.subTest('the journal directory is made before the write'):
            t.file.parent.mkdir.assert_called_once_with(
                parents=True,
                exist_ok=True,
            )

        with t.subTest('the file opens for append, as UTF-8'):
            t.file.open.assert_called_once_with('a', encoding='utf-8')

        with t.subTest('under an exclusive lock, released at the end'):
            taken, released = t.flock.call_args_list
            t.assertEqual(taken.args[1], LOCK_EX)
            t.assertEqual(released.args[1], LOCK_UN)

        with t.subTest('the event counts the file as the lock found it'):
            t.assertEqual(ret['seq'], 3)
            t.assertEqual(ret['stream_seq'], 2)

        with t.subTest('the change time is given, the record time is now'):
            t.assertEqual(ret['occurred_at'], '2026-08-05T09:00:00+00:00')
            t.assertEqual(ret['recorded_at'], STAMP)

        with t.subTest('the event returned is the one written'):
            t.handle.write.assert_called_once_with(json.dumps(ret) + '\n')

        with t.subTest('and the write drops the read it invalidates'):
            t.assertNotIn('text', t.journal.__dict__)
            t.assertNotIn('events', t.journal.__dict__)

    def test_next_event(t) -> None:
        t.journal.events = [
            {'stream_id': 'task/aa'},
            {'stream_id': 'task/bb'},
        ]

        with t.subTest('the envelope carries the event and its metadata'):
            ret = t.journal.next_event(
                'TaskUpdated',
                'task/aa',
                {'delta': {}},
                actor='agent',
                source_file='a-list.md',
                occurred_at=None,
                recorded_at=STAMP,
            )

            t.assertEqual(
                ret,
                {
                    'seq': 3,
                    'event_id': 'ffff-1',
                    'stream_id': 'task/aa',
                    'stream_seq': 2,
                    'type': 'TaskUpdated',
                    'schema_version': SCHEMA_VERSION,
                    'occurred_at': STAMP,
                    'recorded_at': STAMP,
                    'metadata': {
                        'actor': 'agent',
                        'source_file': 'a-list.md',
                    },
                    'payload': {'delta': {}},
                },
            )

        with t.subTest('a given time is when the change happened'):
            ret = t.journal.next_event(
                'TaskUpdated',
                'task/aa',
                {},
                actor='agent',
                source_file='a-list.md',
                occurred_at='2026-08-05T09:00:00+00:00',
                recorded_at=STAMP,
            )

            t.assertEqual(ret['occurred_at'], '2026-08-05T09:00:00+00:00')
            t.assertEqual(ret['recorded_at'], STAMP)

    def test_next_seq(t) -> None:
        with t.subTest('the first event is one'):
            t.journal.events = []
            ret = t.journal.next_seq
            t.assertEqual(ret, 1)

        with t.subTest('one past the events of the text'):
            t.journal.events = [
                {'stream_id': 'task/aa'},
                {'stream_id': 'task/bb'},
            ]

            ret = t.journal.next_seq

            t.assertEqual(ret, 3)

    def test_next_stream_seq(t) -> None:
        t.journal.events = [
            {'stream_id': 'task/aa'},
            {'stream_id': 'task/bb'},
            {'stream_id': 'task/aa'},
        ]

        with t.subTest('one past the events of the stream'):
            ret = t.journal.next_stream_seq('task/aa')
            t.assertEqual(ret, 3)

        with t.subTest('a stream with no events starts at one'):
            ret = t.journal.next_stream_seq('task/cc')
            t.assertEqual(ret, 1)

    def test__write(t) -> None:
        t.journal._write(t.handle, {'seq': 1})

        with t.subTest('the event is written as one JSON line'):
            t.handle.write.assert_called_once_with('{"seq": 1}\n')

        with t.subTest('and flushed to the disk it claims to be on'):
            t.handle.flush.assert_called_once_with()
            t.fsync.assert_called_once_with(t.handle.fileno.return_value)
