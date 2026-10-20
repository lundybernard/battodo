from argparse import Namespace, _HelpAction, _SubParsersAction
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, call, patch, sentinel

from ..cli import (
    BATCLI,
    DEFAULT_PERIOD,
    LOG_LEVELS,
    MESSAGES,
    PERIODS,
    ArgumentParser,
    Commands,
    argparser,
)

SRC = 'battodo.cli'


def clock(t: TestCase) -> Mock:
    """A stand-in for the clock the commands read.

    It stands in rather than being compared against a real one: a
    real-value assertion would only catch a zoneless `now()` during the
    hours when the host's date and the app timezone's disagree.
    """
    patcher = patch(f'{SRC}.datetime', autospec=True)
    t.addCleanup(patcher.stop)
    return patcher.start()


def zone(t: TestCase) -> Mock:
    """A stand-in for the decoder of the configured zone."""
    patcher = patch(f'{SRC}.time_zone', autospec=True)
    t.addCleanup(patcher.stop)
    return patcher.start()


def subparsers(parser):
    """Every parser reachable from `parser`, keyed by its command name."""
    found = {'btodo': parser}
    for action in parser._actions:
        if isinstance(action, _SubParsersAction):
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
        if isinstance(action, _HelpAction):
            continue
        if isinstance(action, _SubParsersAction):
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
    """Unit tests for battodo.cli.MESSAGES.

    Every string the CLI displays is an entry in the catalog.

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
    """Unit tests for battodo.cli.argparser."""

    def setUp(t):
        t.parser = argparser()

    def test_format(t):
        # TODO: --format cuts across the view and show commands. Move it
        # up one level to serve both, or split the cases per command.
        with t.subTest('view holds None when the flag is not given'):
            # The schema default answers, below the environment and the
            # config file.
            args = t.parser.parse_args(['view'])
            t.assertIsNone(getattr(args, 'battodo.format'))

        with t.subTest('view holds json when json is asked for'):
            args = t.parser.parse_args(['view', '--format', 'json'])
            t.assertEqual(getattr(args, 'battodo.format'), 'json')

        with t.subTest('the default is accepted by name too'):
            args = t.parser.parse_args(['view', '--format', 'text'])
            t.assertEqual(getattr(args, 'battodo.format'), 'text')

        for argv in (
            ['view'],
            ['show', 'brush pile'],
            ['completed'],
            ['history', 'brush pile'],
        ):
            with t.subTest(f'an unknown {argv[0]} format is a usage error'):
                stderr = StringIO()

                with (
                    redirect_stderr(stderr),
                    t.assertRaises(SystemExit) as caught,
                ):
                    t.parser.parse_args([*argv, '--format', 'xml'])

                t.assertEqual(caught.exception.code, 2)
                t.assertIn(
                    "error: argument --format: invalid choice: 'xml'",
                    stderr.getvalue(),
                )

        with t.subTest('show holds the same two values'):
            # Two cycles: each one checks one of the two accepted values.
            args = t.parser.parse_args(['show', 'brush pile'])
            t.assertIsNone(getattr(args, 'battodo.format'))

            args = t.parser.parse_args(
                ['show', 'brush pile', '--format', 'json']
            )
            t.assertEqual(getattr(args, 'battodo.format'), 'json')

        with t.subTest('and so does completed'):
            # Two cycles: each one checks one of the two accepted values.
            args = t.parser.parse_args(['completed'])
            t.assertIsNone(getattr(args, 'battodo.format'))

            args = t.parser.parse_args(['completed', '--format', 'json'])
            t.assertEqual(getattr(args, 'battodo.format'), 'json')

        with t.subTest('and so does history'):
            # Two cycles: each one checks one of the two accepted values.
            args = t.parser.parse_args(['history', 'brush pile'])
            t.assertIsNone(getattr(args, 'battodo.format'))

            args = t.parser.parse_args(
                ['history', 'brush pile', '--format', 'json']
            )
            t.assertEqual(getattr(args, 'battodo.format'), 'json')

    def test_top(t):
        with t.subTest('None when the flag is not given'):
            args = t.parser.parse_args(['view'])
            t.assertIsNone(getattr(args, 'battodo.view.top'))

        with t.subTest('the string as typed when it is'):
            args = t.parser.parse_args(['view', '--top', '2'])
            t.assertEqual(getattr(args, 'battodo.view.top'), '2')

        count_error = 'the item count must be a whole number of 1 or more'
        for value in ('0', '-1', 'five'):
            with t.subTest(f'a top of {value} exits with a usage error'):
                stderr = StringIO()

                with (
                    redirect_stderr(stderr),
                    t.assertRaises(SystemExit) as caught,
                ):
                    t.parser.parse_args(['view', '--top', value])

                t.assertEqual(caught.exception.code, 2)
                t.assertIn(
                    f'error: argument --top: {count_error}: {value}',
                    stderr.getvalue(),
                )

    def test_view_all(t):
        with t.subTest('Default: False'):
            args = t.parser.parse_args(['view'])
            t.assertFalse(args.show_all)

        with t.subTest('view --all asks for every item'):
            args = t.parser.parse_args(['view', '--all'])
            t.assertTrue(args.show_all)

    def test_every_subcommand_reaches_its_command(t):
        cases = [
            (['view'], Commands.view),
            (['add', 'chores', 'Water it'], Commands.add),
            (['show', 'brush pile'], Commands.show),
            (['update', 'brush pile', '-p', '3'], Commands.update),
            (['done', 'brush pile'], Commands.done),
            (['note', 'brush pile', 'Too wet'], Commands.note),
            (['history', 'brush pile'], Commands.history),
            (['backfill'], Commands.backfill),
            (['completed'], Commands.completed),
        ]
        for argv, command in cases:
            with t.subTest(argv[0]):
                args = t.parser.parse_args(argv)
                t.assertIs(args.func, command)

    def test_verbosity(t):
        cases = {
            ('view',): None,
            ('-v', 'view'): 'INFO',
            ('--verbose', 'view'): 'INFO',
            ('--debug', 'view'): 'DEBUG',
        }

        for argv, expected in cases.items():
            with t.subTest(' '.join(argv)):
                args = t.parser.parse_args(list(argv))
                t.assertEqual(getattr(args, 'battodo.loglevel'), expected)

    def test_add_priority_spellings(t):
        for flag in ('-p', '--priority'):
            with t.subTest(flag):
                args = t.parser.parse_args(['add', 'chores', 'X', flag, '4'])
                t.assertEqual(args.priority, '4')

    def test_selector(t):
        commands = ('show', 'update', 'done', 'note', 'history')
        for command in commands:
            with t.subTest(command):
                args = t.parser.parse_args([command, 'brush pile'])
                t.assertEqual(args.selector, 'brush pile')

    def test_description(t):
        for argv in (['add', 'chores', 'X'], ['update', 'brush pile']):
            with t.subTest(f'{argv[0]} holds None when the flag is not given'):
                args = t.parser.parse_args(argv)
                t.assertIsNone(args.description)

            with t.subTest(f'{argv[0]} --description holds its text'):
                args = t.parser.parse_args([*argv, '--description', 'A\nB'])
                t.assertEqual(args.description, 'A\nB')

            with t.subTest(f'{argv[0]} --description takes an empty text'):
                args = t.parser.parse_args([*argv, '--description', ''])
                t.assertEqual(args.description, '')

    def test_update_list(t):
        with t.subTest('None when not given'):
            args = t.parser.parse_args(['update', 'brush pile'])
            t.assertIsNone(args.list_name)

        with t.subTest('--list holds the name of a list'):
            args = t.parser.parse_args(
                ['update', 'brush pile', '--list', 'chores'],
            )
            t.assertEqual(args.list_name, 'chores')

    def test_update_repeat(t):
        with t.subTest('None when not given'):
            args = t.parser.parse_args(['update', 'brush pile'])
            t.assertIsNone(args.repeat)

        with t.subTest('--repeat holds its text, None as a word'):
            args = t.parser.parse_args(
                ['update', 'brush pile', '--repeat', 'None'],
            )
            t.assertEqual(args.repeat, 'None')

    def test_update_with_subtasks(t):
        with t.subTest('off when not given'):
            args = t.parser.parse_args(['update', 'brush pile'])
            t.assertFalse(args.with_subtasks)

        with t.subTest('on when given'):
            args = t.parser.parse_args(
                ['update', 'brush pile', '--with-subtasks'],
            )
            t.assertTrue(args.with_subtasks)

    def test_done_date(t):
        with t.subTest('Default: None'):
            args = t.parser.parse_args(['done', 'brush pile'])
            t.assertIsNone(args.date)

        with t.subTest('done --date accepts an ISO date string'):
            args = t.parser.parse_args(
                ['done', 'brush pile', '--date', '2026-08-15'],
            )
            t.assertEqual(args.date, '2026-08-15')

    def test_done_scratch(t):
        with t.subTest('off when not given'):
            args = t.parser.parse_args(['done', 'brush pile'])
            t.assertFalse(args.scratch)

        with t.subTest('on when given'):
            args = t.parser.parse_args(['done', 'brush pile', '--scratch'])
            t.assertTrue(args.scratch)

    def test_attributes(t):
        for argv in [
            ['done', 'brush pile'],
            ['update', 'brush pile'],
            ['add', 'chores', 'Water it'],
        ]:
            with t.subTest(f'{argv[0]}: None when not given'):
                args = t.parser.parse_args(argv)
                t.assertEqual((args.attrs, args.note), (None, None))

            with t.subTest(f'{argv[0]} takes both'):
                given = [*argv, '--attrs', 'cost=45.00', '--note', 'a note']
                args = t.parser.parse_args(given)
                t.assertEqual(
                    (args.attrs, args.note), ('cost=45.00', 'a note')
                )

    def test_note(t):
        with t.subTest('None when neither is given'):
            args = t.parser.parse_args(['note', 'brush pile'])
            t.assertEqual((args.text, args.attrs), (None, None))

        with t.subTest('the text and the attributes'):
            given = ['note', 'brush pile', 'Too wet', '--attrs', 'cost=0']
            args = t.parser.parse_args(given)
            t.assertEqual((args.text, args.attrs), ('Too wet', 'cost=0'))

        with t.subTest('note takes no --note'):
            stderr = StringIO()

            with redirect_stderr(stderr), t.assertRaises(SystemExit) as caught:
                t.parser.parse_args(['note', 'brush pile', '--note', 'Wet'])

            t.assertEqual(caught.exception.code, 2)
            t.assertIn(
                'error: unrecognized arguments: --note',
                stderr.getvalue(),
            )

    def test_completed_period(t):
        with t.subTest('the week when none is named'):
            args = t.parser.parse_args(['completed'])
            t.assertEqual(args.period, DEFAULT_PERIOD)

        for period in PERIODS:
            with t.subTest(period):
                args = t.parser.parse_args(['completed', period])
                t.assertEqual(args.period, period)

        with t.subTest('a period with no definition is a usage error'):
            stderr = StringIO()

            with redirect_stderr(stderr), t.assertRaises(SystemExit) as caught:
                t.parser.parse_args(['completed', 'fortnight'])

            t.assertEqual(caught.exception.code, 2)
            t.assertIn(
                "error: argument period: invalid choice: 'fortnight'",
                stderr.getvalue(),
            )

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
    """Unit tests for battodo.cli.BATCLI."""

    def setUp(t):
        # The entry point sets a level on the real logger. Patched, so
        # a run leaves the level of the test process alone.
        patches = {
            'exit': f'{SRC}.sys.exit',
            'get_config': f'{SRC}.get_config',
            'log': f'{SRC}.log',
        }
        for name, target in patches.items():
            patcher = patch(target, autospec=True)
            setattr(t, name, patcher.start())
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
                    m_cmd.assert_called_with(t.get_config.return_value, args)
                    t.exit.assert_called_with(0)

    @patch(f'{SRC}.Commands.view', autospec=True)
    @patch(f'{SRC}.Commands.set_log_level', autospec=True)
    def test_set_log_level(t, set_log_level, view):
        args = [
            '--debug',
            'view',
        ]

        BATCLI(args)

        set_log_level.assert_called_with(t.get_config.return_value)
        t.exit.assert_called_with(0)

    @patch(f'{SRC}.Commands.view', autospec=True)
    @patch(f'{SRC}.Commands.set_log_level', autospec=True)
    def test_log_level_error(t, set_log_level, view):
        """a bad log level reports on stderr and leaves stdout clean"""
        msg = (
            "unknown log level 'bogus'; choose one of CRITICAL, ERROR, WARNING, INFO, DEBUG"
        )
        set_log_level.side_effect = ValueError(msg)
        out, err = StringIO(), StringIO()

        with redirect_stdout(out), redirect_stderr(err):
            BATCLI(['view'])

        with t.subTest('the message goes to stderr'):
            t.assertEqual(err.getvalue(), f'{msg}\n')

        with t.subTest('stdout stays parseable for a consumer'):
            t.assertEqual(out.getvalue(), '')

        with t.subTest('the command does not run'):
            view.assert_not_called()

        with t.subTest('the exit code is non-zero'):
            t.assertEqual(t.exit.call_args_list[0], call(1))

    def test_missing_command(t):
        """prints help if no arguments are given"""
        # A real parser, so `func` defaults to the real help closure.
        parser = argparser()
        parser.print_help = Mock(wraps=parser.print_help)

        with (
            patch(f'{SRC}.argparser', autospec=True, return_value=parser),
            redirect_stdout(StringIO()),
        ):
            BATCLI([])

        parser.print_help.assert_called_with()

    def test_command_error(t):
        """a failing command reports on stderr and leaves stdout clean"""

        exc = Exception('boom')

        def fail(conf, args):
            raise exc

        args = argparser().parse_args([])
        args.func = fail
        parser = Mock(ArgumentParser)
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


class CommandsViewTests(TestCase):
    """Unit tests for battodo.cli.Commands.view."""

    def setUp(t):
        t.datetime = clock(t)
        t.time_zone = zone(t)
        patcher = patch(f'{SRC}.get_view', autospec=True)
        t.get_view = patcher.start()
        t.addCleanup(patcher.stop)
        patcher = patch('builtins.print', autospec=True)
        t.print = patcher.start()
        t.addCleanup(patcher.stop)

        t.conf = Mock(spec=['view', 'format'])
        t.args = Namespace(show_all=True)

    def test_view(t):
        Commands.view(t.conf, t.args)

        with t.subTest('the input reaches the library beside the config'):
            t.get_view.assert_called_once_with(
                t.conf,
                t.datetime.now.return_value,
                show_all=True,
            )

        with t.subTest('the clock is read in the configured zone'):
            t.time_zone.assert_called_with(t.conf)
            t.datetime.now.assert_called_with(t.time_zone.return_value)

        with t.subTest('and the command prints what comes back'):
            t.print.assert_called_once_with(t.get_view.return_value)


class CommandsBackfillTests(TestCase):
    """Unit tests for battodo.cli.Commands.backfill."""

    def setUp(t):
        t.datetime = clock(t)
        t.time_zone = zone(t)
        patcher = patch(f'{SRC}.backfill_items', autospec=True)
        t.backfill_items = patcher.start()
        t.addCleanup(patcher.stop)
        patcher = patch('builtins.print', autospec=True)
        t.print = patcher.start()
        t.addCleanup(patcher.stop)

        t.conf = Mock(spec=['view'])
        t.args = Namespace()

    def test_backfill(t):
        Commands.backfill(t.conf, t.args)

        with t.subTest('the configuration reaches the library unread'):
            t.backfill_items.assert_called_once_with(
                t.conf,
                t.datetime.now.return_value,
            )

        with t.subTest('the clock is read in the configured zone'):
            t.time_zone.assert_called_with(t.conf)
            t.datetime.now.assert_called_with(t.time_zone.return_value)

        with t.subTest('and the command prints what comes back'):
            t.print.assert_called_once_with(t.backfill_items.return_value)


class CommandsAddTests(TestCase):
    """Unit tests for battodo.cli.Commands.add."""

    def setUp(t):
        t.datetime = clock(t)
        t.time_zone = zone(t)
        patcher = patch(f'{SRC}.add_item', autospec=True)
        t.add_item = patcher.start()
        t.addCleanup(patcher.stop)
        patcher = patch('builtins.print', autospec=True)
        t.print = patcher.start()
        t.addCleanup(patcher.stop)

        t.conf = Mock(spec=['view'])
        t.args = Namespace(
            list_name='a list',
            title='a title',
            parent='a parent',
            priority='a priority',
            loe='a loe',
            due='a due date',
            repeat='a repeat',
            tags='some tags',
            description='a description',
            attrs='some attrs',
            note='a note',
        )

    def test_add(t):
        Commands.add(t.conf, t.args)

        with t.subTest('the inputs reach the library beside the config'):
            t.add_item.assert_called_once_with(
                t.conf,
                t.datetime.now.return_value,
                list_name='a list',
                title='a title',
                parent='a parent',
                priority='a priority',
                loe='a loe',
                due='a due date',
                repeat='a repeat',
                tags='some tags',
                description='a description',
                attrs='some attrs',
                note='a note',
            )

        with t.subTest('the clock is read in the configured zone'):
            t.time_zone.assert_called_with(t.conf)
            t.datetime.now.assert_called_with(t.time_zone.return_value)

        with t.subTest('and the command prints what comes back'):
            t.print.assert_called_once_with(t.add_item.return_value)


class CommandsShowTests(TestCase):
    """Unit tests for battodo.cli.Commands.show."""

    def setUp(t):
        t.datetime = clock(t)
        t.time_zone = zone(t)
        patcher = patch(f'{SRC}.get_item', autospec=True)
        t.get_item = patcher.start()
        t.addCleanup(patcher.stop)
        patcher = patch('builtins.print', autospec=True)
        t.print = patcher.start()
        t.addCleanup(patcher.stop)

        t.conf = Mock(spec=['view', 'format'])
        t.args = Namespace(selector='a selector')

    def test_show(t):
        Commands.show(t.conf, t.args)

        with t.subTest('the input reaches the library beside the config'):
            t.get_item.assert_called_once_with(
                t.conf,
                t.datetime.now.return_value,
                selector='a selector',
            )

        with t.subTest('the clock is read in the configured zone'):
            t.time_zone.assert_called_with(t.conf)
            t.datetime.now.assert_called_with(t.time_zone.return_value)

        with t.subTest('and the command prints what comes back'):
            t.print.assert_called_once_with(t.get_item.return_value)


class CommandsHistoryTests(TestCase):
    """Unit tests for battodo.cli.Commands.history."""

    def setUp(t):
        t.datetime = clock(t)
        t.time_zone = zone(t)
        patcher = patch(f'{SRC}.get_history', autospec=True)
        t.get_history = patcher.start()
        t.addCleanup(patcher.stop)
        patcher = patch('builtins.print', autospec=True)
        t.print = patcher.start()
        t.addCleanup(patcher.stop)

        t.conf = Mock(spec=['view', 'format'])
        t.args = Namespace(selector='a selector')

    def test_history(t):
        Commands.history(t.conf, t.args)

        with t.subTest('the input reaches the library beside the config'):
            t.get_history.assert_called_once_with(
                t.conf,
                t.datetime.now.return_value,
                selector='a selector',
            )

        with t.subTest('the clock is read in the configured zone'):
            t.time_zone.assert_called_with(t.conf)
            t.datetime.now.assert_called_with(t.time_zone.return_value)

        with t.subTest('and the command prints what comes back'):
            t.print.assert_called_once_with(t.get_history.return_value)


class CommandsCompletedTests(TestCase):
    """Unit tests for battodo.cli.Commands.completed."""

    def setUp(t):
        t.datetime = clock(t)
        t.time_zone = zone(t)
        patcher = patch(f'{SRC}.get_completed', autospec=True)
        t.get_completed = patcher.start()
        t.addCleanup(patcher.stop)
        patcher = patch('builtins.print', autospec=True)
        t.print = patcher.start()
        t.addCleanup(patcher.stop)

        t.conf = Mock(spec=['view', 'format'])
        t.args = Namespace(period='a period')

    def test_completed(t):
        Commands.completed(t.conf, t.args)

        with t.subTest('the input reaches the library beside the config'):
            t.get_completed.assert_called_once_with(
                t.conf,
                t.datetime.now.return_value,
                period='a period',
            )

        with t.subTest('the clock is read in the configured zone'):
            t.time_zone.assert_called_with(t.conf)
            t.datetime.now.assert_called_with(t.time_zone.return_value)

        with t.subTest('and the command prints what comes back'):
            t.print.assert_called_once_with(t.get_completed.return_value)


class CommandsUpdateTests(TestCase):
    """Unit tests for battodo.cli.Commands.update."""

    def setUp(t):
        t.datetime = clock(t)
        t.time_zone = zone(t)
        patcher = patch(f'{SRC}.update_item', autospec=True)
        t.update_item = patcher.start()
        t.addCleanup(patcher.stop)
        patcher = patch('builtins.print', autospec=True)
        t.print = patcher.start()
        t.addCleanup(patcher.stop)

        t.conf = Mock(spec=['view'])
        t.args = Namespace(
            selector='a selector',
            title='a title',
            priority='a priority',
            due='a due date',
            repeat='a repeat',
            tags='some tags',
            description='a description',
            attrs='some attrs',
            note='a note',
            list_name='a list',
            with_subtasks=True,
        )

    def test_update(t):
        Commands.update(t.conf, t.args)

        with t.subTest('the inputs reach the library beside the config'):
            t.update_item.assert_called_once_with(
                t.conf,
                t.datetime.now.return_value,
                selector='a selector',
                title='a title',
                priority='a priority',
                due='a due date',
                repeat='a repeat',
                tags='some tags',
                description='a description',
                attrs='some attrs',
                note='a note',
                list_name='a list',
                with_subtasks=True,
            )

        with t.subTest('the clock is read in the configured zone'):
            t.time_zone.assert_called_with(t.conf)
            t.datetime.now.assert_called_with(t.time_zone.return_value)

        with t.subTest('and the command prints what comes back'):
            t.print.assert_called_once_with(t.update_item.return_value)


class CommandsDoneTests(TestCase):
    """Unit tests for battodo.cli.Commands.done."""

    def setUp(t):
        t.datetime = clock(t)
        t.time_zone = zone(t)
        patcher = patch(f'{SRC}.complete_item', autospec=True)
        t.complete_item = patcher.start()
        t.addCleanup(patcher.stop)
        patcher = patch('builtins.print', autospec=True)
        t.print = patcher.start()
        t.addCleanup(patcher.stop)

        t.conf = Mock(spec=['view'])
        t.args = Namespace(
            selector='a selector',
            date='a date',
            scratch=True,
            attrs='some attrs',
            note='a note',
        )

    def test_done(t):
        Commands.done(t.conf, t.args)

        with t.subTest('the inputs reach the library beside the config'):
            t.complete_item.assert_called_once_with(
                t.conf,
                t.datetime.now.return_value,
                selector='a selector',
                date='a date',
                scratch=True,
                attrs='some attrs',
                note='a note',
            )

        with t.subTest('the clock is read in the configured zone'):
            t.time_zone.assert_called_with(t.conf)
            t.datetime.now.assert_called_with(t.time_zone.return_value)

        with t.subTest('and the command prints what comes back'):
            t.print.assert_called_once_with(t.complete_item.return_value)


class CommandsNoteTests(TestCase):
    """Unit tests for battodo.cli.Commands.note."""

    def setUp(t):
        t.datetime = clock(t)
        t.time_zone = zone(t)
        patcher = patch(f'{SRC}.annotate_item', autospec=True)
        t.annotate_item = patcher.start()
        t.addCleanup(patcher.stop)
        patcher = patch('builtins.print', autospec=True)
        t.print = patcher.start()
        t.addCleanup(patcher.stop)

        t.conf = Mock(spec=['view'])
        t.args = Namespace(
            selector='a selector',
            text='a note',
            attrs='some attrs',
        )

    def test_note(t):
        Commands.note(t.conf, t.args)

        with t.subTest('the inputs reach the library beside the config'):
            t.annotate_item.assert_called_once_with(
                t.conf,
                t.datetime.now.return_value,
                selector='a selector',
                text='a note',
                attrs='some attrs',
            )

        with t.subTest('the clock is read in the configured zone'):
            t.time_zone.assert_called_with(t.conf)
            t.datetime.now.assert_called_with(t.time_zone.return_value)

        with t.subTest('and the command prints what comes back'):
            t.print.assert_called_once_with(t.annotate_item.return_value)


class CommandsSetLogLevelTests(TestCase):
    """Unit tests for battodo.cli.Commands.set_log_level."""

    @patch(f'{SRC}.log', autospec=True)
    def test_set_log_level(t, log):
        with t.subTest('the level is set on the logger'):
            conf = SimpleNamespace(loglevel=sentinel.loglevel)
            Commands.set_log_level(conf)
            log.setLevel.assert_called_once_with(sentinel.loglevel)

        log.reset_mock()

        with t.subTest('an unknown level raises a config refusal'):
            log.setLevel.side_effect = ValueError("Unknown level: 'bogus'")
            conf = SimpleNamespace(loglevel='bogus')
            with t.assertRaises(ValueError) as raised:
                Commands.set_log_level(conf)
            expected = (
                "unknown log level 'bogus'; "
                'choose one of CRITICAL, ERROR, WARNING, INFO, DEBUG'
            )
            t.assertEqual(str(raised.exception), expected)
