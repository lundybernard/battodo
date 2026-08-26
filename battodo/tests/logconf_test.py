import logging
from logging.config import dictConfig
from unittest import TestCase

from ..logconf import logging_config


class LoggingConfigTests(TestCase):
    """Unit tests for battodo.logconf.logging_config."""

    def setUp(t):
        # dictConfig rewrites the root logger, which outlives the test.
        root = logging.getLogger()
        handlers, level = list(root.handlers), root.level
        t.addCleanup(setattr, root, 'level', level)
        t.addCleanup(root.handlers.extend, handlers)
        t.addCleanup(root.handlers.clear)

    def test_logging_config(t):
        """Applying the config must not silence loggers it does not name.

        Libraries create their loggers at import time, before the CLI
        applies this config. dictConfig disables every pre-existing
        logger by default, which would swallow all third-party output.
        """
        third_party = logging.getLogger('battodo_test.third_party')

        dictConfig(logging_config)

        t.assertFalse(third_party.disabled)
