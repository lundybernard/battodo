from functools import cached_property
from os import environ
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

# Root of the config tree: the path every lookup is namespaced under, and
# so the prefix CLI arguments must carry to be resolvable as config.
# Named explicitly and passed to Configuration, so no lookup path ever
# depends on where a config class happens to be defined.
CONFIG_ROOT = 'battodo'

# The searched file names. The working directory holds the files of
# every tool, so the file there carries the application name; the user
# config directory is already named for the application.
PROJECT_FILE_NAME = 'battodo.toml'
USER_FILE_NAME = 'config.toml'
# The environment variable that names a file.
CONFIG_FILE_ENV_VAR = EnvSource().env_name('config_file', CONFIG_ROOT)


class ConfigFile:
    """The config file of a run, found by the ADR 0015 search order.

    Parameters
    ----------
    name : str or None
        A file the user named on the command line.
    config_env : str or None
        The environment to read from the file. The file names its own
        default when this is None.
    """

    def __init__(
        self,
        name: str | None = None,
        config_env: str | None = None,
    ) -> None:
        self._name = name
        self._config_env = config_env

    @cached_property
    def named(self) -> str | None:
        """The file the user named, or None when there is none."""
        return self._name or environ.get(CONFIG_FILE_ENV_VAR)

    @cached_property
    def candidates(self) -> tuple[Path, ...]:
        """The searched locations: working directory, then user config."""
        xdg_config_home = environ.get('XDG_CONFIG_HOME')
        user_config = (
            Path(xdg_config_home)
            if xdg_config_home
            else Path.home() / '.config'
        )
        return (
            Path.cwd() / PROJECT_FILE_NAME,
            user_config / CONFIG_ROOT / USER_FILE_NAME,
        )

    @cached_property
    def path(self) -> str | None:
        """The file to read, or None when there is none."""
        if self.named:
            return self.named
        for candidate in self.candidates:
            if candidate.is_file():
                return str(candidate)
        return None

    @cached_property
    def source(self) -> TomlSource | None:
        """A config source for the file, or None when there is none."""
        if not self.path:
            return None
        return TomlSource(
            self.path,
            config_env=self._config_env,
            # A file the user named must exist: an unreadable one is a
            # configuration error, not an empty result. A file the
            # search found exists already.
            missing_file_option='error' if self.named else 'ignore',
        )


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
        or ConfigFile(name=config_file_name, config_env=config_env).source,
    ]

    source_list = SourceList(config_sources)

    return Configuration(source_list, config_class, path=CONFIG_ROOT)
