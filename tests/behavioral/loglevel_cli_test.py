"""The log level a run applies, read back off the logger.

The entry point runs in process, so the level it set is readable after
it exits. The command line carries no subcommand: the run prints help
and reads nothing else, so only the level is under test.
"""

from logging import DEBUG, ERROR, INFO, getLogger
from unittest import TestCase

from .cli_runner import run_cli

LEVEL_VAR = 'BATTODO_LOGLEVEL'


class LogLevelTests(TestCase):
    """The level the entry point leaves on the logger."""

    def setUp(t) -> None:
        log = getLogger('root')
        t.addCleanup(log.setLevel, log.level)

    def test_log_level(t) -> None:
        cases = {
            'the built-in default answers when nothing else does': (
                [],
                {},
                ERROR,
            ),
            'the environment names the level': (
                [],
                {LEVEL_VAR: 'DEBUG'},
                DEBUG,
            ),
            'and a flag outranks the environment': (
                ['--verbose'],
                {LEVEL_VAR: 'DEBUG'},
                INFO,
            ),
        }

        for name, (args, env, expected) in cases.items():
            with t.subTest(name):
                run_cli(args, env)
                t.assertEqual(getLogger('root').level, expected)
