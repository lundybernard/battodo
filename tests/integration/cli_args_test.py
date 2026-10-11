"""Contract test for the seam between the parser and the configuration.

Parsed CLI arguments must resolve through the real `Configuration`.
The contract only exists when the real parser and the real
`get_config` meet, so both are real here; the config file is the one
dependency stood in for.
"""

from contextlib import redirect_stdout
from datetime import datetime
from io import StringIO
from os import environ
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from batconf import TomlSource
from batconf.types import SourceInterfaceP

from battodo.cli import DEFAULT_PERIOD, TZ, argparser, get_config
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
    """Parsed CLI arguments must resolve through the real Configuration.

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
        with t.subTest('an option reaches the command'):
            conf = t.resolve(['view', '--format', 'json'])
            t.assertEqual(conf.format, 'json')

        with t.subTest('a flag reaches the command'):
            conf = t.resolve(['view', '--all'])
            t.assertTrue(conf.show_all)

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

        with t.subTest('both add positionals reach the command'):
            conf = t.resolve(['add', 'chores', 'Water it'])
            t.assertEqual(conf.list, 'chores')
            t.assertEqual(conf.title, 'Water it')

        with t.subTest('every add field reaches the command'):
            conf = t.resolve(
                [
                    'add',
                    'chores',
                    'X',
                    '-p',
                    '4',
                    '--loe',
                    '2',
                    '--due',
                    '2026-09-01',
                    '--repeat',
                    '15d',
                    '--tags',
                    'yard,summer',
                ]
            )

            t.assertEqual(conf.priority, '4')
            t.assertEqual(conf.loe, '2')
            t.assertEqual(conf.due, '2026-09-01')
            t.assertEqual(conf.repeat, '15d')
            t.assertEqual(conf.tags, 'yard,summer')

        with t.subTest('an omitted add field is absent, not empty'):
            conf = t.resolve(['add', 'chores', 'X'])
            t.assertIsNone(getattr(conf, 'due', None))

        with t.subTest('an optional positional reaches the command'):
            conf = t.resolve(['completed', 'month'])
            t.assertEqual(conf.period, 'month')

        with t.subTest('and an omitted one falls back to the default'):
            conf = t.resolve(['completed'])
            t.assertEqual(conf.period, DEFAULT_PERIOD)


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
