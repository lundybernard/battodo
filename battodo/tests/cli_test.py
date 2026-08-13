from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, call, patch

from ..cli import (
    BATCLI,
    Commands,
    argparse,
    argparser,
    get_config,
    logging,
)

SRC = 'battodo.cli'


class ArgparserTests(TestCase):
    def test_argparser(t):
        p = argparser()

        with t.subTest('view renders for a human by default'):
            args = p.parse_args(['view'])
            t.assertEqual(getattr(args, 'battodo.format'), 'text')

        with t.subTest('view takes a machine-readable format'):
            args = p.parse_args(['view', '--format', 'json'])
            t.assertEqual(getattr(args, 'battodo.format'), 'json')


class BATCLITests(TestCase):
    def setUp(t):
        patches = [
            'exit',
            'get_config',
        ]
        for target in patches:
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)

    def validate_commands(t, commands):
        for cmd in commands:
            with t.subTest(cmd):
                func = '_'.join(cmd.split())
                with patch(f'{SRC}.Commands.{func}', autospec=True) as m_cmd:
                    m_cmd.__name__ = func
                    ARGS = cmd.split()
                    BATCLI(ARGS)
                    args = argparser().parse_args(ARGS)
                    t.get_config.assert_called_with(
                        cli_args=args,
                        config_file_name=args.config_file,
                        config_env=args.config_env,
                    )
                    m_cmd.assert_called_with(t.get_config.return_value)
                    t.exit.assert_called_with(0)

    @patch(f'{SRC}.Commands.set_log_level', autospec=True)
    def test_set_log_level(t, set_log_level):
        args = [
            '--debug',
            'hello',
        ]
        BATCLI(args)
        set_log_level.assert_called_with(argparser().parse_args(args))
        t.exit.assert_called_with(0)

    def test_missing_command(t):
        """prints help if no arguments are given"""
        # A real parser, so `func` defaults to the real help closure.
        parser = argparser()
        parser.print_help = Mock(wraps=parser.print_help)

        with patch(f'{SRC}.argparser', return_value=parser):
            BATCLI([])

        parser.print_help.assert_called_with()

    def test_command_error(t):
        """a failing command reports on stderr and leaves stdout clean"""

        exc = Exception('boom')

        def fail(conf):
            raise exc

        args = argparser().parse_args([])
        args.func = fail
        parser = Mock(argparse.ArgumentParser)
        parser.parse_args.return_value = args
        out, err = StringIO(), StringIO()

        with (
            patch(f'{SRC}.argparser', return_value=parser),
            redirect_stdout(out),
            redirect_stderr(err),
        ):
            BATCLI([])

        with t.subTest('the message goes to stderr'):
            t.assertEqual(err.getvalue(), 'boom\n')

        with t.subTest('stdout stays parseable for a consumer'):
            t.assertEqual(out.getvalue(), '')

        with t.subTest('a runtime failure is not a usage error'):
            parser.print_help.assert_not_called()

        with t.subTest('the exit code is non-zero'):
            t.assertEqual(t.exit.call_args_list[0], call(1))

    def test_commands(t):
        commands = [
            'hello',
        ]

        t.validate_commands(commands)

    # TODO: full coverage of CLI arguments that trigger commands


class CommandsViewTests(TestCase):
    def setUp(t):
        for target in ('build_view', 'build_json'):
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        patcher = patch('builtins.print')
        t.print = patcher.start()
        t.addCleanup(patcher.stop)

        t.conf = Mock()
        t.conf.view.source_dir = '~/todo'
        t.conf.show_all = True
        t.conf.format = 'text'

    def test_view(t):
        with t.subTest('the human view is the default'):
            Commands.view(t.conf)

            args, kwargs = t.build_view.call_args
            t.print.assert_called_with(t.build_view.return_value)
            t.assertFalse(str(args[0]).startswith('~'))
            t.assertTrue(kwargs['show_all'])

        with t.subTest('json format is serialized instead'):
            t.print.reset_mock()
            t.conf.format = 'json'

            Commands.view(t.conf)

            args, kwargs = t.build_json.call_args
            t.print.assert_called_with(t.build_json.return_value)
            t.assertFalse(str(args[0]).startswith('~'))
            t.assertTrue(kwargs['show_all'])
            t.build_view.assert_called_once()


class CommandsBackfillTests(TestCase):
    def setUp(t):
        t.conf = Mock()
        t.conf.view.source_dir = '~/todo'

    @patch('builtins.print')
    @patch(f'{SRC}.backfill_all', autospec=True)
    def test_backfill(t, backfill_all, print):
        with t.subTest('reports a count per changed list'):
            backfill_all.return_value = {'work.md': ['a', 'b']}
            Commands.backfill(t.conf)
            print.assert_called_with('work.md: stamped 2')

        with t.subTest('says so when nothing needed stamping'):
            backfill_all.return_value = {}
            Commands.backfill(t.conf)
            print.assert_called_with('nothing to backfill')

        with t.subTest('source dir is expanded'):
            t.assertFalse(str(backfill_all.call_args[0][0]).startswith('~'))


class CommandsAddTests(TestCase):
    def setUp(t):
        patcher = patch(f'{SRC}.add_task', autospec=True)
        t.add_task = patcher.start()
        t.addCleanup(patcher.stop)
        patcher = patch('builtins.print')
        t.print = patcher.start()
        t.addCleanup(patcher.stop)

        t.path = Path('~/todo/chores.md')
        t.entry = '- [ ] Water it [P:4] [ADDED:2026-08-08] [ID:ab12cd]'
        t.add_task.return_value = (t.path, t.entry)

        # spec models batconf: an argument the user did not supply is
        # absent from the Configuration, not None.
        t.conf = Mock(spec=['view', 'list', 'title', 'priority', 'due'])
        t.conf.view.source_dir = '~/todo'
        t.conf.list = 'chores'
        t.conf.title = 'Water it'
        t.conf.priority = '4'
        t.conf.due = '2026-09-01'

    def test_add(t):
        with t.subTest('list, title and supplied fields are forwarded'):
            Commands.add(t.conf)

            args = t.add_task.call_args[0]
            t.assertFalse(str(args[0]).startswith('~'))
            t.assertEqual(args[1], 'chores')
            t.assertEqual(args[2], 'Water it')
            t.assertEqual(args[3], {'P': '4', 'DUE': '2026-09-01'})

        with t.subTest('the created line and its file are echoed'):
            # A P-less add ranks near 0 and will not show in a view, so
            # the echo is the only confirmation the user gets.
            t.print.assert_has_calls([call(t.entry), call(t.path)])

        with t.subTest('an add with no fields writes none'):
            t.add_task.reset_mock()
            conf = Mock(spec=['view', 'list', 'title'])
            conf.view.source_dir = '~/todo'
            conf.list = 'chores'
            conf.title = 'Water it'

            Commands.add(conf)

            t.assertEqual(t.add_task.call_args[0][3], {})


class CommandsDoneTests(TestCase):
    def setUp(t):
        t.conf = Mock()
        t.conf.view.source_dir = '~/todo'
        t.conf.selector = 'brush pile'

    @patch('builtins.print')
    @patch(f'{SRC}.complete', autospec=True)
    def test_done(t, complete, print):
        with t.subTest('prints the completed.md entries'):
            complete.return_value = ['2026-08-08 | chores | DONE | Chip it']
            Commands.done(t.conf)
            print.assert_called_with('2026-08-08 | chores | DONE | Chip it')

        with t.subTest('selector is forwarded, source dir expanded'):
            args = complete.call_args[0]
            t.assertFalse(str(args[0]).startswith('~'))
            t.assertEqual(args[1], 'brush pile')

        with t.subTest('says so when the item is not logged'):
            complete.return_value = []
            Commands.done(t.conf)
            print.assert_called_with('checked off')


class CommandsScratchTests(TestCase):
    def setUp(t):
        t.conf = Mock()
        t.conf.view.source_dir = '~/todo'
        t.conf.selector = 'brush pile'

    @patch('builtins.print')
    @patch(f'{SRC}.scratch', autospec=True)
    def test_scratch(t, scratch, print):
        with t.subTest('prints the completed.md entry'):
            scratch.return_value = ['2026-08-08 | chores | SCRATCHED | Chip']
            Commands.scratch(t.conf)
            print.assert_called_with('2026-08-08 | chores | SCRATCHED | Chip')

        with t.subTest('selector is forwarded, source dir expanded'):
            args = scratch.call_args[0]
            t.assertFalse(str(args[0]).startswith('~'))
            t.assertEqual(args[1], 'brush pile')

        with t.subTest('says so when the item is not logged'):
            scratch.return_value = []
            Commands.scratch(t.conf)
            print.assert_called_with('dropped')


class CliArgsResolutionTests(TestCase):
    """Parsed CLI arguments must resolve through the real Configuration.

    Cross-module by necessity: the contract under test is the seam
    between argparse dests and batconf's dotted config paths, which only
    exists when the real parser and the real get_config meet.
    """

    class NullFileSource:
        """Stands in for the config file; the filesystem is out of scope."""

        def get(self, key: str, path: str | None = None) -> None:
            return None

    def resolve(t, argv):
        args = argparser().parse_args(argv)
        return get_config(cli_args=args, config_file=t.NullFileSource())

    def test_cli_args(t):
        with t.subTest('a positional reaches the command'):
            t.assertEqual(
                t.resolve(['done', 'brush pile']).selector, 'brush pile'
            )

        with t.subTest('an option reaches the command'):
            t.assertEqual(
                t.resolve(['view', '--format', 'json']).format, 'json'
            )

        with t.subTest('a flag reaches the command'):
            t.assertTrue(t.resolve(['view', '--all']).show_all)

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


class CommandsTests(TestCase):
    @patch(f'{SRC}.log', autospec=True)
    def test_set_log_level(t, log):
        with t.subTest('default to ERROR'):
            args = argparse.Namespace(loglevel=logging.INFO)
            Commands.set_log_level(args)
            log.setLevel.assert_called_with(logging.INFO)

        with t.subTest('set given value'):
            args = argparse.Namespace(loglevel=logging.INFO)
            Commands.set_log_level(args)
            log.setLevel.assert_called_with(logging.INFO)
