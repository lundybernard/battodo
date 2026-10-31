"""Refusal test for the priority.

The fixture lists are copied to a temporary directory first: `add` and
`update` write, and the committed fixtures are read-only inputs to the
`view` and `show` goldens.

`-p` takes a whole number that `int` reads. A superscript digit is not
one, so `add` and `update` refuse it, write nothing, and journal no event.
"""

from datetime import datetime
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from battodo.journal import Journal
from tests.environment import TZ

from .cli_runner import run_cli

FIXTURES = Path(__file__).parent / 'data' / 'todo'
FROZEN = datetime(2026, 8, 5, 10, 30, tzinfo=TZ)
SOURCE_VAR = 'BATTODO_VIEW_SOURCE_DIR'


class PriorityCommandTests(TestCase):
    """Refusal tests for the `-p` option."""

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

    def test_priority_refused(t) -> None:
        """A superscript digit reports on stderr and writes nothing."""
        commands = (
            ('add', 'work', 'Rx refill', '-p', '²'),
            ('update', 'Overdue task', '-p', '²'),
        )
        original = (t.source / 'work.md').read_text(encoding='utf-8')

        for args in commands:
            with t.subTest(command=args[0]):
                ret = run_cli(list(args), t.env)

                t.assertEqual(
                    ret, ('', "P must be a whole number, not '²'\n", 1)
                )
                t.assertEqual(
                    (t.source / 'work.md').read_text(encoding='utf-8'),
                    original,
                )
                t.assertEqual(Journal(t.source).events, [])
