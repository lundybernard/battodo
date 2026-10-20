"""An environment for a test run that no battodo setting of the host reaches.

The host's other variables stay. A cleared environment also hides the
variable that tells mutmut which mutant is active, so no test under it
runs against a mutant.

Not named `*_test.py`, so the discovery pattern imports it without
collecting it.
"""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from os import environ
from unittest.mock import patch
from zoneinfo import ZoneInfo

# The zone of every fixture clock. A named zone, not a fixed offset, so
# a fixture date keeps its local day across a daylight-saving change.
TZ = ZoneInfo('America/Los_Angeles')

# The variables a run reads its configuration from: the environment
# source of the configuration, and the user config directory.
CONFIG_PREFIX = 'BATTODO_'
CONFIG_HOME = 'XDG_CONFIG_HOME'


@contextmanager
def isolate_environ(values: Mapping[str, str] | None = None) -> Iterator[None]:
    """Remove the battodo variables of the host, then set `values`.

    Every change is undone on exit.
    """
    with patch.dict(environ):
        for name in list(environ):
            if name.startswith(CONFIG_PREFIX) or name == CONFIG_HOME:
                del environ[name]
        environ.update(values or {})
        yield
