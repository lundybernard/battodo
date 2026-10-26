"""Golden tests for the rendered output of the `view` command.

Each test runs the console entry point in process against the fixture
lists in `data/todo/` and compares stdout, byte for byte, with a
committed file in `data/golden/`. Nothing below the entry point is
imported.

The output depends on the clock, the terminal width, and the source
directory, so all three are pinned. The entry point runs in process
because a subprocess's clock cannot be patched.

The fixture lists:

- `work.md`: open window, more items than the abridged view shows.
  Each item pins one rendered behaviour: overdue, due today, a
  clipped long title, open and completed children, a legacy-scale
  priority, a completed item, a future recurrence, a placeholder
  date, and a second heading that is not an open section.
- `chores.md`: shut window; absent from every golden.
- `backlog.md`: parked; the scan steps over it.
- `side-quests.md`: a name outside the category order, so always
  shown. The hyphen renders as a space, and its undated item makes a
  rank with more decimals than the JSON publishes.

`data/format-guide.md` is a document, not a list: it shows the list
format in a fenced example. A test copies it beside the lists.
`data/longer-heading.md` is not a list either: its heading
`## Open-prefixed heading` starts with `## Open` but is longer.
"""

from datetime import datetime
from json import loads
from pathlib import Path
from shutil import copy, copytree
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from tests.environment import TZ

from .cli_runner import run_cli

DATA = Path(__file__).parent / 'data'
TODO_DIR = DATA / 'todo'
GOLDEN_DIR = DATA / 'golden'
# The config file that sets the schedule of the goldens.
SCHEDULE_FILE = DATA / 'battodo.toml'
# A config file that sets no schedule.
UNSCHEDULED_FILE = DATA / 'unscheduled.toml'
GUIDE_FILE = DATA / 'format-guide.md'
LONGER_HEADING_FILE = DATA / 'longer-heading.md'

# Wednesday mid-morning: the work window is open, the chores window
# is shut. All fixture dates are relative to this instant.
FROZEN = datetime(2026, 8, 5, 10, 30, tzinfo=TZ)
# The layout reads the terminal width from COLUMNS.
WIDTH = '80'
# The environment outranks any config file in the checkout.
SOURCE_VAR = 'BATTODO_VIEW_SOURCE_DIR'
TOP_VAR = 'BATTODO_VIEW_TOP'
ALL_VAR = 'BATTODO_VIEW_ALL'
FORMAT_VAR = 'BATTODO_FORMAT'
LEVEL_VAR = 'BATTODO_LOGLEVEL'
CURVE_VAR = 'BATTODO_VIEW_RANK_DUE_CURVE'
CONFIG_VAR = 'BATTODO_CONFIG_FILE'
ZONE_VAR = 'BATTODO_VIEW_TIME_ZONE'
WINDOWS_VAR = 'BATTODO_VIEW_WINDOWS'
ALWAYS_VAR = 'BATTODO_VIEW_ALWAYS_ACTIVE'


def golden(name: str) -> str:
    """Return the committed output named `name`.

    The goldens hold box-drawing characters, so the encoding is
    explicit, not the host default.
    """
    return (GOLDEN_DIR / name).read_text(encoding='utf-8')


class ViewCommandTests(TestCase):
    """Golden tests for the output of the `view` command."""

    maxDiff = None

    def setUp(t) -> None:
        # Pin the clock: the rendered output depends on it. The instant
        # is fixed, and the configured zone decides its local time.
        patcher = patch('battodo.cli.datetime', autospec=True)
        t.datetime = patcher.start()
        t.addCleanup(patcher.stop)
        t.datetime.now.side_effect = FROZEN.astimezone

    def cli(
        t,
        *args: str,
        env: dict[str, str] | None = None,
    ) -> tuple[str, str, object]:
        """Run `view` with `args`, and `env` over the pinned variables."""
        pinned = {
            'COLUMNS': WIDTH,
            SOURCE_VAR: str(TODO_DIR),
            CONFIG_VAR: str(SCHEDULE_FILE),
        }
        return run_cli(['view', *args], pinned | (env or {}))

    def render(t, *args: str, env: dict[str, str] | None = None) -> str:
        """Run `view` with `args` and return what it wrote to stdout."""
        out, err, code = t.cli(*args, env=env)
        # A misconfigured run reports on stderr and exits non-zero.
        # Check that before diffing stdout.
        t.assertEqual(err, '')
        t.assertEqual(code, 0)
        return out

    def test_view(t) -> None:
        cases = {
            'the human view is the default': ((), 'view.txt'),
            'every open item, not just the top few': (
                ('--all',),
                'view_all.txt',
            ),
            'and a document for a machine to read': (
                ('--format', 'json'),
                'view_json.json',
            ),
            'a chosen count replaces the default five': (
                ('--top', '1'),
                'view_top.txt',
            ),
            'the document is abridged to the same count': (
                ('--top', '1', '--format', 'json'),
                'view_top_json.json',
            ),
            'asking for everything outranks a count': (
                ('--all', '--top', '1'),
                'view_all.txt',
            ),
        }

        for name, (args, recorded) in cases.items():
            with t.subTest(name):
                out = t.render(*args)
                t.assertEqual(out, golden(recorded))

        out, err, code = t.cli('--top', '0')

        with t.subTest('a count below one is a usage error'):
            t.assertIn('argument --top: ', err)
            t.assertIn('must be a whole number of 1 or more', err)

        with t.subTest('which exits non-zero and writes no view'):
            t.assertNotEqual(code, 0)
            t.assertEqual(out, '')

    def test_view_fenced_example(t) -> None:
        tmp = TemporaryDirectory()
        t.addCleanup(tmp.cleanup)
        source = Path(tmp.name) / 'todo'
        copytree(TODO_DIR, source)
        copy(GUIDE_FILE, source)

        out = t.render('--all', env={SOURCE_VAR: str(source)})

        # A fenced example of the list format is not a list.
        t.assertEqual(out, golden('view_all.txt'))

    def test_view_longer_heading(t) -> None:
        tmp = TemporaryDirectory()
        t.addCleanup(tmp.cleanup)
        source = Path(tmp.name)
        copy(LONGER_HEADING_FILE, source)

        out, err, code = t.cli(env={SOURCE_VAR: str(source)})

        with t.subTest('a heading that only starts with Open makes no list'):
            t.assertEqual(
                err,
                'no todo lists (no file with a "## Open" heading) '
                f'in: {source}\n',
            )
            t.assertEqual(code, 1)

        with t.subTest('and the run writes no view'):
            t.assertEqual(out, '')

    def test_view_top_is_configured(t) -> None:
        with t.subTest('the environment sets the count'):
            out = t.render(env={TOP_VAR: '1'})
            t.assertEqual(out, golden('view_top.txt'))

        with t.subTest('the command line outranks the environment'):
            out = t.render('--top', '5', env={TOP_VAR: '1'})
            t.assertEqual(out, golden('view.txt'))

        out, err, code = t.cli(env={TOP_VAR: '0'})

        with t.subTest('a configured count below one is reported'):
            t.assertIn('must be a whole number of 1 or more', err)

        with t.subTest('which exits non-zero and writes no view'):
            t.assertNotEqual(code, 0)
            t.assertEqual(out, '')

    def test_view_all_is_configured(t) -> None:
        with t.subTest('the environment shows every item without the flag'):
            out = t.render(env={ALL_VAR: 'true'})
            t.assertEqual(out, golden('view_all.txt'))

        with t.subTest('a configured false keeps the abridged view'):
            out = t.render(env={ALL_VAR: 'false'})
            t.assertEqual(out, golden('view.txt'))

        with t.subTest('the flag shows every item whatever is configured'):
            out = t.render('--all', env={ALL_VAR: 'false'})
            t.assertEqual(out, golden('view_all.txt'))

        with t.subTest('a value btodo cannot read: reported, exit 1, no view'):
            out, err, code = t.cli(env={ALL_VAR: 'yes'})

            t.assertEqual(
                err,
                "unknown view.all value 'yes'; choose one of false, true\n",
            )
            t.assertEqual(code, 1)
            t.assertEqual(out, '')

    def test_view_format_is_configured(t) -> None:
        with t.subTest('the environment sets the format'):
            out = t.render(env={FORMAT_VAR: 'json'})
            t.assertEqual(out, golden('view_json.json'))

        with t.subTest('the command line outranks the environment'):
            out = t.render('--format', 'text', env={FORMAT_VAR: 'json'})
            t.assertEqual(out, golden('view.txt'))

        out, err, code = t.cli(env={FORMAT_VAR: 'xml'})

        with t.subTest('a configured format btodo cannot write is reported'):
            t.assertEqual(
                err, "unknown format 'xml'; choose one of text, json\n"
            )

        with t.subTest('which exits non-zero and writes no view'):
            t.assertEqual(code, 1)
            t.assertEqual(out, '')

    def test_view_log_level_is_configured(t) -> None:
        out, err, code = t.cli(env={LEVEL_VAR: 'bogus'})

        with t.subTest('a configured level btodo cannot set is reported'):
            t.assertEqual(
                err,
                "unknown log level 'bogus'; choose one of CRITICAL, FATAL, "
                'ERROR, WARN, WARNING, INFO, DEBUG, NOTSET\n',
            )

        with t.subTest('which exits non-zero and writes no view'):
            t.assertEqual(code, 1)
            t.assertEqual(out, '')

    def test_view_due_curve_is_configured(t) -> None:
        with t.subTest('a flat curve leaves a dated task at its priority'):
            out = t.render('--format', 'json', env={CURVE_VAR: '0:1.0'})

            ranks = {
                task['title']: task['rank']
                for category in loads(out)['categories']
                for task in category['tasks']
            }

            t.assertEqual(ranks['Overdue task'], 4.0)

        with t.subTest('a curve btodo cannot read: reported, exit 1, no view'):
            out, err, code = t.cli(env={CURVE_VAR: '-30:0.5, soon:1.0'})

            t.assertEqual(
                err,
                "a rank due curve point must read days:factor: 'soon:1.0'\n",
            )
            t.assertEqual(code, 1)
            t.assertEqual(out, '')

    def test_view_time_zone_is_configured(t) -> None:
        with t.subTest('the zone moves the clock to its own day and hour'):
            # 10:30 in Los Angeles is 02:30 the next day in Tokyo: a
            # Thursday, before the work window opens.
            out = t.render(env={ZONE_VAR: 'Asia/Tokyo'})

            t.assertEqual(
                out.split('\n')[0],
                'Thursday 2026-08-06 02:30 — active: career, events, study',
            )

        with t.subTest('a zone btodo does not know: reported, exit 1'):
            out, err, code = t.cli(env={ZONE_VAR: 'Mars/Olympus'})

            t.assertEqual(
                err,
                "unknown time zone in view.time_zone: 'Mars/Olympus'\n",
            )
            t.assertEqual(code, 1)
            t.assertEqual(out, '')

    def test_view_schedule_is_configured(t) -> None:
        with t.subTest('no schedule: every list, under the day and time'):
            out = t.render(env={CONFIG_VAR: str(UNSCHEDULED_FILE)})

            t.assertEqual(out.split('\n')[0], 'Wednesday 2026-08-05 10:30')
            t.assertIn('── Chores ', out)

        with t.subTest('the environment sets the windows'):
            out = t.render(env={WINDOWS_VAR: 'chores=wed 10-11'})

            t.assertEqual(
                out.split('\n')[0],
                'Wednesday 2026-08-05 10:30 — active: career, chores, events, '
                'study',
            )
            t.assertIn('── Chores ', out)

        with t.subTest('and the names no window shuts'):
            out = t.render(env={ALWAYS_VAR: 'chores'})

            t.assertEqual(
                out.split('\n')[0],
                'Wednesday 2026-08-05 10:30 — active: chores, work',
            )
            t.assertIn('── Chores ', out)

        with t.subTest('windows btodo cannot read: reported, exit 1'):
            out, err, code = t.cli(env={WINDOWS_VAR: 'chores=someday 9-17'})

            t.assertEqual(
                err,
                'a view.windows window must read <days> <start>-<end>: '
                "'someday 9-17'\n",
            )
            t.assertEqual(code, 1)
            t.assertEqual(out, '')
