from datetime import datetime
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from battodo.lib import get_completed, get_item, get_view

SRC = 'battodo.lib'
# The configured `~/todo` as every function resolves it.
SOURCE = Path.home() / 'todo'


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


class GetCompletedTests(TestCase):
    def setUp(t):
        for target in ('Digest', 'DigestView'):
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        t.digest = t.Digest.from_config.return_value

        t.now = Mock(spec=datetime)
        t.conf = Mock(spec=['view', 'format'])
        t.conf.format = 'text'

    def test_get_completed(t):
        with t.subTest('the configuration is decoded once, by the digest'):
            rendered = get_completed(t.conf, t.now)

            t.Digest.from_config.assert_called_once_with(t.conf, t.now)

        with t.subTest('which a human reads as a rendered digest'):
            t.DigestView.assert_called_once_with(t.digest)
            t.assertEqual(rendered, t.DigestView.return_value.text)

        with t.subTest('and a machine reads as the same digest, as JSON'):
            t.conf.format = 'json'

            t.assertEqual(get_completed(t.conf, t.now), t.digest.json)

        with t.subTest('which is serialized, never rendered'):
            t.DigestView.assert_called_once()

        with t.subTest('an unconfigured format is the human digest'):
            conf = Mock(spec=['view'])

            t.assertEqual(
                get_completed(conf, t.now), t.DigestView.return_value.text
            )


class GetItemTests(TestCase):
    def setUp(t):
        for target in ('build_item', 'build_item_json'):
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)

        t.now = Mock(spec=datetime)
        # spec models batconf: an option the user did not supply is
        # absent from the Configuration, not None.
        t.conf = Mock(spec=['view', 'selector', 'format'])
        t.conf.view = Mock(spec=['source_dir'])
        t.conf.view.source_dir = '~/todo'
        t.conf.selector = 'brush pile'
        t.conf.format = 'text'

    def test_get_item(t):
        with t.subTest('the human form is the default'):
            built = get_item(t.conf, t.now)

            args = t.build_item.call_args[0]
            t.assertEqual(args[0], SOURCE)
            t.assertEqual(args[1], 'brush pile')
            t.assertEqual(args[2], t.now)
            t.assertEqual(built, t.build_item.return_value)

        with t.subTest('json format is serialized instead'):
            t.conf.format = 'json'

            built = get_item(t.conf, t.now)

            t.assertEqual(t.build_item_json.call_args[0][1], 'brush pile')
            t.assertEqual(built, t.build_item_json.return_value)

        with t.subTest('which is serialized, never rendered'):
            t.build_item.assert_called_once()

        with t.subTest('an unconfigured format is the human form'):
            conf = Mock(spec=['view', 'selector'])
            conf.view.source_dir = '~/todo'
            conf.selector = 'brush pile'

            get_item(conf, t.now)

            t.assertEqual(t.build_item.call_count, 2)
