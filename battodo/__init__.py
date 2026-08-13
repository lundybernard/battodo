from dataclasses import dataclass

from .view import Config as ViewConfig


@dataclass
class GlobalConfig:
    view: ViewConfig
