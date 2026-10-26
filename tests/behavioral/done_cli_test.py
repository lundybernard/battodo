"""Round-trip test for `done`, with and without a completion date.

`done --scratch` closes a task without completing it.

The fixture lists are copied to a temporary directory first: `done`
writes, and the committed fixtures are read-only inputs to the `view`
and `show` goldens.

The clock is pinned, so the day an undated completion falls on is a
fact the test can state. The targets are top-level tasks that do not
repeat: rescheduling reads the completion date too, and that is a
behaviour of its own.
"""

from datetime import datetime
from pathlib import Path
from shutil import copy, copytree
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from battodo.journal import Journal
from tests.environment import TZ

from .cli_runner import run_cli

FIXTURES = Path(__file__).parent / 'data' / 'todo'
# A document beside the lists that shows the list format in a fenced
# example.
GUIDE = Path(__file__).parent / 'data' / 'format-guide.md'
FROZEN = datetime(2026, 8, 5, 10, 30, tzinfo=TZ)
SOURCE_VAR = 'BATTODO_VIEW_SOURCE_DIR'
# The day the work finished, earlier than the day it is logged.
BACKDATE = '2026-07-20'


class DoneCommandTests(TestCase):
    """Round-trip tests for the `done` command."""

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

    def read(t, name: str) -> str:
        return (t.source / name).read_text(encoding='utf-8')

    def test_done_on_a_given_date(t) -> None:
        entry = f'{BACKDATE} | work | DONE | Overdue task'

        logged = t.run_ok('done', 'Overdue task', '--date', BACKDATE)

        with t.subTest('the entry carries the date the user gave'):
            t.assertIn(entry, logged)

        with t.subTest('and the log records it under that date'):
            t.assertIn(entry, t.read('completed.md'))

        with t.subTest('and the journal records it as the completion day'):
            event = Journal(t.source).events[-1]
            t.assertEqual(event['payload']['completed_on'], BACKDATE)

    def test_done_defaults_to_the_clock(t) -> None:
        logged = t.run_ok('done', 'Due today task')

        t.assertIn(
            f'{FROZEN.date().isoformat()} | work | DONE | Due today task',
            logged,
        )

    def test_done_fenced_example(t) -> None:
        copy(GUIDE, t.source)
        before = t.read('format-guide.md')

        out, err, code = run_cli(['done', 'fenced example task'], t.env)

        with t.subTest('a fenced example of the list format is no task'):
            t.assertEqual(err, "no open task matches 'fenced example task'\n")
            t.assertEqual(code, 1)

        with t.subTest('stdout stays empty'):
            t.assertEqual(out, '')

        with t.subTest('and the document stays as it was'):
            t.assertEqual(t.read('format-guide.md'), before)

    def test_done_on_an_unreadable_date(t) -> None:
        """A rejected date reports on stderr and writes nothing."""
        before = (t.read('work.md'), t.read('completed.md'))

        out, err, code = run_cli(
            ['done', 'Overdue task', '--date', 'yesterday'],
            t.env,
        )

        with t.subTest('the message names the value it could not read'):
            t.assertIn('yesterday', err)

        with t.subTest('stdout stays parseable'):
            t.assertEqual(out, '')

        with t.subTest('the exit code is non-zero'):
            t.assertEqual(code, 1)

        with t.subTest('and the run wrote nothing'):
            t.assertEqual((t.read('work.md'), t.read('completed.md')), before)

    def test_done_with_attributes(t) -> None:
        entry = (
            '2026-08-05 | work | DONE | Overdue task [P:4] [LOE:2] '
            '[DUE:2026-08-01] [attrs:{"confirmation": "A1B2C3", '
            '"place": "Main St, Suite 4", "note": "Renewed online"}]'
        )

        logged = t.run_ok(
            'done',
            'Overdue task',
            '--attrs',
            'confirmation=A1B2C3, place=Main St, Suite 4',
            '--note',
            'Renewed online',
        )

        with t.subTest('the journal records the attributes'):
            event = Journal(t.source).events[-1]
            t.assertEqual(
                event['payload']['attrs'],
                {
                    'confirmation': 'A1B2C3',
                    'place': 'Main St, Suite 4',
                    'note': 'Renewed online',
                },
            )

        with t.subTest('the entry carries them after its fields'):
            t.assertIn(entry, logged)

        with t.subTest('and the log records them on its line'):
            t.assertIn(f'{entry}\n', t.read('completed.md'))

    def test_done_scratch(t) -> None:
        entry = (
            f'{BACKDATE} | work | SCRATCHED | Overdue task [P:4] [LOE:2] '
            '[DUE:2026-08-01] [attrs:{"note": "Not needed"}]'
        )

        logged = t.run_ok(
            'done',
            'Overdue task',
            '--scratch',
            '--date',
            BACKDATE,
            '--note',
            'Not needed',
        )

        with t.subTest('the entry logs the task as SCRATCHED'):
            t.assertIn(entry, logged)

        with t.subTest('and the log records it'):
            t.assertIn(f'{entry}\n', t.read('completed.md'))

        with t.subTest('and the journal records its reason and its day'):
            event = Journal(t.source).events[-1]
            payload = event['payload']
            t.assertEqual(
                (event['type'], payload['attrs'], payload['completed_on']),
                ('TaskScratched', {'note': 'Not needed'}, BACKDATE),
            )

        with t.subTest('and the task leaves its list'):
            t.assertNotIn('Overdue task', t.read('work.md'))

    def test_done_with_refused_attributes(t) -> None:
        """A refused attribute reports on stderr and writes nothing."""
        cases = {
            'a key outside the grammar': (
                ['Overdue task', '--attrs', 'Place=Main St'],
                "attribute key must be a lowercase identifier, not 'Place'\n",
            ),
            'a checklist item takes no attributes': (
                ['Open checklist item', '--note', 'Renewed online'],
                'a checklist item takes no attributes\n',
            ),
            'a line break after a comma': (
                ['Overdue task', '--attrs', 'place=Main St,\ncost=45.00'],
                (
                    "attribute 'place' must hold no line break, "
                    "not 'Main St,\\ncost=45.00'\n"
                ),
            ),
        }
        before = (t.read('work.md'), t.read('completed.md'))

        for name, (args, message) in cases.items():
            with t.subTest(name):
                ret = run_cli(['done', *args], t.env)

                t.assertEqual(ret, ('', message, 1))
                t.assertEqual(
                    (t.read('work.md'), t.read('completed.md')),
                    before,
                )
                t.assertEqual(Journal(t.source).events, [])
