"""Golden tests for the rendered output of the `show` command.

The entry point runs against the fixture lists in `data/todo/` and its
stdout is compared, byte for byte, with a committed file in
`data/golden/`. Nothing below the entry point is imported.

`Legacy priority task` is the fixture the goldens read: it carries a
legacy-scale priority, an LOE, no `[ID:]`, and three children covering
an open checklist item, an open subtask, and a completed one.

The clock is pinned because the rank depends on it.
"""

from datetime import datetime
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from battodo.cli import TZ

from .cli_runner import run_cli

DATA = Path(__file__).parent / 'data'
TODO_DIR = DATA / 'todo'
GOLDEN_DIR = DATA / 'golden'

# The instant every fixture date is relative to.
FROZEN = datetime(2026, 8, 5, 10, 30, tzinfo=TZ)
# The environment outranks any config file in the checkout.
SOURCE_VAR = 'BATTODO_VIEW_SOURCE_DIR'
SELECTOR = 'Legacy priority'


def golden(name: str) -> str:
    """Return the committed output named `name`."""
    return (GOLDEN_DIR / name).read_text(encoding='utf-8')


class ShowCommandTests(TestCase):
    maxDiff = None

    def setUp(t) -> None:
        patcher = patch('battodo.cli.datetime', autospec=True)
        t.datetime = patcher.start()
        t.addCleanup(patcher.stop)
        t.datetime.now.return_value = FROZEN
        t.env = {SOURCE_VAR: str(TODO_DIR)}

    def render(t, *args: str) -> str:
        """Run `show` with `args` and return what it wrote to stdout."""
        out, err, code = run_cli(['show', *args], t.env)
        # A failed run reports on stderr and exits non-zero. Check that
        # before diffing stdout.
        t.assertEqual(err, '')
        t.assertEqual(code, 0)
        return out

    def test_show(t) -> None:
        cases = {
            'the human form is the default': ((), 'show.txt'),
            'and a document for a machine to read': (
                ('--format', 'json'),
                'show_json.json',
            ),
        }
        for name, (args, recorded) in cases.items():
            with t.subTest(name):
                t.assertEqual(t.render(SELECTOR, *args), golden(recorded))

    def test_show_unknown_item(t) -> None:
        """An unmatched selector is an error a consumer can branch on."""
        out, err, code = run_cli(['show', 'no such task'], t.env)

        with t.subTest('the message goes to stderr'):
            t.assertIn('no open task matches', err)

        with t.subTest('stdout stays parseable'):
            t.assertEqual(out, '')

        with t.subTest('the exit code is non-zero'):
            t.assertEqual(code, 1)
