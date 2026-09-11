"""Contract tests for the event journal, against a real file.

The journal is written and read back from a temporary directory. This
layer asserts state; interaction checks stay in the isolation tests
beside the code.
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from battodo.journal import SCHEMA_VERSION, Journal

SRC = 'battodo.journal'


class JournalTests(TestCase):
    """Contract tests for battodo.journal.Journal."""

    def setUp(t) -> None:
        t.tmp = TemporaryDirectory()
        t.addCleanup(t.tmp.cleanup)
        t.dir = Path(t.tmp.name)
        t.journal = Journal(t.dir)

    def append(t, **kwargs):
        params = {
            'event_type': 'TaskUpdated',
            'stream_id': 'task/abc123',
            'payload': {'delta': {'P': [1, 2]}},
            'actor': 'agent',
            'source_file': 'a-list.md',
        }
        params.update(kwargs)
        return t.journal.append(**params)

    def test_path(t) -> None:
        ret = t.journal.path
        t.assertEqual(ret, t.dir / '.journal' / 'log.jsonl')

    def test_append(t) -> None:
        with t.subTest('creates the journal directory and file'):
            event = t.append()
            t.assertTrue(t.journal.path.exists())

        with t.subTest('envelope shape'):
            t.assertEqual(event['seq'], 1)
            t.assertEqual(event['stream_id'], 'task/abc123')
            t.assertEqual(event['stream_seq'], 1)
            t.assertEqual(event['type'], 'TaskUpdated')
            t.assertEqual(event['schema_version'], SCHEMA_VERSION)
            t.assertEqual(
                event['metadata'],
                {'actor': 'agent', 'source_file': 'a-list.md'},
            )
            t.assertEqual(event['payload'], {'delta': {'P': [1, 2]}})

        with t.subTest('timestamps are UTC and ISO-8601'):
            t.assertTrue(event['recorded_at'].endswith('+00:00'))
            t.assertEqual(event['occurred_at'], event['recorded_at'])

        with t.subTest('explicit occurred_at is preserved'):
            other = t.append(occurred_at='2020-01-01T00:00:00+00:00')
            t.assertEqual(other['occurred_at'], '2020-01-01T00:00:00+00:00')
            t.assertNotEqual(other['recorded_at'], other['occurred_at'])

        with t.subTest('one json object per line'):
            lines = t.journal.path.read_text().splitlines()
            t.assertEqual(len(lines), 2)
            t.assertEqual(json.loads(lines[0])['seq'], 1)

        with t.subTest('seq follows line number'):
            third = t.append()
            t.assertEqual(third['seq'], 3)

        with t.subTest('stream_seq counts within one stream'):
            other = t.append(stream_id='task/other')
            same = t.append()

            t.assertEqual(other['stream_seq'], 1)
            t.assertEqual(same['stream_seq'], 4)

        with t.subTest('a source directory that does not exist yet'):
            # More than one level can be missing, so the journal digs
            # the whole way down rather than only the last directory.
            nested = Journal(t.dir / 'new' / 'nested')

            written = nested.append(
                event_type='TaskAdded',
                stream_id='task/abc123',
                payload={},
                actor='agent',
                source_file='a-list.md',
            )

            t.assertEqual(nested.events, [written])

        with (
            t.subTest('the event id comes from the uuid source'),
            patch(f'{SRC}.uuid4', autospec=True, return_value='fixed-uuid'),
        ):
            # A journal of its own: the counters above are absolute, so
            # a sixth event on the shared one would move them.
            identified = Journal(t.dir / 'ids').append(
                event_type='TaskAdded',
                stream_id='task/abc123',
                payload={},
                actor='agent',
                source_file='a-list.md',
            )

            t.assertEqual(identified['event_id'], 'fixed-uuid')

    def test_text(t) -> None:
        with t.subTest('a journal that is not there is empty text'):
            ret = t.journal.text
            t.assertEqual(ret, '')

        with t.subTest('otherwise the file, byte for byte'):
            t.append()
            ret = t.journal.text
            t.assertEqual(ret, t.journal.path.read_text())

    def test_events(t) -> None:
        with t.subTest('a journal that is not there holds no events'):
            ret = t.journal.events
            t.assertEqual(ret, [])

        with t.subTest('appended events come back in order'):
            t.append()
            t.append(event_type='TaskCompleted')

            ret = t.journal.events

            t.assertEqual(
                [event['type'] for event in ret],
                ['TaskUpdated', 'TaskCompleted'],
            )

        with t.subTest('a blank line is not an event'):
            with t.journal.path.open('a') as handle:
                handle.write('\n')

            ret = Journal(t.dir).events

            t.assertEqual(len(ret), 2)

        with t.subTest('a write from elsewhere does not reach a read object'):
            Journal(t.dir).append(
                event_type='TaskAdded',
                stream_id='task/abc123',
                payload={},
                actor='agent',
                source_file='a-list.md',
            )

            ret = t.journal.events

            t.assertEqual(len(ret), 2)

        with t.subTest('an entry carrying the retired hash fields reads'):
            legacy = {'type': 'TaskAdded', 'prev_hash': None, 'hash': None}
            with t.journal.path.open('a') as handle:
                handle.write(json.dumps(legacy) + '\n')

            ret = Journal(t.dir).events

            t.assertEqual(ret[-1], legacy)
