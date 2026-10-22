from dataclasses import dataclass
from datetime import UTC
from os import environ
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, Mock, patch
from zoneinfo import ZoneInfoNotFoundError

from ..conf import (
    CONFIG_FILE_ENV_VAR,
    ConfigFile,
    Namespace,
    get_config,
    time_zone,
)

SRC = 'battodo.conf'


class GetConfigTests(TestCase):
    """Unit tests for battodo.conf.get_config."""

    def setUp(t) -> None:
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
    """Unit tests for battodo.conf.ConfigFile.

    Where the config file is, and the source that reads it.
    """

    def setUp(t):
        # Only the variables ConfigFile reads go: a cleared environment
        # also hides the variable that selects the active mutant.
        patcher = patch.dict(environ)
        patcher.start()
        t.addCleanup(patcher.stop)
        for name in (CONFIG_FILE_ENV_VAR, 'XDG_CONFIG_HOME'):
            environ.pop(name, None)

        t.cf = ConfigFile(
            # Default: name=None,
            # Default: config_env=None,
        )
        t.cf_named = ConfigFile('/given.toml')

    def test_init(t):
        ret = ConfigFile('/given.toml', config_env='another-env')
        # The inputs are stored raw.
        t.assertEqual(ret._name, '/given.toml')
        t.assertEqual(ret._config_env, 'another-env')

    def test_named(t):
        with t.subTest('nothing names a file'):
            ret = t.cf.named
            t.assertIsNone(ret)

        with t.subTest('the given name'):
            ret = t.cf_named.named
            t.assertEqual(ret, '/given.toml')

        with patch.dict('os.environ', {CONFIG_FILE_ENV_VAR: '/env.toml'}):
            with t.subTest('the environment names one'):
                ret = ConfigFile().named
                t.assertEqual(ret, '/env.toml')

            with t.subTest('the given name outranks the environment'):
                ret = ConfigFile('/given.toml').named
                t.assertEqual(ret, '/given.toml')

    @patch(f'{SRC}.Path', autospec=True)
    def test_candidates(t, Path_):
        # The module holds the name, so the name is what stands in:
        # patching an attribute of `pathlib.Path` reaches every user of
        # it in the process.
        Path_.side_effect = Path
        Path_.home.return_value = Path('/user')
        Path_.cwd.return_value = Path('/work')

        with t.subTest('the user config directory is the XDG default'):
            ret = t.cf.candidates

            t.assertEqual(
                ret,
                (
                    Path('/work/battodo.toml'),
                    Path('/user/.config/battodo/config.toml'),
                ),
            )

        with (
            t.subTest('XDG_CONFIG_HOME names the user config directory'),
            patch.dict('os.environ', {'XDG_CONFIG_HOME': '/xdg'}),
        ):
            ret = ConfigFile().candidates

            t.assertEqual(
                ret,
                (
                    Path('/work/battodo.toml'),
                    Path('/xdg/battodo/config.toml'),
                ),
            )

    def test_path(t):
        project, user = MagicMock(spec=Path), MagicMock(spec=Path)
        t.cf.candidates = (project, user)

        with t.subTest('no candidate exists'):
            project.is_file.return_value = False
            user.is_file.return_value = False

            ret = t.cf.path

            t.assertIsNone(ret)

        with t.subTest('the first candidate that exists wins'):
            user.is_file.return_value = True
            cf = ConfigFile()
            cf.candidates = (project, user)

            ret = cf.path

            t.assertEqual(ret, str(user))

        with t.subTest('a named file is never searched for'):
            project.is_file.reset_mock()
            user.is_file.reset_mock()

            ret = t.cf_named.path

            t.assertEqual(ret, '/given.toml')
            project.is_file.assert_not_called()
            user.is_file.assert_not_called()

    @patch(f'{SRC}.TomlSource', autospec=True)
    def test_source(t, TomlSource):
        with t.subTest('no file, no source'):
            t.cf.path = None

            ret = t.cf.source

            t.assertIsNone(ret)
            TomlSource.assert_not_called()

        with t.subTest('a file the search found is optional'):
            cf = ConfigFile()
            cf.path = '/work/battodo.toml'

            ret = cf.source

            t.assertEqual(ret, TomlSource.return_value)
            TomlSource.assert_called_with(
                '/work/battodo.toml',
                config_env=None,
                missing_file_option='ignore',
            )

        with t.subTest('a file the user named must exist'):
            cf = ConfigFile('/given.toml', config_env='test')

            ret = cf.source

            t.assertEqual(ret, TomlSource.return_value)
            TomlSource.assert_called_with(
                '/given.toml',
                config_env='test',
                missing_file_option='error',
            )


class TimeZoneTests(TestCase):
    """Unit tests for battodo.conf.time_zone."""

    ZoneInfo: MagicMock

    def setUp(t) -> None:
        patcher = patch(f'{SRC}.ZoneInfo', autospec=True)
        t.ZoneInfo = patcher.start()
        t.addCleanup(patcher.stop)

        t.conf = Mock(spec=['view'])
        t.conf.view = Mock(spec=['time_zone'])
        t.conf.view.time_zone = 'Another/Zone'

    def test_named(t) -> None:
        ret = time_zone(t.conf)

        t.assertIs(ret, t.ZoneInfo.return_value)
        t.ZoneInfo.assert_called_once_with('Another/Zone')

    @patch(f'{SRC}.datetime', autospec=True)
    def test_local(t, datetime: MagicMock) -> None:
        local = datetime.now.return_value.astimezone.return_value

        with t.subTest('an empty name reads the zone of the system'):
            t.conf.view.time_zone = ''

            ret = time_zone(t.conf)

            t.assertIs(ret, local.tzinfo)
            datetime.now.assert_called_once_with(UTC)

        with t.subTest('and so does a name the lookup cannot find'):
            t.conf.view = Mock(spec=[])
            ret = time_zone(t.conf)
            t.assertIs(ret, local.tzinfo)

    def test_unknown(t) -> None:
        refusals = {
            'a name the system has no zone for': ZoneInfoNotFoundError(
                'another-zone'
            ),
            'a name that is no zone key at all': ValueError('another-key'),
        }

        for name, error in refusals.items():
            with t.subTest(name):
                t.ZoneInfo.side_effect = error

                with t.assertRaises(ValueError) as caught:
                    time_zone(t.conf)

                t.assertEqual(
                    str(caught.exception),
                    "unknown time zone in view.time_zone: 'Another/Zone'",
                )
