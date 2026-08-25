"""Contract test for the seam between the parser and the configuration.

Parsed CLI arguments must resolve through the real `Configuration`.
The contract only exists when the real parser and the real
`get_config` meet, so both are real here; the config file is the one
dependency stood in for.
"""

from unittest import TestCase
from unittest.mock import patch

from battodo.cli import DEFAULT_PERIOD, argparser, get_config
from battodo.view import TOP_N


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

    def setUp(t):
        # The environment source outranks the schema defaults: an
        # ambient BATTODO_* var would answer before them.
        patcher = patch.dict('os.environ', clear=True)
        patcher.start()
        t.addCleanup(patcher.stop)

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

        with t.subTest('a count reaches the command as a string'):
            t.assertEqual(t.resolve(['view', '--top', '2']).view.top, '2')

        with t.subTest('and the schema answers when no source does'):
            t.assertEqual(t.resolve(['view']).view.top, str(TOP_N))

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
            t.assertEqual(t.resolve(['completed', 'month']).period, 'month')
            t.assertEqual(t.resolve(['completed']).period, DEFAULT_PERIOD)
