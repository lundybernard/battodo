"""Golden test for a run configured by a file the CLI finds itself.

`view` runs with no source directory in the environment and no
`--conf` argument, so the config file in the user config directory is
the only place the source can come from. The output is the same
golden the environment-configured run produces.
"""

from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from battodo.cli import TZ

from .cli_runner import run_cli

DATA = Path(__file__).parent / 'data'
TODO_DIR = DATA / 'todo'
GOLDEN_DIR = DATA / 'golden'

# The instant every fixture date is relative to.
FROZEN = datetime(2026, 8, 5, 10, 30, tzinfo=TZ)
# The layout reads the terminal width from COLUMNS.
WIDTH = '80'


class UserConfigFileTests(TestCase):
    maxDiff = None

    def setUp(t) -> None:
        # Pin the clock: the rendered output depends on it.
        patcher = patch('battodo.cli.datetime', autospec=True)
        t.datetime = patcher.start()
        t.addCleanup(patcher.stop)
        t.datetime.now.return_value = FROZEN

        home = TemporaryDirectory()
        t.addCleanup(home.cleanup)
        t.home = Path(home.name)
        t.config_home = t.home / '.config'
        config_file = t.config_home / 'battodo' / 'config.toml'
        config_file.parent.mkdir(parents=True)
        config_file.write_text(
            '[batconf]\n'
            'default_env = "test"\n'
            '\n'
            '[test.battodo.view]\n'
            f'source_dir = "{TODO_DIR}"\n'
        )

    def test_view(t) -> None:
        """The view is built from the source the config file names."""
        env = {
            'COLUMNS': WIDTH,
            'HOME': str(t.home),
            'XDG_CONFIG_HOME': str(t.config_home),
        }
        out, err, code = run_cli(['view'], env)

        t.assertEqual(err, '')
        t.assertEqual(code, 0)
        t.assertEqual(
            out,
            (GOLDEN_DIR / 'view.txt').read_text(encoding='utf-8'),
        )
