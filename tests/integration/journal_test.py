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
        t.assertEqual(t.journal.path, t.dir / '.journal' / 'log.jsonl')

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
            t.assertIsNone(event['prev_hash'])
            t.assertIsNone(event['hash'])
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
            t.assertEqual(t.append()['seq'], 3)

        with t.subTest('stream_seq counts within one stream'):
            t.assertEqual(t.append(stream_id='task/other')['stream_seq'], 1)
            t.assertEqual(t.append()['stream_seq'], 4)

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

            t.assertEqual(nested.read(), [written])

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

    def test_read(t) -> None:
        with t.subTest('missing journal reads empty'):
            t.assertEqual(t.journal.read(), [])

        with t.subTest('round-trips appended events'):
            t.append()
            t.append(event_type='TaskCompleted')
            events = t.journal.read()
            t.assertEqual(
                [e['type'] for e in events], ['TaskUpdated', 'TaskCompleted']
            )

        with t.subTest('blank trailing lines are skipped'):
            with t.journal.path.open('a') as handle:
                handle.write('\n')
            t.assertEqual(len(t.journal.read()), 2)
