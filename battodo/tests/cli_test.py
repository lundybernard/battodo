from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, call, patch

from ..cli import (
    BATCLI,
    DEFAULT_PERIOD,
    MESSAGES,
    PERIODS,
    TZ,
    Commands,
    argparse,
    argparser,
    logging,
)

SRC = 'battodo.cli'
# The configured `~/todo` as every command resolves it.
SOURCE = Path.home() / 'todo'


def subparsers(parser):
    """Every parser reachable from `parser`, keyed by its command name."""
    found = {'btodo': parser}
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            found.update(action.choices)
    return found


def documented(parser):
    """Each string one parser must show, labelled with what shows it.

    `-h` is argparse's own, and a subparsers action carries no help of
    its own -- the text for each subcommand lives on the pseudo-action
    standing in for it.
    """
    yield 'description', parser.description
    for action in parser._actions:
        if isinstance(action, argparse._HelpAction):
            continue
        if isinstance(action, argparse._SubParsersAction):
            for choice in action._choices_actions:
                yield f'{choice.dest} command', choice.help
            continue
        yield action.dest, action.help
        if not action.option_strings:
            # A positional shows its metavar, or its dest -- and the
            # dest is a dotted config path, not something to read.
            yield f'{action.dest} metavar', action.metavar


def displayed(parser):
    """Every user-facing string one parser holds, `None`s included."""
    yield parser.usage
    group = parser._subparsers
    if group is not None:
        yield group.title
        yield group.description
    for _, text in documented(parser):
        yield text


class MessageCatalogTests(TestCase):
    """Every string the CLI displays is an entry in the catalog.

    Held apart from the parser so the wording can be translated, and so
    a display string is never mistaken for behaviour: the catalog is
    data, and only the lookups that reach into it are logic.
    """

    def setUp(t):
        t.parsers = subparsers(argparser())

    def test_every_screen_is_documented(t):
        for name, parser in t.parsers.items():
            for label, text in documented(parser):
                with t.subTest(f'{name} {label}'):
                    t.assertIn(text, MESSAGES.values())

    def test_no_entry_goes_unused(t):
        shown = {
            text
            for parser in t.parsers.values()
            for text in displayed(parser)
            if text is not None
        }
        t.assertEqual(set(MESSAGES.values()) - shown, set())


class ArgparserTests(TestCase):
    def setUp(t):
        t.parser = argparser()

    def test_argparser(t):
        p = t.parser

        with t.subTest('view renders for a human by default'):
            args = p.parse_args(['view'])
            t.assertEqual(getattr(args, 'battodo.format'), 'text')

        with t.subTest('view takes a machine-readable format'):
            args = p.parse_args(['view', '--format', 'json'])
            t.assertEqual(getattr(args, 'battodo.format'), 'json')

        with t.subTest('the default is also a format one may ask for'):
            args = p.parse_args(['view', '--format', 'text'])
            t.assertEqual(getattr(args, 'battodo.format'), 'text')

        with (
            t.subTest('an unknown format is a usage error'),
            redirect_stderr(StringIO()),
            t.assertRaises(SystemExit),
        ):
            p.parse_args(['view', '--format', 'xml'])

        with t.subTest('view leaves the count to the configuration'):
            args = p.parse_args(['view'])
            t.assertIsNone(getattr(args, 'battodo.view.top'))

        with t.subTest('view takes a count of its own, as a string'):
            args = p.parse_args(['view', '--top', '2'])
            t.assertEqual(getattr(args, 'battodo.view.top'), '2')

        for value in ('0', '-1', 'five'):
            with (
                t.subTest(f'a top of {value} is a usage error'),
                redirect_stderr(StringIO()),
                t.assertRaises(SystemExit),
            ):
                p.parse_args(['view', '--top', value])

        with t.subTest('show offers the same two formats, human first'):
            args = p.parse_args(['show', 'brush pile'])
            t.assertEqual(getattr(args, 'battodo.format'), 'text')
            args = p.parse_args(['show', 'brush pile', '--format', 'json'])
            t.assertEqual(getattr(args, 'battodo.format'), 'json')

        with t.subTest('and so does completed'):
            args = p.parse_args(['completed'])
            t.assertEqual(getattr(args, 'battodo.format'), 'text')
            args = p.parse_args(['completed', '--format', 'json'])
            t.assertEqual(getattr(args, 'battodo.format'), 'json')

    def test_every_subcommand_reaches_its_command(t):
        cases = [
            (['view'], Commands.view),
            (['add', 'chores', 'Water it'], Commands.add),
            (['show', 'brush pile'], Commands.show),
            (['update', 'brush pile', '-p', '3'], Commands.update),
            (['done', 'brush pile'], Commands.done),
            (['scratch', 'brush pile'], Commands.scratch),
            (['backfill'], Commands.backfill),
            (['completed'], Commands.completed),
        ]
        for argv, command in cases:
            with t.subTest(argv[0]):
                t.assertIs(t.parser.parse_args(argv).func, command)

    def test_verbosity(t):
        cases = {
            ('view',): None,
            ('-v', 'view'): logging.INFO,
            ('--verbose', 'view'): logging.INFO,
            ('--debug', 'view'): logging.DEBUG,
        }
        for argv, expected in cases.items():
            with t.subTest(' '.join(argv)):
                args = t.parser.parse_args(list(argv))
                t.assertEqual(args.loglevel, expected)

    def test_add_priority_spellings(t):
        for flag in ('-p', '--priority'):
            with t.subTest(flag):
                args = t.parser.parse_args(['add', 'chores', 'X', flag, '4'])
                t.assertEqual(getattr(args, 'battodo.priority'), '4')

    def test_completed_period(t):
        with t.subTest('the week when none is named'):
            args = t.parser.parse_args(['completed'])
            t.assertEqual(getattr(args, 'battodo.period'), DEFAULT_PERIOD)

        for period in PERIODS:
            with t.subTest(period):
                args = t.parser.parse_args(['completed', period])
                t.assertEqual(getattr(args, 'battodo.period'), period)

        with (
            t.subTest('a period with no definition is a usage error'),
            redirect_stderr(StringIO()),
            t.assertRaises(SystemExit),
        ):
            t.parser.parse_args(['completed', 'fortnight'])

    def test_config_selection(t):
        spellings = {
            'config_file': ('-c', '--conf', '--config_file'),
            'config_env': ('-e', '--env', '--config_environment'),
        }
        for dest, flags in spellings.items():
            for flag in flags:
                with t.subTest(flag):
                    args = t.parser.parse_args([flag, 'chosen', 'view'])
                    t.assertEqual(getattr(args, dest), 'chosen')

        with t.subTest('neither is required'):
            args = t.parser.parse_args(['view'])
            t.assertIsNone(args.config_file)
            t.assertIsNone(args.config_env)


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

    @patch(f'{SRC}.Commands.view', autospec=True)
    @patch(f'{SRC}.Commands.set_log_level', autospec=True)
    def test_set_log_level(t, set_log_level, view):
        args = [
            '--debug',
            'view',
        ]
        BATCLI(args)
        set_log_level.assert_called_with(argparser().parse_args(args))
        t.exit.assert_called_with(0)

    def test_missing_command(t):
        """prints help if no arguments are given"""
        # A real parser, so `func` defaults to the real help closure.
        parser = argparser()
        parser.print_help = Mock(wraps=parser.print_help)

        with patch(f'{SRC}.argparser', autospec=True, return_value=parser):
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
            patch(f'{SRC}.argparser', autospec=True, return_value=parser),
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
            'view',
        ]

        t.validate_commands(commands)

    def test_config_arguments_reach_the_configuration(t):
        """The two global options are the ones only BATCLI can forward."""
        with patch(f'{SRC}.Commands.view', autospec=True):
            BATCLI(['-c', 'other.toml', '-e', 'prod', 'view'])

        kwargs = t.get_config.call_args[1]
        t.assertEqual(kwargs['config_file_name'], 'other.toml')
        t.assertEqual(kwargs['config_env'], 'prod')


class ClockTests(TestCase):
    """Base for the commands that read the clock.

    It is mocked rather than compared against a real one: a real-value
    assertion would only catch a zoneless `now()` during the hours when
    the host's date and the app timezone's disagree.
    """

    def setUp(t):
        patcher = patch(f'{SRC}.datetime', autospec=True)
        t.datetime = patcher.start()
        t.addCleanup(patcher.stop)
        t.today = t.datetime.now.return_value.date.return_value


class CommandsViewTests(ClockTests):
    def setUp(t):
        super().setUp()
        patcher = patch(f'{SRC}.get_view', autospec=True)
        t.get_view = patcher.start()
        t.addCleanup(patcher.stop)
        patcher = patch('builtins.print', autospec=True)
        t.print = patcher.start()
        t.addCleanup(patcher.stop)

        t.conf = Mock(spec=['view', 'show_all', 'format'])

    def test_view(t):
        Commands.view(t.conf)

        with t.subTest('the configuration reaches the library unread'):
            t.get_view.assert_called_once_with(
                t.conf, t.datetime.now.return_value
            )

        with t.subTest('the clock is read in the local zone, not the host'):
            t.datetime.now.assert_called_with(TZ)

        with t.subTest('and the command prints what comes back'):
            t.print.assert_called_once_with(t.get_view.return_value)


class CommandsBackfillTests(ClockTests):
    def setUp(t):
        super().setUp()
        t.conf = Mock(spec=['view'])
        t.conf.view = Mock(spec=['source_dir'])
        t.conf.view.source_dir = '~/todo'

    @patch('builtins.print', autospec=True)
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

        with t.subTest('the source dir and the local day are forwarded'):
            args = backfill_all.call_args[0]
            t.assertEqual(args[0], SOURCE)
            t.assertEqual(args[1], t.today)
            t.datetime.now.assert_called_with(TZ)


class CommandsAddTests(ClockTests):
    def setUp(t):
        super().setUp()
        patcher = patch(f'{SRC}.add_item', autospec=True)
        t.add_item = patcher.start()
        t.addCleanup(patcher.stop)
        patcher = patch('builtins.print', autospec=True)
        t.print = patcher.start()
        t.addCleanup(patcher.stop)

        t.conf = Mock(spec=['view', 'list', 'title', 'priority', 'due'])

    def test_add(t):
        Commands.add(t.conf)

        with t.subTest('the configuration reaches the library unread'):
            t.add_item.assert_called_once_with(
                t.conf, t.datetime.now.return_value
            )

        with t.subTest('the clock is read in the local zone, not the host'):
            t.datetime.now.assert_called_with(TZ)

        with t.subTest('and the command prints what comes back'):
            t.print.assert_called_once_with(t.add_item.return_value)


class CommandsShowTests(ClockTests):
    def setUp(t):
        super().setUp()
        patcher = patch(f'{SRC}.get_item', autospec=True)
        t.get_item = patcher.start()
        t.addCleanup(patcher.stop)
        patcher = patch('builtins.print', autospec=True)
        t.print = patcher.start()
        t.addCleanup(patcher.stop)

        t.conf = Mock(spec=['view', 'selector', 'format'])

    def test_show(t):
        Commands.show(t.conf)

        with t.subTest('the configuration reaches the library unread'):
            t.get_item.assert_called_once_with(
                t.conf, t.datetime.now.return_value
            )

        with t.subTest('the clock is read in the local zone, not the host'):
            t.datetime.now.assert_called_with(TZ)

        with t.subTest('and the command prints what comes back'):
            t.print.assert_called_once_with(t.get_item.return_value)


class CommandsCompletedTests(ClockTests):
    def setUp(t):
        super().setUp()
        patcher = patch(f'{SRC}.get_completed', autospec=True)
        t.get_completed = patcher.start()
        t.addCleanup(patcher.stop)
        patcher = patch('builtins.print', autospec=True)
        t.print = patcher.start()
        t.addCleanup(patcher.stop)

        t.conf = Mock(spec=['view', 'period', 'format'])

    def test_completed(t):
        Commands.completed(t.conf)

        with t.subTest('the configuration reaches the library unread'):
            t.get_completed.assert_called_once_with(
                t.conf, t.datetime.now.return_value
            )

        with t.subTest('the clock is read in the local zone, not the host'):
            t.datetime.now.assert_called_with(TZ)

        with t.subTest('and the command prints what comes back'):
            t.print.assert_called_once_with(t.get_completed.return_value)


class CommandsUpdateTests(ClockTests):
    def setUp(t):
        super().setUp()
        patcher = patch(f'{SRC}.update_task', autospec=True)
        t.update_task = patcher.start()
        t.addCleanup(patcher.stop)
        patcher = patch('builtins.print', autospec=True)
        t.print = patcher.start()
        t.addCleanup(patcher.stop)

        t.path = Path('~/todo/chores.md')
        t.entry = '- [ ] Water it [P:4] [ID:ab12cd]'
        t.update_task.return_value = (t.path, t.entry)

        # spec models batconf: an option the user did not supply is
        # absent from the Configuration, not None.
        t.conf = Mock(spec=['view', 'selector', 'priority', 'due', 'title'])
        t.conf.view = Mock(spec=['source_dir'])
        t.conf.view.source_dir = '~/todo'
        t.conf.selector = 'brush pile'
        t.conf.priority = '4'
        t.conf.due = '2026-09-01'
        t.conf.title = 'Water it'

    def test_update(t):
        with t.subTest('selector, supplied fields and title are forwarded'):
            Commands.update(t.conf)

            args, kwargs = t.update_task.call_args
            t.assertEqual(args[0], SOURCE)
            t.assertEqual(args[1], 'brush pile')
            t.assertEqual(args[2], {'P': '4', 'DUE': '2026-09-01'})
            t.assertEqual(args[3], t.today)
            t.assertEqual(kwargs['title'], 'Water it')
            t.datetime.now.assert_called_with(TZ)

        with t.subTest('the written line and its file are echoed'):
            t.print.assert_has_calls([call(t.entry), call(t.path)])

        with t.subTest('an option left off names no change to that field'):
            t.update_task.reset_mock()
            conf = Mock(spec=['view', 'selector', 'tags'])
            conf.view.source_dir = '~/todo'
            conf.selector = 'brush pile'
            conf.tags = 'yard,summer'

            Commands.update(conf)

            args, kwargs = t.update_task.call_args
            t.assertEqual(args[2], {'TAGS': 'yard,summer'})
            t.assertIsNone(kwargs['title'])


class CommandsDoneTests(ClockTests):
    def setUp(t):
        super().setUp()
        t.conf = Mock(spec=['view', 'selector'])
        t.conf.view = Mock(spec=['source_dir'])
        t.conf.view.source_dir = '~/todo'
        t.conf.selector = 'brush pile'

    @patch('builtins.print', autospec=True)
    @patch(f'{SRC}.complete', autospec=True)
    def test_done(t, complete, print):
        with t.subTest('prints the completed.md entries, one per line'):
            # Completing the last open child completes its parent too,
            # so one command can log more than one entry.
            complete.return_value = [
                '2026-08-08 | chores | DONE | Deck > Chip it',
                '2026-08-08 | chores | DONE | Deck',
            ]
            Commands.done(t.conf)
            print.assert_called_with(
                '2026-08-08 | chores | DONE | Deck > Chip it\n'
                '2026-08-08 | chores | DONE | Deck'
            )

        with t.subTest('selector, source dir and local day are forwarded'):
            args = complete.call_args[0]
            t.assertEqual(args[0], SOURCE)
            t.assertEqual(args[1], 'brush pile')
            t.assertEqual(args[2], t.today)
            t.datetime.now.assert_called_with(TZ)

        with t.subTest('says so when the item is not logged'):
            complete.return_value = []
            Commands.done(t.conf)
            print.assert_called_with('checked off')


class CommandsScratchTests(ClockTests):
    def setUp(t):
        super().setUp()
        t.conf = Mock(spec=['view', 'selector'])
        t.conf.view = Mock(spec=['source_dir'])
        t.conf.view.source_dir = '~/todo'
        t.conf.selector = 'brush pile'

    @patch('builtins.print', autospec=True)
    @patch(f'{SRC}.scratch', autospec=True)
    def test_scratch(t, scratch, print):
        with t.subTest('prints the completed.md entries, one per line'):
            scratch.return_value = [
                '2026-08-08 | chores | SCRATCHED | Deck > Chip',
                '2026-08-08 | chores | SCRATCHED | Deck',
            ]
            Commands.scratch(t.conf)
            print.assert_called_with(
                '2026-08-08 | chores | SCRATCHED | Deck > Chip\n'
                '2026-08-08 | chores | SCRATCHED | Deck'
            )

        with t.subTest('selector, source dir and local day are forwarded'):
            args = scratch.call_args[0]
            t.assertEqual(args[0], SOURCE)
            t.assertEqual(args[1], 'brush pile')
            t.assertEqual(args[2], t.today)
            t.datetime.now.assert_called_with(TZ)

        with t.subTest('says so when the item is not logged'):
            scratch.return_value = []
            Commands.scratch(t.conf)
            print.assert_called_with('dropped')


class CommandsTests(TestCase):
    @patch(f'{SRC}.log', autospec=True)
    def test_set_log_level(t, log):
        with t.subTest('default to ERROR'):
            args = argparse.Namespace(loglevel=None)
            Commands.set_log_level(args)
            log.setLevel.assert_called_with(logging.ERROR)

        with t.subTest('set given value'):
            args = argparse.Namespace(loglevel=logging.INFO)
            Commands.set_log_level(args)
            log.setLevel.assert_called_with(logging.INFO)
