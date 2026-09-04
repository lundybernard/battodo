import json
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

    def test_new_task_id(t) -> None:
        with t.subTest('six base36 characters'):
            for _ in range(20):
                value = new_task_id()
                t.assertEqual(len(value), 6)
                t.assertTrue(
                    all(
                        c in '0123456789abcdefghijklmnopqrstuvwxyz'
                        for c in value
                    )
                )

        with t.subTest('varies between calls'):
            t.assertNotEqual(
                {new_task_id() for _ in range(20)},
                {new_task_id()},
            )


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
        t.source = t.Path.return_value
        t.journal_dir = t.source.__truediv__.return_value
        t.journal_dir.__truediv__.return_value = t.file
        t.handle = t.file.open.return_value.__enter__.return_value
        t.handle.read.return_value = ''

        t.journal = Journal(sentinel.source_dir)

    def test_path(t) -> None:
        with t.subTest('the log sits in the journal directory of the source'):
            t.source.__truediv__.assert_called_once_with(JOURNAL_DIRNAME)
            t.journal_dir.__truediv__.assert_called_once_with(JOURNAL_FILENAME)

        with t.subTest('and is what the journal reads and writes'):
            t.assertEqual(t.journal.path, t.file)

    def test_read(t) -> None:
        with t.subTest('a journal that is not there reads as empty'):
            t.file.exists.return_value = False

            t.assertEqual(t.journal.read(), [])
            t.file.read_text.assert_not_called()

        with t.subTest('every line is one event, in order'):
            t.file.exists.return_value = True
            t.file.read_text.return_value = '{"seq": 1}\n\n{"seq": 2}\n'

            t.assertEqual(t.journal.read(), [{'seq': 1}, {'seq': 2}])

    def test_append(t) -> None:
        event = t.journal.append(
            'TaskAdded',
            'task/zz01ab',
            {'delta': {}},
            actor='agent',
            source_file='a-list.md',
        )

        with t.subTest('the journal directory is made before the write'):
            t.file.parent.mkdir.assert_called_once_with(
                parents=True,
                exist_ok=True,
            )

        with t.subTest('the envelope carries the event and its metadata'):
            t.assertEqual(
                event,
                {
                    'seq': 1,
                    'event_id': 'ffff-1',
                    'stream_id': 'task/zz01ab',
                    'stream_seq': 1,
                    'type': 'TaskAdded',
                    'schema_version': SCHEMA_VERSION,
                    'occurred_at': STAMP,
                    'recorded_at': STAMP,
                    'prev_hash': None,
                    'hash': None,
                    'metadata': {
                        'actor': 'agent',
                        'source_file': 'a-list.md',
                    },
                    'payload': {'delta': {}},
                },
            )

        with t.subTest('which is written as one JSON line'):
            t.handle.write.assert_called_once_with(json.dumps(event) + '\n')

        with t.subTest('the write is flushed to the disk it claims to be on'):
            t.fsync.assert_called_once_with(t.handle.fileno.return_value)

        with t.subTest('under an exclusive lock, released at the end'):
            taken, released = t.flock.call_args_list
            t.assertEqual(taken.args[1], LOCK_EX)
            t.assertEqual(released.args[1], LOCK_UN)

        with t.subTest('the two counters count over different populations'):
            t.handle.read.return_value = (
                '{"stream_id": "task/aa"}\n{"stream_id": "task/bb"}\n'
            )

            event = t.journal.append(
                'TaskUpdated',
                'task/aa',
                {},
                actor='agent',
                source_file='a-list.md',
            )

            t.assertEqual(event['seq'], 3)
            t.assertEqual(event['stream_seq'], 2)

        with t.subTest('a given time is when the change happened'):
            t.handle.read.return_value = ''

            event = t.journal.append(
                'TaskAdded',
                'task/zz01ab',
                {},
                actor='agent',
                source_file='a-list.md',
                occurred_at='2026-08-05T09:00:00+00:00',
            )

            t.assertEqual(event['occurred_at'], '2026-08-05T09:00:00+00:00')
            t.assertEqual(event['recorded_at'], STAMP)
