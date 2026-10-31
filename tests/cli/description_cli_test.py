"""Round-trip test for a task description.

The fixture lists are copied to a temporary directory first: these
commands write, and the committed fixtures are read-only inputs to the
`view` and `show` goldens.

The narrative is one description's life on a repeating task. `add`
sets it, `show` reads it back, a completion keeps it, `update` changes
it and then clears it, and the journal records each step.
"""

from datetime import datetime
from json import loads
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
from typing import Any
from unittest import TestCase
from unittest.mock import patch

from battodo.journal import Journal
from tests.environment import TZ

from .cli_runner import run_cli

FIXTURES = Path(__file__).parent / 'data' / 'todo'
FROZEN = datetime(2026, 8, 5, 10, 30, tzinfo=TZ)
SOURCE_VAR = 'BATTODO_VIEW_SOURCE_DIR'
TITLE = 'A repeating task'
DESCRIPTION = 'A first description line.\nA second description line.'
CHANGED = 'A changed description line.'


class DescriptionCommandTests(TestCase):
    """Round-trip tests for the `--description` option."""

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

    def test_description(t) -> None:
        t.run_ok(
            'add',
            'work',
            TITLE,
            '--repeat',
            '7d',
            '--description',
            DESCRIPTION,
        )

        with t.subTest('the list holds it as description lines'):
            written = (t.source / 'work.md').read_text(encoding='utf-8')
            t.assertIn(
                '\n      A first description line.'
                '\n      A second description line.\n',
                written,
            )

        with t.subTest('show reads it back'):
            added = t.show(TITLE)
            t.assertEqual(added['description'], DESCRIPTION)

        with t.subTest('and shows it as a row'):
            rendered = t.run_ok('show', TITLE)
            t.assertIn(
                '  description  A first description line.\n'
                '               A second description line.\n',
                rendered,
            )

        t.run_ok('done', TITLE)

        with t.subTest('a completion of a repeating task keeps it'):
            rescheduled = t.show(TITLE)
            t.assertEqual(rescheduled['due'], '2026-08-12')
            t.assertEqual(rescheduled['description'], DESCRIPTION)

        t.run_ok('update', TITLE, '--description', CHANGED)

        with t.subTest('update changes it'):
            changed = t.show(TITLE)
            t.assertEqual(changed['description'], CHANGED)

        t.run_ok('update', TITLE, '--description', '')

        with t.subTest('and an empty description clears it'):
            cleared = t.show(TITLE)
            t.assertIsNone(cleared['description'])

        with t.subTest('the journal records every step'):
            added_event, completed, changed_event, cleared_event = (
                event['payload'] for event in Journal(t.source).events
            )
            t.assertEqual(added_event['snapshot']['description'], DESCRIPTION)
            t.assertEqual(completed['snapshot']['description'], DESCRIPTION)
            t.assertEqual(
                changed_event['delta']['description'],
                [DESCRIPTION, CHANGED],
            )
            t.assertEqual(
                cleared_event['delta']['description'],
                [CHANGED, None],
            )

    def test_description_refused(t) -> None:
        """A refused description reports on stderr and writes nothing."""
        cases = {
            'a blank line': ('A line.\n\nAnother line.', "''"),
            'a line that reads as a task': (
                '- [ ] A line.',
                "'- [ ] A line.'",
            ),
            'a line that reads as a heading': ('## A line.', "'## A line.'"),
            'a line that reads as a comment': (
                '<!-- A line. -->',
                "'<!-- A line. -->'",
            ),
            'a carriage return': ('A line.\r', "'A line.\\r'"),
        }
        original = (t.source / 'work.md').read_text(encoding='utf-8')

        for name, (description, named) in cases.items():
            for args in (
                ('add', 'work', TITLE, '--description', description),
                ('update', 'Overdue task', '--description', description),
            ):
                with t.subTest(name, command=args[0]):
                    out, err, code = run_cli(list(args), t.env)

                    t.assertEqual(code, 1)
                    t.assertEqual(out, '')
                    t.assertIn(named, err)
                    t.assertEqual(
                        (t.source / 'work.md').read_text(encoding='utf-8'),
                        original,
                    )

        with t.subTest('a checklist item takes no description'):
            out, err, code = run_cli(
                ['update', 'Open checklist', '--description', CHANGED],
                t.env,
            )

            t.assertEqual(code, 1)
            t.assertIn('is a checklist item', err)
            t.assertEqual(
                (t.source / 'work.md').read_text(encoding='utf-8'),
                original,
            )

        with t.subTest('no refusal reaches the journal'):
            t.assertEqual(Journal(t.source).events, [])
