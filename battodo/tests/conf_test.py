from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from ..conf import (
    CONFIG_FILE_NAME,
    Namespace,
    get_config,
)

SRC = 'battodo.conf'


class GetConfigTests(TestCase):
    def setUp(t):
        patches = [
            'TomlSource',
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
        t.TomlSource.return_value = None
        EnvSource.return_value = None

        CONF = get_config(t.GlobalConfig)

        t.assertEqual(CONF.AModule.arg_3, 'dataclass_default_arg_3')
        t.assertEqual(CONF.BModule.arg_1, 'dataclass_default_isodate')

    def test_arg_cli_args(t):
        """CLI values are addressed by their dotted config path"""
        cli_args = Namespace(**{'battodo.AModule.arg_1': 'cli_arg_1'})

        conf = get_config(t.GlobalConfig, cli_args=cli_args)

        t.assertEqual(conf.AModule.arg_1, 'cli_arg_1')

    def test_arg_config_file(t):
        """The given config_file parameter is used for attribute lookups"""
        config_file = t.TomlSource.return_value
        conf = get_config(t.GlobalConfig, config_file=config_file)

        t.assertEqual(conf.AModule.arg_1, config_file.get.return_value)
        config_file.get.assert_called_with('arg_1', path='battodo.AModule')

    def test_arg_config_file_name(t):
        """The given config_file_name is passed to the TomlSource constructor"""
        config_file_name = './test.config.toml'
        get_config(t.GlobalConfig, config_file_name=config_file_name)
        t.TomlSource.assert_called_with(
            config_file_name,
            config_env=None,
            missing_file_option='error',
        )

    def test_arg_config_env(t):
        """The given config_env name is passed to the TomlSource constructor"""
        config_env = 'configuration file environment'
        get_config(t.GlobalConfig, config_env=config_env)
        t.TomlSource.assert_called_with(
            CONFIG_FILE_NAME,
            config_env=config_env,
            missing_file_option='ignore',
        )

    @patch(f'{SRC}.EnvSource', autospec=True)
    def test__getattr__missing_attribute(t, EnvSource):
        t.TomlSource.return_value = None
        EnvSource.return_value = None

        conf = get_config(t.GlobalConfig)
        with t.assertRaises(AttributeError):
            _ = conf._sir_not_appearing_in_this_film


class ConfigFileTests(TestCase):
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
        # would answer first and hide whatever the file says.
        patcher = patch.dict('os.environ', clear=True)
        patcher.start()
        t.addCleanup(patcher.stop)

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

        with (
            t.subTest('the default file is optional'),
            patch(f'{SRC}.CONFIG_FILE_NAME', missing),
        ):
            conf = get_config()

            t.assertEqual(conf.view.source_dir, '~/todo')
