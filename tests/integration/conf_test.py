"""Contract tests for the config file search, against real files.

Real files in real directories, read through a real `TomlSource`. The
search order of ADR 0015 is asserted by the value that answers
`view.source_dir`: each config file names a different one.
"""

from os import chdir, environ, getcwd
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from battodo.conf import get_config

SRC = 'battodo.conf'

ENV_VAR = 'BATTODO_CONFIG_FILE'


def write_config(path: Path, source_dir: str) -> str:
    """Write a config file at `path` that names `source_dir`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '[batconf]\n'
        'default_env = "test"\n'
        '\n'
        '[test.battodo.view]\n'
        f'source_dir = "{source_dir}"\n'
    )
    return str(path)


class ConfigFileSearchTests(TestCase):
    """An empty working directory and an empty user config directory."""

    def setUp(t) -> None:
        tmp = TemporaryDirectory()
        t.addCleanup(tmp.cleanup)
        t.root = Path(tmp.name)
        t.project = t.root / 'project'
        t.project.mkdir()
        t.config_home = t.root / 'config'

        # The search reads the working directory and the environment.
        t.addCleanup(chdir, getcwd())
        chdir(t.project)
        patcher = patch.dict(
            environ,
            {'XDG_CONFIG_HOME': str(t.config_home)},
            clear=True,
        )
        patcher.start()
        t.addCleanup(patcher.stop)

    def test_get_config(t) -> None:
        """Each case adds a location above the last one."""
        with t.subTest('no file: the dataclass default answers'):
            t.assertEqual(get_config().view.source_dir, '~/todo')

        write_config(t.config_home / 'battodo' / 'config.toml', '/user')
        with t.subTest('the user config file'):
            t.assertEqual(get_config().view.source_dir, '/user')

        write_config(t.project / 'battodo.toml', '/project')
        with t.subTest('the working directory outranks the user file'):
            t.assertEqual(get_config().view.source_dir, '/project')

        named = write_config(t.root / 'named.toml', '/named')
        with (
            t.subTest('the environment names a file above both'),
            patch.dict(environ, {ENV_VAR: named}),
        ):
            t.assertEqual(get_config().view.source_dir, '/named')

        given = write_config(t.root / 'given.toml', '/given')
        with (
            t.subTest('the given file outranks the environment'),
            patch.dict(environ, {ENV_VAR: named}),
        ):
            conf = get_config(config_file_name=given)
            t.assertEqual(conf.view.source_dir, '/given')

        with t.subTest('a file the user names must exist'):
            conf = get_config(config_file_name=str(t.root / 'gone.toml'))
            with t.assertRaises(FileNotFoundError):
                _ = conf.view.source_dir


class TomlBackendTests(TestCase):
    """The config file is read for real: no mocked TomlSource.

    Parsing TOML needs a backend batconf only declares under its
    optional `toml` extra on python < 3.11, and the failure is lazy —
    importing TomlSource succeeds, only the first read fails. Mocked
    tests cannot see that, so this one parses an actual file.
    """

    def setUp(t):
        tmp = TemporaryDirectory()
        t.addCleanup(tmp.cleanup)
        t.config_file = Path(tmp.name) / 'config.toml'

        # EnvSource outranks the config file: an ambient BATTODO_* var
        # would answer first and hide whatever the file says. The
        # search reads the environment too, so the user config
        # directory is the empty temporary one.
        patcher = patch.dict(
            'os.environ',
            {'XDG_CONFIG_HOME': tmp.name},
            clear=True,
        )
        patcher.start()
        t.addCleanup(patcher.stop)

        # The searched working directory is the temporary one as well.
        cwd = patch(
            f'{SRC}.Path.cwd',
            autospec=True,
            return_value=Path(tmp.name),
        )
        cwd.start()
        t.addCleanup(cwd.stop)

    def test_config_file(t):
        t.config_file.write_text(
            '[batconf]\n'
            'default_env = "test"\n'
            '\n'
            '[test.battodo.view]\n'
            'source_dir = "~/todo-from-config-file"\n'
        )

        conf = get_config(config_file_name=str(t.config_file))

        t.assertEqual(conf.view.source_dir, '~/todo-from-config-file')

    def test_missing_config_file(t):
        missing = str(t.config_file)  # setUp never writes it

        with t.subTest('an explicitly named file must exist'):
            conf = get_config(config_file_name=missing)
            with t.assertRaises(FileNotFoundError):
                _ = conf.view.source_dir

        with t.subTest('the searched locations are optional'):
            conf = get_config()

            t.assertEqual(conf.view.source_dir, '~/todo')
