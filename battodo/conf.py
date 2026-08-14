from pathlib import Path

from batconf import (
    Configuration,
    EnvSource,
    Namespace,
    NamespaceSource,
    SourceList,
    TomlSource,
)
from batconf.types import ConfigP, SourceInterfaceP

from battodo import GlobalConfig

# Default config file path: look for config.toml in the working directory.
CONFIG_FILE_NAME = str(Path.cwd() / 'config.toml')

# Root of the config tree: the path every lookup is namespaced under, and
# so the prefix CLI arguments must carry to be resolvable as config.
# Named explicitly and passed to Configuration, so no lookup path ever
# depends on where a config class happens to be defined.
CONFIG_ROOT = 'battodo'


def get_config(
    # Known issue: https://github.com/python/mypy/issues/4536
    config_class: ConfigP = GlobalConfig,  # type: ignore
    cli_args: Namespace | None = None,
    config_file: SourceInterfaceP | None = None,
    config_file_name: str | None = None,
    config_env: str | None = None,
) -> Configuration:

    # Build a prioritized config source list
    config_sources = [
        NamespaceSource(cli_args) if cli_args else None,
        EnvSource(),
        config_file
        if config_file
        else TomlSource(
            config_file_name or CONFIG_FILE_NAME,
            config_env=config_env,
            # A file the caller named and we cannot read is a
            # configuration error, not an empty result. The default
            # file is a convenience, so its absence is unremarkable.
            missing_file_option='error' if config_file_name else 'ignore',
        ),
    ]

    source_list = SourceList(config_sources)

    return Configuration(source_list, config_class, path=CONFIG_ROOT)
