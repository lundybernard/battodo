from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from ..conf import (
    CONFIG_FILE_ENV_VAR,
    ConfigFile,
    Namespace,
    get_config,
)

SRC = 'battodo.conf'


class GetConfigTests(TestCase):
    def setUp(t):
        patches = [
            'ConfigFile',
        ]
        for target in patches:
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)

        @dataclass
        class ConfA:
            arg_1: str = 'dataclass_default_arg_1'
            arg_2: str = 'dataclass_default_arg_2'
            arg_3: str = 'dataclass_default_arg_3'

        @dataclass
        class ConfB:
            arg_1: str = 'dataclass_default_isodate'

        @dataclass
        class GlobalConfig:
            AModule: ConfA
            BModule: ConfB
            config_file: str = './GlobalConfig.toml'

        t.GlobalConfig = GlobalConfig

    @patch(f'{SRC}.EnvSource', autospec=True)
    def test_default_values(t, EnvSource):
        t.ConfigFile.return_value.source = None
        EnvSource.return_value = None

        CONF = get_config(t.GlobalConfig)

        t.assertEqual(CONF.AModule.arg_3, 'dataclass_default_arg_3')
        t.assertEqual(CONF.BModule.arg_1, 'dataclass_default_isodate')

    def test_arg_cli_args(t):
        """CLI values are addressed by their dotted config path"""
        cli_args = Namespace(**{'battodo.AModule.arg_1': 'cli_arg_1'})

        conf = get_config(t.GlobalConfig, cli_args=cli_args)

        t.assertEqual(conf.AModule.arg_1, 'cli_arg_1')

    @patch(f'{SRC}.TomlSource', autospec=True)
    def test_arg_config_file(t, TomlSource):
        """The given config_file parameter is used for attribute lookups"""
        config_file = TomlSource.return_value
        conf = get_config(t.GlobalConfig, config_file=config_file)

        t.assertEqual(conf.AModule.arg_1, config_file.get.return_value)
        config_file.get.assert_called_with('arg_1', path='battodo.AModule')

    @patch(f'{SRC}.TomlSource', autospec=True)
    def test_arg_config_file_name(t, TomlSource):
        """The given config_file_name names the file ConfigFile reads"""
        source = TomlSource.return_value
        t.ConfigFile.return_value.source = source
        config_file_name = './test.config.toml'

        conf = get_config(t.GlobalConfig, config_file_name=config_file_name)

        t.ConfigFile.assert_called_with(
            name=config_file_name,
            config_env=None,
        )
        t.assertEqual(conf.AModule.arg_1, source.get.return_value)

    def test_arg_config_env(t):
        """The given config_env name is passed to ConfigFile"""
        config_env = 'configuration file environment'
        get_config(t.GlobalConfig, config_env=config_env)

        t.ConfigFile.assert_called_with(name=None, config_env=config_env)

    @patch(f'{SRC}.EnvSource', autospec=True)
    def test__getattr__missing_attribute(t, EnvSource):
        t.ConfigFile.return_value.source = None
        EnvSource.return_value = None

        conf = get_config(t.GlobalConfig)
        with t.assertRaises(AttributeError):
            _ = conf._sir_not_appearing_in_this_film


class ConfigFileTests(TestCase):
    """Where the config file is, and the source that reads it."""

    def setUp(t):
        patcher = patch.dict('os.environ', {}, clear=True)
        patcher.start()
        t.addCleanup(patcher.stop)

        t.cf = ConfigFile(
            # Default: name=None,
            # Default: config_env=None,
        )
        t.cf_named = ConfigFile('/given.toml')

    def test_named(t):
        with t.subTest('nothing names a file'):
            t.assertIsNone(t.cf.named)

        with t.subTest('the given name'):
            t.assertEqual(t.cf_named.named, '/given.toml')

        with patch.dict('os.environ', {CONFIG_FILE_ENV_VAR: '/env.toml'}):
            with t.subTest('the environment names one'):
                t.assertEqual(ConfigFile().named, '/env.toml')

            with t.subTest('the given name outranks the environment'):
                t.assertEqual(ConfigFile('/given.toml').named, '/given.toml')

    @patch(f'{SRC}.Path.home', autospec=True, return_value=Path('/user'))
    @patch(f'{SRC}.Path.cwd', autospec=True, return_value=Path('/work'))
    def test_candidates(t, cwd, home):
        with t.subTest('the user config directory is the XDG default'):
            t.assertEqual(
                t.cf.candidates,
                (
                    Path('/work/battodo.toml'),
                    Path('/user/.config/battodo/config.toml'),
                ),
            )

        with (
            t.subTest('XDG_CONFIG_HOME names the user config directory'),
            patch.dict('os.environ', {'XDG_CONFIG_HOME': '/xdg'}),
        ):
            t.assertEqual(
                ConfigFile().candidates,
                (
                    Path('/work/battodo.toml'),
                    Path('/xdg/battodo/config.toml'),
                ),
            )

    @patch(f'{SRC}.Path.is_file', autospec=True)
    def test_path(t, is_file):
        project = Path('/work/battodo.toml')
        user = Path('/user/.config/battodo/config.toml')
        t.cf.candidates = (project, user)

        with t.subTest('no candidate exists'):
            is_file.return_value = False
            t.assertIsNone(t.cf.path)

        with t.subTest('the first candidate that exists wins'):
            is_file.reset_mock()
            is_file.side_effect = lambda candidate: candidate == user
            cf = ConfigFile()
            cf.candidates = (project, user)
            t.assertEqual(cf.path, str(user))

        with t.subTest('a named file is never searched for'):
            is_file.reset_mock()
            t.assertEqual(t.cf_named.path, '/given.toml')
            is_file.assert_not_called()

    @patch(f'{SRC}.TomlSource', autospec=True)
    def test_source(t, TomlSource):
        with t.subTest('no file, no source'):
            t.cf.path = None
            t.assertIsNone(t.cf.source)
            TomlSource.assert_not_called()

        with t.subTest('a file the search found is optional'):
            cf = ConfigFile()
            cf.path = '/work/battodo.toml'

            t.assertEqual(cf.source, TomlSource.return_value)
            TomlSource.assert_called_with(
                '/work/battodo.toml',
                config_env=None,
                missing_file_option='ignore',
            )

        with t.subTest('a file the user named must exist'):
            cf = ConfigFile('/given.toml', config_env='test')

            t.assertEqual(cf.source, TomlSource.return_value)
            TomlSource.assert_called_with(
                '/given.toml',
                config_env='test',
                missing_file_option='error',
            )


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
