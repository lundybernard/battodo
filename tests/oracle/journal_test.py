"""Characterization tests for the read path in `battodo.journal`.

Temporary scaffolding for the conversion to a property chain. The suite
pins what `read` answers and what `append` counts from the same file,
then asserts the property chain answers the same. It is deleted with
the read method it pins.
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from battodo.journal import Journal

# The two events the pinned file holds. Their stream ids differ, so the
# per-stream counter and the file-wide counter cannot agree by accident.
EVENTS = [
    {'seq': 1, 'stream_id': 'task/aa01bc', 'type': 'TaskAdded'},
    {'seq': 2, 'stream_id': 'task/dd02ef', 'type': 'TaskUpdated'},
]
# Every shape the read path branches on: an event line, a blank line
# between events, and a blank line at the end.
LOG = '{}\n\n{}\n\n'.format(*(json.dumps(event) for event in EVENTS))


class JournalTests(TestCase):
    """Characterization tests for the journal read path, old and new."""

    maxDiff = None

    def setUp(t) -> None:
        t.tmp = TemporaryDirectory()
        t.addCleanup(t.tmp.cleanup)
        t.dir = Path(t.tmp.name)
        t.journal = Journal(t.dir)

    def fill(t) -> None:
        """Write the pinned file under a journal that has none."""
        t.journal.path.parent.mkdir(parents=True)
        t.journal.path.write_text(LOG)

    def test_path(t) -> None:
        ret = t.journal.path
        t.assertEqual(ret, t.dir / '.journal' / 'log.jsonl')

    def test_read(t) -> None:
        with t.subTest('a journal that is not there reads as empty'):
            ret = t.journal.read()
            t.assertEqual(ret, [])

        with t.subTest('the property chain derives the same from no file'):
            read_events = t.journal.read()
            text = t.journal.text
            events = t.journal.events

            t.assertEqual(text, '')
            t.assertEqual(events, read_events)

        with t.subTest('every non-blank line is one event, in order'):
            t.fill()
            ret = t.journal.read()
            t.assertEqual(ret, EVENTS)

        with t.subTest('the property chain derives the same from the file'):
            fresh = Journal(t.dir)

            read_events = t.journal.read()
            text = fresh.text
            events = fresh.events

            t.assertEqual(text, LOG)
            t.assertEqual(events, read_events)

    def test_append(t) -> None:
        with t.subTest('the first event of a journal that has none'):
            event = t.journal.append(
                'TaskAdded',
                'task/aa01bc',
                {},
                actor='agent',
                source_file='a-list.md',
            )

            t.assertEqual(event['seq'], 1)
            t.assertEqual(event['stream_seq'], 1)

        with t.subTest('the counters read the file the read path reads'):
            t.journal.path.write_text(LOG)

            event = t.journal.append(
                'TaskUpdated',
                'task/aa01bc',
                {},
                actor='agent',
                source_file='a-list.md',
            )

            t.assertEqual(event['seq'], 3)
            t.assertEqual(event['stream_seq'], 2)

        with t.subTest('the text before the write is kept, byte for byte'):
            ret = t.journal.path.read_text()
            t.assertEqual(ret, LOG + json.dumps(event) + '\n')

        with t.subTest('and the property chain answers as the read path'):
            read_events = t.journal.read()
            text = t.journal.text
            events = t.journal.events

            t.assertEqual(text, t.journal.path.read_text())
            t.assertEqual(events, read_events)
