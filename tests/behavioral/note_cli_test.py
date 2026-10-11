"""Round-trip test for the `note` command.

The fixture lists are copied to a temporary directory first: `note`
writes, and the committed fixtures are read-only inputs to the `view`
and `show` goldens.

The narrative is a note on an open task between its writes. Note an
item that carries no `[ID:]`, find the note on the task's stream, then
note it again by the id the first note stamped.
"""

from datetime import datetime
from json import loads
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
from typing import Any
from unittest import TestCase
from unittest.mock import patch

from battodo.cli import TZ
from battodo.journal import Journal

from .cli_runner import run_cli

FIXTURES = Path(__file__).parent / 'data' / 'todo'
FROZEN = datetime(2026, 8, 5, 10, 30, tzinfo=TZ)
SOURCE_VAR = 'BATTODO_VIEW_SOURCE_DIR'
SELECTOR = 'Legacy priority'


class NoteCommandTests(TestCase):
    """Round-trip tests for the `note` command."""

    maxDiff = None

    def setUp(t) -> None:
        tmp = TemporaryDirectory()
        t.addCleanup(tmp.cleanup)
        t.source = Path(tmp.name) / 'todo'
        copytree(FIXTURES, t.source)
        t.env = {SOURCE_VAR: str(t.source)}

        patcher = patch('battodo.cli.datetime', autospec=True)
        t.datetime = patcher.start()
        t.addCleanup(patcher.stop)
        t.datetime.now.return_value = FROZEN

    def run_ok(t, *args: str) -> str:
        """Run `args`, require it to succeed, and return its stdout."""
        out, err, code = run_cli(list(args), t.env)
        t.assertEqual(err, '')
        t.assertEqual(code, 0)
        return out

    def show(t, selector: str) -> dict[str, Any]:
        return loads(t.run_ok('show', selector, '--format', 'json'))

    def test_note(t) -> None:
        before = t.show(SELECTOR)

        echoed = t.run_ok(
            'note',
            SELECTOR,
            'Waiting on the vendor',
            '--attrs',
            'contact=a value, with a comma',
        )

        after = t.show(SELECTOR)
        task_id = after['id']
        stamp, annotated = Journal(t.source).events

        with t.subTest('the written line and its file are echoed'):
            t.assertIn('- [ ] Legacy priority task', echoed)
            t.assertIn('work.md', echoed)

        with t.subTest('the task is stamped first, on an event of its own'):
            t.assertEqual(stamp['type'], 'TaskUpdated')
            t.assertEqual(stamp['payload']['delta'], {'ID': [None, task_id]})

        with t.subTest('the note goes on the stream of the task'):
            t.assertEqual(annotated['type'], 'TaskAnnotated')
            t.assertEqual(annotated['stream_id'], f'task/{task_id}')
            t.assertEqual(
                annotated['payload']['attrs'],
                {
                    'contact': 'a value, with a comma',
                    'note': 'Waiting on the vendor',
                },
            )

        with t.subTest('the note changes nothing else in the task'):
            t.assertNotIn('delta', annotated['payload'])
            t.assertEqual({**after, 'id': None}, before)

        with t.subTest('a second note by id stamps nothing'):
            t.run_ok('note', task_id, 'Vendor replied')

            events = Journal(t.source).events
            t.assertEqual(len(events), 3)
            t.assertEqual(events[-1]['type'], 'TaskAnnotated')

    def test_note_rejected(t) -> None:
        """A rejected note reports on stderr and writes nothing."""
        cases = {
            'a note with no text and no attributes': ('note', SELECTOR),
            'a checklist item takes no note': (
                'note',
                'Open checklist item',
                'Started',
            ),
            'a done task is out of reach': (
                'note',
                'Completed task',
                'Started',
            ),
            'a note given twice never reaches the file': (
                'note',
                SELECTOR,
                'Waiting',
                '--attrs',
                'note=Waiting',
            ),
        }
        original = (t.source / 'work.md').read_text(encoding='utf-8')

        for name, args in cases.items():
            with t.subTest(name):
                out, err, code = run_cli(list(args), t.env)

                t.assertEqual(code, 1)
                t.assertEqual(out, '')
                t.assertNotEqual(err, '')
                t.assertEqual(
                    (t.source / 'work.md').read_text(encoding='utf-8'),
                    original,
                )
                t.assertEqual(Journal(t.source).events, [])
