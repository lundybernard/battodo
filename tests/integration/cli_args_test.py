"""Contract tests for the seam between the parser and the configuration.

A config option resolves through the real `Configuration`. A command
input passes beside it, so no environment variable and no config file
reaches it. The contract only exists when the real parser and the real
`get_config` meet, so both are real here. The config file is stood in
for, unless a test writes one.
"""

from contextlib import redirect_stdout
from datetime import datetime
from io import StringIO
from json import loads
from os import environ
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import MagicMock, patch

from batconf import TomlSource
from batconf.types import SourceInterfaceP

from battodo.cli import TZ, argparser, get_config
from battodo.journal import Journal
from battodo.view import TOP_N

SOURCE_VAR = 'BATTODO_VIEW_SOURCE_DIR'
FROZEN = datetime(2026, 8, 5, 10, 30, tzinfo=TZ)
# A day other than the clock's, so a value that leaks in shows.
STRAY_DATE = '2020-01-01'
# No category window shuts this list: the display order does not name
# it.
YARD = (
    '# Yard\n'
    '\n'
    '## Open\n'
    '\n'
    '- [ ] Rake leaves [P:3] [ID:rk01lv]\n'
    '- [ ] Sweep deck [P:2]\n'
)


class NullFileSource:
    """Stands in for the config file; the filesystem is out of scope."""

    def get(self, key: str, path: str | None = None) -> None:
        return None


class CliArgsResolutionTests(TestCase):
    """Parsed config options must resolve through the real Configuration.

    Cross-module by necessity: the contract under test is the seam
    between argparse dests and batconf's dotted config paths, which only
    exists when the real parser and the real get_config meet.
    """

    def setUp(t):
        # The environment source outranks the schema defaults: an
        # ambient BATTODO_* var would answer before them.
        patcher = patch.dict('os.environ', clear=True)
        patcher.start()
        t.addCleanup(patcher.stop)

    def resolve(t, argv):
        args = argparser().parse_args(argv)
        return get_config(cli_args=args, config_file=NullFileSource())

    def test_cli_args(t):
        with t.subTest('a format reaches the command'):
            conf = t.resolve(['view', '--format', 'json'])
            t.assertEqual(conf.format, 'json')

        with (
            t.subTest('and the environment answers when no flag is given'),
            patch.dict(environ, {'BATTODO_FORMAT': 'json'}),
        ):
            conf = t.resolve(['view'])
            t.assertEqual(conf.format, 'json')

        with t.subTest('and the schema answers when no source does'):
            conf = t.resolve(['view'])
            t.assertEqual(conf.format, 'text')

        with t.subTest('the log level reaches the command'):
            conf = t.resolve(['--debug', 'view'])
            t.assertEqual(conf.loglevel, 'DEBUG')

        with t.subTest('and the schema answers when no flag is given'):
            conf = t.resolve(['view'])
            t.assertEqual(conf.loglevel, 'ERROR')

        with t.subTest('a count reaches the command as a string'):
            conf = t.resolve(['view', '--top', '2'])
            t.assertEqual(conf.view.top, '2')

        with t.subTest('and the schema answers when no source does'):
            conf = t.resolve(['view'])
            t.assertEqual(conf.view.top, str(TOP_N))


class CommandInputTests(TestCase):
    """Contract tests for the command inputs of battodo.cli.Commands.

    A command input passes beside the configuration, so no environment
    variable and no config file reaches it. Each run reads and writes a
    real list in a temporary source directory.
    """

    maxDiff = None

    def setUp(t):
        tmp = TemporaryDirectory()
        t.addCleanup(tmp.cleanup)
        t.root = Path(tmp.name)
        t.source = t.root / 'todo'
        t.source.mkdir()
        (t.source / 'yard.md').write_text(YARD, encoding='utf-8')

        patcher = patch('battodo.cli.datetime', autospec=True)
        t.datetime = patcher.start()
        t.addCleanup(patcher.stop)
        t.datetime.now.return_value = FROZEN

    def run_command(
        t,
        argv: list[str],
        env: dict[str, str],
        config_file: SourceInterfaceP | None = None,
    ) -> str:
        """Run one command with `env` as the whole environment.

        The configuration reads its sources lazily, so the command runs
        inside the patched environment. Returns what the command
        printed.
        """
        args = argparser().parse_args(argv)
        out = StringIO()
        with (
            patch.dict(environ, {SOURCE_VAR: str(t.source)} | env, clear=True),
            redirect_stdout(out),
        ):
            conf = get_config(
                cli_args=args,
                config_file=config_file or NullFileSource(),
            )
            args.func(conf, args)
        return out.getvalue()

    @patch('battodo.mutate.new_task_id', autospec=True)
    def test_add(t, new_task_id: MagicMock):
        new_task_id.return_value = 'nw01id'
        listed = t.source / 'yard.md'

        with t.subTest('BATTODO_PARENT does not reach add'):
            ret = t.run_command(
                ['add', 'yard', 'Water it'],
                {'BATTODO_PARENT': 'rk01lv'},
            )

            t.assertEqual(
                ret,
                f'- [ ] Water it [ADDED:2026-08-05] [ID:nw01id]\n{listed}\n',
            )

        with t.subTest('BATTODO_LOE does not reach add'):
            ret = t.run_command(
                ['add', 'yard', 'Mow lawn'],
                {'BATTODO_LOE': '8'},
            )

            t.assertEqual(
                ret,
                f'- [ ] Mow lawn [ADDED:2026-08-05] [ID:nw01id]\n{listed}\n',
            )

        with t.subTest('--attrs and --note reach the event'):
            t.run_command(
                ['add', 'yard', 'Trim hedge', '--attrs', 'cost=12.50'],
                {},
            )

            event = Journal(t.source).events[-1]
            t.assertEqual(event['payload']['attrs'], {'cost': '12.50'})

        with t.subTest('and the event of a subtask'):
            t.run_command(
                [
                    'add',
                    'yard',
                    'Bag them',
                    '--parent',
                    'rk01lv',
                    '--note',
                    'Wet',
                ],
                {},
            )

            event = Journal(t.source).events[-1]
            t.assertEqual(event['payload']['attrs'], {'note': 'Wet'})

    def test_view(t):
        with t.subTest('BATTODO_SHOW_ALL does not reach view'):
            ret = t.run_command(
                ['view', '--format', 'json'],
                {'BATTODO_SHOW_ALL': 'false', 'BATTODO_VIEW_TOP': '1'},
            )

            # One of the two open tasks shows. The other is abridged.
            t.assertEqual(loads(ret)['categories'][0]['hidden'], 1)

    def test_done(t):
        with t.subTest('BATTODO_DATE does not reach done'):
            ret = t.run_command(
                ['done', 'rk01lv'],
                {'BATTODO_DATE': STRAY_DATE},
            )

            t.assertEqual(
                ret, '2026-08-05 | yard | DONE | Rake leaves [P:3]\n'
            )

        with t.subTest('a date in the config file does not reach done'):
            config_file = t.root / 'battodo.toml'
            config_file.write_text(
                f'[test.battodo]\ndate = "{STRAY_DATE}"\n',
                encoding='utf-8',
            )

            ret = t.run_command(
                ['done', 'Sweep deck'],
                {},
                TomlSource(str(config_file), config_env='test'),
            )

            t.assertEqual(ret, '2026-08-05 | yard | DONE | Sweep deck [P:2]\n')

        with t.subTest('--scratch, --attrs and --note reach the event'):
            # The subtests above closed both tasks.
            (t.source / 'yard.md').write_text(YARD, encoding='utf-8')

            t.run_command(
                [
                    'done',
                    'rk01lv',
                    '--scratch',
                    '--attrs',
                    'cost=0',
                    '--note',
                    'Too wet',
                ],
                {},
            )

            event = Journal(t.source).events[-1]
            t.assertEqual(
                (event['type'], event['payload']['attrs']),
                ('TaskScratched', {'cost': '0', 'note': 'Too wet'}),
            )

    def test_note(t):
        with t.subTest('TEXT and --attrs reach the event'):
            t.run_command(
                ['note', 'rk01lv', 'Too wet', '--attrs', 'cost=0'],
                {},
            )

            event = Journal(t.source).events[-1]
            t.assertEqual(
                event['payload']['attrs'],
                {'cost': '0', 'note': 'Too wet'},
            )

        with t.subTest('BATTODO_ATTRS does not reach note'):
            t.run_command(
                ['note', 'rk01lv', 'Still wet'],
                {'BATTODO_ATTRS': 'cost=9'},
            )

            event = Journal(t.source).events[-1]
            t.assertEqual(event['payload']['attrs'], {'note': 'Still wet'})

    def test_history(t):
        t.run_command(['note', 'rk01lv', 'Too wet'], {})

        with t.subTest('the selector and BATTODO_FORMAT reach history'):
            ret = t.run_command(
                ['history', 'rk01lv'],
                {'BATTODO_FORMAT': 'json'},
            )

            history = loads(ret)
            t.assertEqual(history['id'], 'rk01lv')
            t.assertEqual(history['title'], 'Rake leaves')
            t.assertEqual(history['entries'][0]['kind'], 'TaskAnnotated')

    def test_update(t):
        listed = t.source / 'yard.md'

        with t.subTest('BATTODO_TITLE does not reach update'):
            ret = t.run_command(
                ['update', 'rk01lv', '-p', '4'],
                {'BATTODO_TITLE': 'Renamed'},
            )

            t.assertEqual(
                ret,
                f'- [ ] Rake leaves [P:4] [ID:rk01lv]\n{listed}\n',
            )

        with t.subTest('BATTODO_DUE does not reach update'):
            ret = t.run_command(
                ['update', 'rk01lv', '-p', '5'],
                {'BATTODO_DUE': STRAY_DATE},
            )

            t.assertEqual(
                ret,
                f'- [ ] Rake leaves [P:5] [ID:rk01lv]\n{listed}\n',
            )
