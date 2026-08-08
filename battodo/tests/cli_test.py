from unittest import TestCase
from unittest.mock import Mock, patch

from ..cli import (
    BATCLI,
    Commands,
    NestedNameSpace,
    argparse,
    argparser,
    logging,
)

SRC = 'battodo.cli'


class TestArgparser(TestCase):
    def test_argparser(t):
        argparser()


class TestBATCLI(TestCase):
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
                        config_file=args.config_file,
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

    @patch('builtins.print')
    def test_command_error(t, print):
        """prints the error message, and help if a command throws an error"""
        exc = Exception()

        def fail(conf):
            raise exc

        args = argparser().parse_args([])
        args.func = fail
        parser = Mock(argparse.ArgumentParser)
        parser.parse_args.return_value = args

        with patch(f'{SRC}.argparser', return_value=parser):
            BATCLI([])

        print.assert_called_with(exc)
        parser.print_help.assert_called_with()

    def test_commands(t):
        commands = [
            'hello',
        ]

        t.validate_commands(commands)

    # TODO: full coverage of CLI arguments that trigger commands


class TestCommandsView(TestCase):
    @patch('builtins.print')
    @patch(f'{SRC}.build_view', autospec=True)
    def test_view(t, build_view, print):
        conf = Mock()
        conf.view.source_dir = '~/todo'
        conf.show_all = True

        Commands.view(conf)

        args, kwargs = build_view.call_args

        with t.subTest('source dir is expanded'):
            t.assertFalse(str(args[0]).startswith('~'))

        with t.subTest('show_all is forwarded'):
            t.assertTrue(kwargs['show_all'])

        with t.subTest('rendered view is printed'):
            print.assert_called_with(build_view.return_value)


class TestCommandsBackfill(TestCase):
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


class TestNestedNameSpace(TestCase):
    def test_nesting(t):
        nns = NestedNameSpace()
        nns.top = 'level'
        setattr(nns, 'bat.baz', 'baz')
        setattr(nns, 'bat.sub.var', 'sub_var')

        t.assertEqual(nns.top, 'level')
        t.assertEqual(nns.bat.baz, 'baz')
        t.assertEqual(nns.bat.sub.var, 'sub_var')


class TestCommands(TestCase):
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
