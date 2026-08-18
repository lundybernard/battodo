from datetime import datetime
from unittest import TestCase
from unittest.mock import Mock, patch

from battodo.lib import get_view

SRC = 'battodo.lib'


class GetViewTests(TestCase):
    def setUp(t):
        for target in ('Selection', 'View'):
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        t.selection = t.Selection.from_config.return_value

        t.now = Mock(spec=datetime)
        # spec models batconf: an option the user did not supply is
        # absent from the Configuration, not None.
        t.conf = Mock(spec=['view', 'format'])
        t.conf.format = 'text'

    def test_get_view(t):
        with t.subTest('the configuration is decoded once, by the selection'):
            rendered = get_view(t.conf, t.now)

            t.Selection.from_config.assert_called_once_with(t.conf, t.now)

        with t.subTest('which a human reads as a rendered view'):
            t.View.assert_called_once_with(t.selection)
            t.assertEqual(rendered, t.View.return_value.text)

        with t.subTest('and a machine reads as the same selection, as JSON'):
            t.conf.format = 'json'

            t.assertEqual(get_view(t.conf, t.now), t.selection.json)

        with t.subTest('which is serialized, never rendered'):
            t.View.assert_called_once()

        with t.subTest('an unconfigured format is the human view'):
            conf = Mock(spec=['view'])

            t.assertEqual(get_view(conf, t.now), t.View.return_value.text)
