from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo
from functools import cached_property
from os import environ
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from batconf import (
    Configuration,
    EnvSource,
    Namespace,
    NamespaceSource,
    SourceList,
    TomlSource,
)
from batconf.types import ConfigP, SourceInterfaceP

from battodo.rank import DEFAULT_DUE_CURVE
from battodo.view import TOP_N

# Every lookup path starts here, so a CLI argument carries this prefix to
# resolve as config.
CONFIG_ROOT = 'battodo'

# The working directory holds the files of every tool, so the file there
# carries the application name. The user config directory already names
# the application.
PROJECT_FILE_NAME = 'battodo.toml'
USER_FILE_NAME = 'config.toml'
CONFIG_FILE_ENV_VAR = EnvSource().env_name('config_file', CONFIG_ROOT)

ZONE_ERROR = 'unknown time zone in view.time_zone'


@dataclass
class ViewConfig:
    """What a view reads, and how much of it a view shows.

    One source for now; `source_dir` becomes a list of sources once
    ADR 0004 settles the discovery/merge semantics of composable
    sources.

    Every value is a string: the environment source carries nothing
    else, so a consumer decodes what it needs. `top` is read as an
    integer by the view command, and `all` as `true` or `false`:
    `true` shows every item, as `view --all` does. `rank_due_curve` is
    read as the `days:factor` points of the due-date curve (ADR 0026).
    `time_zone` names the zone of the clock; empty means the system
    local zone. `windows` is read as the hour windows of each category,
    and `always_active` as the names no window shuts (ADR 0018). Empty
    schedules nothing, so every category shows.
    """

    source_dir: str = '~/todo'
    top: str = str(TOP_N)
    all: str = 'false'
    rank_due_curve: str = DEFAULT_DUE_CURVE
    time_zone: str = ''
    windows: str = ''
    always_active: str = ''


@dataclass
class GlobalConfig:
    """What the application reads outside any one command.

    `loglevel` names a level for the standard library logger. Its
    default silences every record below an error. `format` names the
    form of the output: text for a terminal, json for an agent.
    """

    view: ViewConfig
    loglevel: str = 'ERROR'
    format: str = 'text'


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
    # mypy rejects the class default, because a dataclass types
    # `__dataclass_fields__` as `dict[str, Field[Any]]` and `ConfigP` names
    # `dict[str, FieldP]`.
    # https://github.com/python/mypy/issues/4536
    config_class: ConfigP = GlobalConfig,  # type: ignore
    cli_args: Namespace | None = None,
    config_file: SourceInterfaceP | None = None,
    config_file_name: str | None = None,
    config_env: str | None = None,
) -> Configuration:

    # The list puts the highest-priority source first.
    config_sources = [
        NamespaceSource(cli_args) if cli_args else None,
        EnvSource(),
        config_file
        or ConfigFile(name=config_file_name, config_env=config_env).source,
    ]

    source_list = SourceList(config_sources)

    return Configuration(source_list, config_class, path=CONFIG_ROOT)


def time_zone(conf: Configuration) -> tzinfo:
    """The zone the clock of a run reads: the configured one, or local.

    The lookup raises AttributeError for a zone that is absent or empty.

    Raises
    ------
    ValueError
        The configured name is not a zone the system knows.
    """
    try:
        name = conf.view.time_zone
    except AttributeError:
        local = datetime.now(UTC).astimezone()
        # The type argument of cast() has no run-time effect.
        return cast('tzinfo', local.tzinfo)  # pragma: no mutate
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exp:
        raise ValueError(f'{ZONE_ERROR}: {name!r}') from exp
