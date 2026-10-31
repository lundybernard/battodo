"""Round-trip test for the level of effort.

The fixture lists are copied to a temporary directory first: `add`
writes, and the committed fixtures are read-only inputs to the `view`
and `show` goldens.

`--loe` takes any whole number of 1 or more. A refusal names the bound,
writes nothing, and journals no event.
"""

from datetime import datetime
from json import loads
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
TITLE = 'Rebuild the deck'


class LevelOfEffortCommandTests(TestCase):
    """Round-trip tests for the `--loe` option."""

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

    def test_loe(t) -> None:
        """A whole number above 8 is written, and reads back as given."""
        # Two cycles: `add` writes the value, and `show` reads it back.
        echoed, err, code = run_cli(
            ['add', 'work', TITLE, '--loe', '13'], t.env
        )

        t.assertEqual((err, code), ('', 0))
        t.assertIn(f'- [ ] {TITLE} [LOE:13] [ADDED:2026-08-05] [ID:', echoed)

        shown, err, code = run_cli(['show', TITLE, '--format', 'json'], t.env)

        t.assertEqual((err, code), ('', 0))
        t.assertEqual(loads(shown)['loe'], 13)

    def test_loe_refused(t) -> None:
        """A refused level of effort reports on stderr and writes nothing."""
        cases = {
            'zero, under the bound': (
                '0',
                "LOE must be a whole number of 1 or more, not '0'\n",
            ),
            'a number that is not whole': (
                '2.5',
                "LOE must be a whole number of 1 or more, not '2.5'\n",
            ),
        }
        original = (t.source / 'work.md').read_text(encoding='utf-8')

        for name, (loe, message) in cases.items():
            with t.subTest(name):
                ret = run_cli(['add', 'work', TITLE, '--loe', loe], t.env)

                t.assertEqual(ret, ('', message, 1))
                t.assertEqual(
                    (t.source / 'work.md').read_text(encoding='utf-8'),
                    original,
                )
                t.assertEqual(Journal(t.source).events, [])
