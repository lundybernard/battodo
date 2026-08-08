from dataclasses import dataclass

from .example import Config
from .view import Config as ViewConfig


@dataclass
class GlobalConfig:
    # example module with configuration dataclass
    example: Config
    view: ViewConfig
