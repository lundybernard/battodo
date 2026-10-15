"""Characterization tests for `Journal.append`.

Temporary scaffolding for the split of `append` into its steps (#63).
The suite pins the file text and the events that a run of appends
writes before the split, and referees the split against them. It is
deleted when the split lands.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from battodo.journal import Journal

SRC = 'battodo.journal'
# The instant the patched clock reports, and an earlier one an append
# names as the time of its change.
STAMP = '2026-08-05T17:30:00+00:00'
EARLIER = '2026-08-05T09:00:00+00:00'
# The file text after the three appends of the test, byte for byte.
GOLDEN = """\
{"seq": 1, "event_id": "ffff-1", "stream_id": "task/aa", "stream_seq": 1, "type": "TaskAdded", "schema_version": 1, "occurred_at": "2026-08-05T17:30:00+00:00", "recorded_at": "2026-08-05T17:30:00+00:00", "metadata": {"actor": "agent", "source_file": "a-list.md"}, "payload": {"delta": {"P": [null, 2]}}}
{"seq": 2, "event_id": "ffff-2", "stream_id": "task/bb", "stream_seq": 1, "type": "TaskAdded", "schema_version": 1, "occurred_at": "2026-08-05T09:00:00+00:00", "recorded_at": "2026-08-05T17:30:00+00:00", "metadata": {"actor": "another-actor", "source_file": "another-list.md"}, "payload": {}}
{"seq": 3, "event_id": "ffff-3", "stream_id": "task/aa", "stream_seq": 2, "type": "TaskCompleted", "schema_version": 1, "occurred_at": "2026-08-05T17:30:00+00:00", "recorded_at": "2026-08-05T17:30:00+00:00", "metadata": {"actor": "agent", "source_file": "a-list.md"}, "payload": {"done": true}}
"""


class JournalAppendTests(TestCase):
    """Characterization tests for battodo.journal.Journal.append."""

    def setUp(t) -> None:
        tmp = TemporaryDirectory()
        t.addCleanup(tmp.cleanup)
        t.journal = Journal(Path(tmp.name) / 'another-source')

        patcher = patch(f'{SRC}.uuid4', autospec=True)
        uuid4 = patcher.start()
        t.addCleanup(patcher.stop)
        uuid4.side_effect = ['ffff-1', 'ffff-2', 'ffff-3']

        patcher = patch(f'{SRC}._utc_now', autospec=True)
        utc_now = patcher.start()
        t.addCleanup(patcher.stop)
        utc_now.return_value = STAMP

    def test_append(t) -> None:
        written = [
            t.journal.append(
                'TaskAdded',
                'task/aa',
                {'delta': {'P': [None, 2]}},
                actor='agent',
                source_file='a-list.md',
            ),
            t.journal.append(
                'TaskAdded',
                'task/bb',
                {},
                actor='another-actor',
                source_file='another-list.md',
                occurred_at=EARLIER,
            ),
            t.journal.append(
                'TaskCompleted',
                'task/aa',
                {'done': True},
                actor='agent',
                source_file='a-list.md',
            ),
        ]

        text = t.journal.path.read_text(encoding='utf-8')
        events = t.journal.events

        t.assertEqual(text, GOLDEN)
        # Each append returns the event it wrote.
        t.assertEqual(written, events)
