import logging
from logging.config import dictConfig
from unittest import TestCase

from ..logconf import logging_config


class LoggingConfigTests(TestCase):
    def test_logging_config(t):
        """Applying the config must not silence loggers it does not name.

        Libraries create their loggers at import time, before the CLI
        applies this config. dictConfig disables every pre-existing
        logger by default, which would swallow all third-party output.
        """
        third_party = logging.getLogger('battodo_test.third_party')

        dictConfig(logging_config)

        t.assertFalse(third_party.disabled)
