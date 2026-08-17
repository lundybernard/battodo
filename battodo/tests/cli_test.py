from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, call, patch

from ..cli import (
    BATCLI,
    MESSAGES,
    TZ,
    Commands,
    argparse,
    argparser,
    get_config,
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

        with t.subTest('show offers the same two formats, human first'):
            args = p.parse_args(['show', 'brush pile'])
            t.assertEqual(getattr(args, 'battodo.format'), 'text')
            args = p.parse_args(['show', 'brush pile', '--format', 'json'])
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

        t.conf = Mock()
        t.conf.view.source_dir = '~/todo'


class CommandsViewTests(ClockTests):
    def setUp(t):
        super().setUp()
        for target in ('build_view', 'build_json'):
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        patcher = patch('builtins.print')
        t.print = patcher.start()
        t.addCleanup(patcher.stop)

        # spec models batconf: an option the user did not supply is
        # absent from the Configuration, not None.
        t.conf = Mock(spec=['view', 'show_all', 'format'])
        t.conf.view.source_dir = '~/todo'
        t.conf.show_all = True
        t.conf.format = 'text'

    def test_view(t):
        with t.subTest('the human view is the default'):
            Commands.view(t.conf)

            args, kwargs = t.build_view.call_args
            t.print.assert_called_with(t.build_view.return_value)
            t.assertEqual(args[0], SOURCE)
            t.assertEqual(args[1], t.datetime.now.return_value)
            t.assertTrue(kwargs['show_all'])

        with t.subTest('the clock is read in the local zone, not the host'):
            t.datetime.now.assert_called_with(TZ)

        with t.subTest('json format is serialized instead'):
            t.print.reset_mock()
            t.conf.format = 'json'

            Commands.view(t.conf)

            args, kwargs = t.build_json.call_args
            t.print.assert_called_with(t.build_json.return_value)
            t.assertEqual(args[0], SOURCE)
            t.assertEqual(args[1], t.datetime.now.return_value)
            t.assertTrue(kwargs['show_all'])
            t.build_view.assert_called_once()

        with t.subTest('an unconfigured view is human and abridged'):
            conf = Mock(spec=['view'])
            conf.view.source_dir = '~/todo'

            Commands.view(conf)

            t.assertEqual(t.build_view.call_count, 2)
            t.assertFalse(t.build_view.call_args[1]['show_all'])


class CommandsBackfillTests(ClockTests):
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

        with t.subTest('the source dir and the local day are forwarded'):
            args = backfill_all.call_args[0]
            t.assertEqual(args[0], SOURCE)
            t.assertEqual(args[1], t.today)
            t.datetime.now.assert_called_with(TZ)


class CommandsAddTests(ClockTests):
    def setUp(t):
        super().setUp()
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
            t.assertEqual(args[0], SOURCE)
            t.assertEqual(args[1], 'chores')
            t.assertEqual(args[2], 'Water it')
            t.assertEqual(args[3], {'P': '4', 'DUE': '2026-09-01'})
            t.assertEqual(args[4], t.today)
            t.datetime.now.assert_called_with(TZ)

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


class CommandsShowTests(ClockTests):
    def setUp(t):
        super().setUp()
        for target in ('build_item', 'build_item_json'):
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        patcher = patch('builtins.print')
        t.print = patcher.start()
        t.addCleanup(patcher.stop)

        # spec models batconf: an option the user did not supply is
        # absent from the Configuration, not None.
        t.conf = Mock(spec=['view', 'selector', 'format'])
        t.conf.view.source_dir = '~/todo'
        t.conf.selector = 'brush pile'
        t.conf.format = 'text'

    def test_show(t):
        with t.subTest('the human form is the default'):
            Commands.show(t.conf)

            args = t.build_item.call_args[0]
            t.print.assert_called_with(t.build_item.return_value)
            t.assertEqual(args[0], SOURCE)
            t.assertEqual(args[1], 'brush pile')
            t.assertEqual(args[2], t.datetime.now.return_value)

        with t.subTest('the clock is read in the local zone, not the host'):
            t.datetime.now.assert_called_with(TZ)

        with t.subTest('json format is serialized instead'):
            t.print.reset_mock()
            t.conf.format = 'json'

            Commands.show(t.conf)

            args = t.build_item_json.call_args[0]
            t.print.assert_called_with(t.build_item_json.return_value)
            t.assertEqual(args[1], 'brush pile')
            t.build_item.assert_called_once()

        with t.subTest('an unconfigured show is the human form'):
            conf = Mock(spec=['view', 'selector'])
            conf.view.source_dir = '~/todo'
            conf.selector = 'brush pile'

            Commands.show(conf)

            t.assertEqual(t.build_item.call_count, 2)


class CommandsUpdateTests(ClockTests):
    def setUp(t):
        super().setUp()
        patcher = patch(f'{SRC}.update_task', autospec=True)
        t.update_task = patcher.start()
        t.addCleanup(patcher.stop)
        patcher = patch('builtins.print')
        t.print = patcher.start()
        t.addCleanup(patcher.stop)

        t.path = Path('~/todo/chores.md')
        t.entry = '- [ ] Water it [P:4] [ID:ab12cd]'
        t.update_task.return_value = (t.path, t.entry)

        # spec models batconf: an option the user did not supply is
        # absent from the Configuration, not None.
        t.conf = Mock(spec=['view', 'selector', 'priority', 'due', 'title'])
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
        t.conf.selector = 'brush pile'

    @patch('builtins.print')
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
        t.conf.selector = 'brush pile'

    @patch('builtins.print')
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
            args = argparse.Namespace(loglevel=None)
            Commands.set_log_level(args)
            log.setLevel.assert_called_with(logging.ERROR)

        with t.subTest('set given value'):
            args = argparse.Namespace(loglevel=logging.INFO)
            Commands.set_log_level(args)
            log.setLevel.assert_called_with(logging.INFO)
