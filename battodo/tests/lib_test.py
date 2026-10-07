from datetime import datetime
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch, sentinel

from ..lib import (
    add_item,
    backfill_items,
    complete_item,
    get_completed,
    get_item,
    get_view,
    scratch_item,
    update_item,
)

SRC = 'battodo.lib'
# The configured `~/a-source-dir` as every function resolves it.
SOURCE = Path.home() / 'a-source-dir'


class GetViewTests(TestCase):
    """Unit tests for battodo.lib.get_view."""

    def setUp(t):
        for target in ('Selection', 'View'):
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        t.selection = t.Selection.from_config.return_value

        t.now = sentinel.now
        # spec models batconf: an option the user did not supply is
        # absent from the Configuration, not None.
        t.conf = Mock(spec=['view', 'format'])
        t.conf.format = 'text'

    def test_selection(t):
        get_view(t.conf, t.now)
        # The configuration is decoded once, by the selection.
        t.Selection.from_config.assert_called_once_with(t.conf, t.now)

    def test_text(t):
        rendered = get_view(t.conf, t.now)
        t.View.assert_called_once_with(t.selection)
        t.assertEqual(rendered, t.View.return_value.text)

    @patch(f'{SRC}.SelectionJsonView', autospec=True)
    def test_json(t, selection_json_view):
        t.conf.format = 'json'

        rendered = get_view(t.conf, t.now)

        selection_json_view.assert_called_once_with(t.selection)
        t.assertEqual(rendered, selection_json_view.return_value.json)
        # The JSON view serializes the selection; the text view is not
        # built.
        t.View.assert_not_called()

    def test_unconfigured_format(t):
        conf = Mock(spec=['view'])
        rendered = get_view(conf, t.now)
        t.assertEqual(rendered, t.View.return_value.text)


class GetCompletedTests(TestCase):
    """Unit tests for battodo.lib.get_completed."""

    def setUp(t):
        for target in ('Digest', 'DigestView'):
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        t.digest = t.Digest.from_config.return_value

        t.now = sentinel.now
        t.conf = Mock(spec=['view', 'format'])
        t.conf.format = 'text'

    def test_digest(t):
        get_completed(t.conf, t.now)
        # The configuration is decoded once, by the digest.
        t.Digest.from_config.assert_called_once_with(t.conf, t.now)

    def test_text(t):
        rendered = get_completed(t.conf, t.now)
        t.DigestView.assert_called_once_with(t.digest)
        t.assertEqual(rendered, t.DigestView.return_value.text)

    @patch(f'{SRC}.DigestJsonView', autospec=True)
    def test_json(t, digest_json_view):
        t.conf.format = 'json'

        rendered = get_completed(t.conf, t.now)

        digest_json_view.assert_called_once_with(t.digest)
        t.assertEqual(rendered, digest_json_view.return_value.json)
        # The JSON view serializes the digest; the text view is not built.
        t.DigestView.assert_not_called()

    def test_unconfigured_format(t):
        conf = Mock(spec=['view'])
        rendered = get_completed(conf, t.now)
        t.assertEqual(rendered, t.DigestView.return_value.text)


class GetItemTests(TestCase):
    """Unit tests for battodo.lib.get_item."""

    def setUp(t):
        patches = ['Item', 'ItemView']
        for target in patches:
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        t.item = t.Item.from_config.return_value

        t.now = sentinel.now
        # spec models batconf: an option the user did not supply is
        # absent from the Configuration, not None.
        t.conf = Mock(spec=['format'])
        t.conf.format = 'text'

    def test_item(t):
        get_item(t.conf, t.now)
        # The configuration is decoded once, by the item.
        t.Item.from_config.assert_called_once_with(t.conf, t.now)

    def test_text(t):
        rendered = get_item(t.conf, t.now)
        t.ItemView.assert_called_once_with(t.item)
        t.assertEqual(rendered, t.ItemView.return_value.text)

    @patch(f'{SRC}.ItemJsonView', autospec=True)
    def test_json(t, item_json_view):
        t.conf.format = 'json'

        rendered = get_item(t.conf, t.now)

        item_json_view.assert_called_once_with(t.item)
        t.assertEqual(rendered, item_json_view.return_value.json)
        # The JSON view serializes the item; the text view is not built.
        t.ItemView.assert_not_called()

    def test_unconfigured_format(t):
        conf = Mock(spec=[])
        rendered = get_item(conf, t.now)
        t.assertEqual(rendered, t.ItemView.return_value.text)


class AddItemTests(TestCase):
    """Unit tests for battodo.lib.add_item."""

    def setUp(t):
        patches = ['Addition', 'SubtaskAddition', 'Task']
        for target in patches:
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        t.addition = t.Addition.return_value
        t.addition.path = Path('~/a-source-dir/a-list.md')
        t.addition.entry = '- [ ] A task title [P:4] [ID:ab12cd]'

        t.now = Mock(spec=datetime)
        t.today = t.now.date.return_value
        # spec models batconf: an argument the user did not supply is
        # absent from the Configuration, not None.
        t.conf = Mock(spec=['view', 'list', 'title', 'priority', 'due'])
        t.conf.view = Mock(spec=['source_dir'])
        t.conf.view.source_dir = '~/a-source-dir'
        t.conf.list = 'a-list'
        t.conf.title = 'A task title'
        t.conf.priority = '4'
        t.conf.due = '2026-09-01'

    def test_forwarded(t):
        add_item(t.conf, t.now)
        t.Addition.assert_called_once_with(
            SOURCE,
            'a-list',
            'A task title',
            {'P': '4', 'DUE': '2026-09-01'},
            t.today,
        )

    def test_written(t):
        add_item(t.conf, t.now)
        t.addition.write.assert_called_once_with()

    def test_result(t):
        written = add_item(t.conf, t.now)
        # A P-less add ranks near 0 and will not show in a view, so
        # this is the only confirmation of the write.
        t.assertEqual(written, f'{t.addition.entry}\n{t.addition.path}')

    def test_no_fields(t):
        conf = Mock(spec=['view', 'list', 'title'])
        conf.view = Mock(spec=['source_dir'])
        conf.view.source_dir = '~/a-source-dir'
        conf.list = 'a-list'
        conf.title = 'A task title'

        add_item(conf, t.now)

        t.assertEqual(t.Addition.call_args[0][3], {})

    def test_subtask(t):
        conf = Mock(spec=['view', 'list', 'title', 'parent', 'loe'])
        conf.view = Mock(spec=['source_dir'])
        conf.view.source_dir = '~/a-source-dir'
        conf.list = 'a-list'
        conf.title = 'A subtask title'
        conf.parent = '9o71lx'
        conf.loe = '2'
        addition = t.SubtaskAddition.return_value
        addition.path = Path('~/a-source-dir/a-list.md')
        addition.entry = '  - [ ] A subtask title [LOE:2] [ID:cd34ef]'

        written = add_item(conf, t.now)

        with t.subTest('a parent sends the add to a subtask'):
            t.Addition.assert_not_called()
            t.SubtaskAddition.assert_called_once_with(
                t.Task.return_value,
                'a-list',
                'A subtask title',
                {'LOE': '2'},
            )

        with t.subTest('the parent is the task its selector names'):
            t.Task.assert_called_once_with(SOURCE, '9o71lx', t.today)

        with t.subTest('the subtask is written'):
            addition.write.assert_called_once_with()

        with t.subTest('the subtask line and its file come back'):
            t.assertEqual(written, f'{addition.entry}\n{addition.path}')


class UpdateItemTests(TestCase):
    """Unit tests for battodo.lib.update_item."""

    def setUp(t):
        patches = ['Update', 'Task']
        for target in patches:
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        t.update = t.Update.return_value
        t.update.path = Path('~/a-source-dir/a-list.md')
        t.update.entry = '- [ ] A task title [P:4] [ID:ab12cd]'

        t.now = Mock(spec=datetime)
        t.today = t.now.date.return_value
        # spec models batconf: an option the user did not supply is
        # absent from the Configuration, not None.
        t.conf = Mock(spec=['view', 'selector', 'priority', 'due', 'title'])
        t.conf.view = Mock(spec=['source_dir'])
        t.conf.view.source_dir = '~/a-source-dir'
        t.conf.selector = 'a selector'
        t.conf.priority = '4'
        t.conf.due = '2026-09-01'
        t.conf.title = 'A task title'

    def test_forwarded(t):
        update_item(t.conf, t.now)

        t.Task.assert_called_once_with(SOURCE, 'a selector', t.today)
        t.Update.assert_called_once_with(
            t.Task.return_value,
            {'P': '4', 'DUE': '2026-09-01'},
            title='A task title',
        )

    def test_written(t):
        update_item(t.conf, t.now)
        t.update.write.assert_called_once_with()

    def test_result(t):
        written = update_item(t.conf, t.now)
        t.assertEqual(written, f'{t.update.entry}\n{t.update.path}')

    def test_option_left_off(t):
        conf = Mock(spec=['view', 'selector', 'tags'])
        conf.view = Mock(spec=['source_dir'])
        conf.view.source_dir = '~/a-source-dir'
        conf.selector = 'a selector'
        conf.tags = 'a-tag,another-tag'

        update_item(conf, t.now)

        # An option left off names no change to that field.
        args, kwargs = t.Update.call_args
        t.assertEqual(args[1], {'TAGS': 'a-tag,another-tag'})
        t.assertIsNone(kwargs['title'])


class CompleteItemTests(TestCase):
    """Unit tests for battodo.lib.complete_item."""

    def setUp(t):
        patches = ['Task', 'Completion']
        for target in patches:
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        # autospec builds `from_config` from its signature, so its
        # return value carries no spec. The instance mock does, so the
        # classmethod is pointed at that.
        t.task = t.Task.return_value
        t.Task.from_config.return_value = t.task
        t.completion = t.Completion.return_value
        t.completion.entries = []

        t.now = sentinel.now
        # The task decodes the configuration, so this call reads no
        # value off it. The spec still names what a `done` carries.
        t.conf = Mock(spec=['view', 'selector'])

    def test_result(t):
        # Completing the last open child completes its parent too, so
        # one call can log more than one entry.
        t.completion.entries = [
            '2026-08-08 | a-list | DONE | A parent > A child',
            '2026-08-08 | a-list | DONE | A parent',
        ]

        logged = complete_item(t.conf, t.now)

        t.assertEqual(
            logged,
            '2026-08-08 | a-list | DONE | A parent > A child\n'
            '2026-08-08 | a-list | DONE | A parent',
        )

    def test_task(t):
        complete_item(t.conf, t.now)

        with t.subTest('the configuration is decoded once, by the task'):
            t.Task.from_config.assert_called_once_with(t.conf, t.now)

        with t.subTest('which the completion is built on'):
            t.Completion.assert_called_once_with(t.task)

    def test_written(t):
        complete_item(t.conf, t.now)
        t.completion.write.assert_called_once_with()

    def test_nothing_logged(t):
        logged = complete_item(t.conf, t.now)
        t.assertEqual(logged, 'checked off')


class ScratchItemTests(TestCase):
    """Unit tests for battodo.lib.scratch_item."""

    def setUp(t):
        patches = ['Scratch', 'Task']
        for target in patches:
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        t.scratch = t.Scratch.return_value
        t.scratch.entries = []

        t.now = Mock(spec=datetime)
        t.today = t.now.date.return_value
        t.conf = Mock(spec=['view', 'selector'])
        t.conf.view = Mock(spec=['source_dir'])
        t.conf.view.source_dir = '~/a-source-dir'
        t.conf.selector = 'a selector'

    def test_result(t):
        t.scratch.entries = [
            '2026-08-08 | a-list | SCRATCHED | A parent > A child',
        ]

        logged = scratch_item(t.conf, t.now)

        t.assertEqual(
            logged,
            '2026-08-08 | a-list | SCRATCHED | A parent > A child',
        )

    def test_forwarded(t):
        scratch_item(t.conf, t.now)

        t.Task.assert_called_once_with(SOURCE, 'a selector', t.today)
        t.Scratch.assert_called_once_with(t.Task.return_value)

    def test_written(t):
        scratch_item(t.conf, t.now)
        t.scratch.write.assert_called_once_with()

    def test_nothing_logged(t):
        logged = scratch_item(t.conf, t.now)
        t.assertEqual(logged, 'dropped')


class BackfillItemsTests(TestCase):
    """Unit tests for battodo.lib.backfill_items."""

    def setUp(t):
        patches = ['Backfill']
        for target in patches:
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        t.backfill = t.Backfill.return_value
        t.backfill.lists = []

        t.now = Mock(spec=datetime)
        t.today = t.now.date.return_value
        t.conf = Mock(spec=['view'])
        t.conf.view = Mock(spec=['source_dir'])
        t.conf.view.source_dir = '~/a-source-dir'

    def test_result(t):
        t.backfill.lists = [
            stamped('a-list.md', 2),
            stamped('another-list.md', 1),
        ]

        ret = backfill_items(t.conf, t.now)

        # A count per changed list, in name order.
        t.assertEqual(ret, 'a-list.md: stamped 2\nanother-list.md: stamped 1')

    def test_forwarded(t):
        backfill_items(t.conf, t.now)
        t.Backfill.assert_called_once_with(SOURCE, t.today)

    def test_written(t):
        backfill_items(t.conf, t.now)
        t.backfill.write.assert_called_once_with()

    def test_nothing_stamped(t):
        ret = backfill_items(t.conf, t.now)
        t.assertEqual(ret, 'nothing to backfill')


def stamped(name: str, count: int) -> Mock:
    """A list backfill: its file, and the tasks it stamps."""
    backfill = Mock(spec=['path', 'tasks'])
    backfill.path = Path(name)
    backfill.tasks = [sentinel.task] * count
    return backfill
