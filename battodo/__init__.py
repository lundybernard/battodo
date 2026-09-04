from dataclasses import dataclass
from zoneinfo import ZoneInfo

from .view import TOP_N

# The host clock runs UTC while todos are anchored to the user's local
# day, so the zone is named rather than a fixed offset.
TZ = ZoneInfo('America/Los_Angeles')


@dataclass
class ViewConfig:
    """What a view reads, and how much of it a view shows.

    One source for now; R6 turns `source_dir` into a list of sources
    once the discovery/merge semantics in ADR 0004 are settled.

    Every value is a string: the environment source carries nothing
    else, so a consumer decodes what it needs. `top` is read as an
    integer by the view command.
    """

    source_dir: str = '~/todo'
    top: str = str(TOP_N)


@dataclass
class GlobalConfig:
    view: ViewConfig
