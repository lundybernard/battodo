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

    def test_json(t):
        t.conf.format = 'json'

        rendered = get_view(t.conf, t.now)

        t.assertEqual(rendered, t.selection.json)
        # The selection serializes itself; nothing renders it.
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

    def test_json(t):
        t.conf.format = 'json'

        rendered = get_completed(t.conf, t.now)

        t.assertEqual(rendered, t.digest.json)
        # The digest serializes itself; nothing renders it.
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

    def test_json(t):
        t.conf.format = 'json'

        rendered = get_item(t.conf, t.now)

        t.assertEqual(rendered, t.item.json)
        # The item serializes itself; nothing renders it.
        t.ItemView.assert_not_called()

    def test_unconfigured_format(t):
        conf = Mock(spec=[])
        rendered = get_item(conf, t.now)
        t.assertEqual(rendered, t.ItemView.return_value.text)


class AddItemTests(TestCase):
    """Unit tests for battodo.lib.add_item."""

    def setUp(t):
        patches = ['add_task', 'add_subtask', 'Task']
        for target in patches:
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)

        t.path = Path('~/a-source-dir/a-list.md')
        t.entry = '- [ ] A task title [P:4] [ADDED:2026-08-08] [ID:ab12cd]'
        t.add_task.return_value = (t.path, t.entry)
        t.add_subtask.return_value = (t.path, t.entry)

        t.now = Mock(spec=datetime)
        t.today = t.now.date.return_value
        # spec models batconf: an argument the user did not supply is
        # absent from the Configuration, not None.
        t.conf = Mock(spec=['view', 'list', 'title', 'priority', 'due'])
        t.conf.view = Mock(spec=['source_dir'])
        t.conf.view.source_dir = '~/a-source-dir'
        t.conf.list = 'chores'
        t.conf.title = 'A task title'
        t.conf.priority = '4'
        t.conf.due = '2026-09-01'

    def test_forwarded(t):
        add_item(t.conf, t.now)

        args = t.add_task.call_args[0]
        t.assertEqual(args[0], SOURCE)
        t.assertEqual(args[1], 'chores')
        t.assertEqual(args[2], 'A task title')
        t.assertEqual(args[3], {'P': '4', 'DUE': '2026-09-01'})
        t.assertEqual(args[4], t.today)

    def test_result(t):
        written = add_item(t.conf, t.now)

        # A P-less add ranks near 0 and will not show in a view, so
        # this is the only confirmation of the write.
        t.assertEqual(written, f'{t.entry}\n{t.path}')

    def test_no_fields(t):
        conf = Mock(spec=['view', 'list', 'title'])
        conf.view = Mock(spec=['source_dir'])
        conf.view.source_dir = '~/a-source-dir'
        conf.list = 'chores'
        conf.title = 'A task title'

        add_item(conf, t.now)

        t.assertEqual(t.add_task.call_args[0][3], {})

    def test_subtask(t):
        conf = Mock(spec=['view', 'list', 'title', 'parent', 'loe'])
        conf.view = Mock(spec=['source_dir'])
        conf.view.source_dir = '~/a-source-dir'
        conf.list = 'work'
        conf.title = 'A subtask title'
        conf.parent = '9o71lx'
        conf.loe = '2'

        written = add_item(conf, t.now)

        with t.subTest('a parent sends the add to the subtask path'):
            t.add_task.assert_not_called()
            t.add_subtask.assert_called_once_with(
                t.Task.return_value,
                'work',
                'A subtask title',
                {'LOE': '2'},
            )

        with t.subTest('the parent is the task its selector names'):
            t.Task.assert_called_once_with(SOURCE, '9o71lx', t.today)

        with t.subTest('the subtask line and its file come back'):
            t.assertEqual(written, f'{t.entry}\n{t.path}')


class UpdateItemTests(TestCase):
    """Unit tests for battodo.lib.update_item."""

    def setUp(t):
        patches = ['update_task', 'Task']
        for target in patches:
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)

        t.path = Path('~/a-source-dir/a-list.md')
        t.entry = '- [ ] A task title [P:4] [ID:ab12cd]'
        t.update_task.return_value = (t.path, t.entry)

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
        t.update_task.assert_called_once_with(
            t.Task.return_value,
            {'P': '4', 'DUE': '2026-09-01'},
            title='A task title',
        )

    def test_result(t):
        written = update_item(t.conf, t.now)
        t.assertEqual(written, f'{t.entry}\n{t.path}')

    def test_option_left_off(t):
        conf = Mock(spec=['view', 'selector', 'tags'])
        conf.view = Mock(spec=['source_dir'])
        conf.view.source_dir = '~/a-source-dir'
        conf.selector = 'a selector'
        conf.tags = 'yard,summer'

        update_item(conf, t.now)

        # An option left off names no change to that field.
        args, kwargs = t.update_task.call_args
        t.assertEqual(args[1], {'TAGS': 'yard,summer'})
        t.assertIsNone(kwargs['title'])


class CompleteItemTests(TestCase):
    """Unit tests for battodo.lib.complete_item."""

    def setUp(t):
        patches = ['Task', 'complete']
        for target in patches:
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        # autospec builds `from_config` from its signature, so its
        # return value carries no spec. The instance mock does, so the
        # classmethod is pointed at that.
        t.task = t.Task.return_value
        t.Task.from_config.return_value = t.task

        t.now = sentinel.now
        # The task decodes the configuration, so this call reads no
        # value off it. The spec still names what a `done` carries.
        t.conf = Mock(spec=['view', 'selector'])

    def test_result(t):
        # Completing the last open child completes its parent too, so
        # one call can log more than one entry.
        t.complete.return_value = [
            '2026-08-08 | chores | DONE | A parent > A child',
            '2026-08-08 | chores | DONE | A parent',
        ]

        logged = complete_item(t.conf, t.now)

        t.assertEqual(
            logged,
            '2026-08-08 | chores | DONE | A parent > A child\n'
            '2026-08-08 | chores | DONE | A parent',
        )

    def test_task(t):
        t.complete.return_value = []

        complete_item(t.conf, t.now)

        with t.subTest('the configuration is decoded once, by the task'):
            t.Task.from_config.assert_called_once_with(t.conf, t.now)

        with t.subTest('which the call then completes'):
            t.complete.assert_called_once_with(t.task)

    def test_nothing_logged(t):
        t.complete.return_value = []
        logged = complete_item(t.conf, t.now)
        t.assertEqual(logged, 'checked off')


class ScratchItemTests(TestCase):
    """Unit tests for battodo.lib.scratch_item."""

    def setUp(t):
        patches = ['scratch', 'Task']
        for target in patches:
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)

        t.now = Mock(spec=datetime)
        t.today = t.now.date.return_value
        t.conf = Mock(spec=['view', 'selector'])
        t.conf.view = Mock(spec=['source_dir'])
        t.conf.view.source_dir = '~/a-source-dir'
        t.conf.selector = 'a selector'

    def test_result(t):
        t.scratch.return_value = [
            '2026-08-08 | chores | SCRATCHED | A parent > A child',
            '2026-08-08 | chores | SCRATCHED | A parent',
        ]

        logged = scratch_item(t.conf, t.now)

        t.assertEqual(
            logged,
            '2026-08-08 | chores | SCRATCHED | A parent > A child\n'
            '2026-08-08 | chores | SCRATCHED | A parent',
        )

    def test_forwarded(t):
        t.scratch.return_value = []

        scratch_item(t.conf, t.now)

        t.Task.assert_called_once_with(SOURCE, 'a selector', t.today)
        t.scratch.assert_called_once_with(t.Task.return_value)

    def test_nothing_logged(t):
        t.scratch.return_value = []
        logged = scratch_item(t.conf, t.now)
        t.assertEqual(logged, 'dropped')


class BackfillItemsTests(TestCase):
    """Unit tests for battodo.lib.backfill_items."""

    def setUp(t):
        patcher = patch(f'{SRC}.backfill_all', autospec=True)
        t.backfill_all = patcher.start()
        t.addCleanup(patcher.stop)

        t.now = Mock(spec=datetime)
        t.today = t.now.date.return_value
        t.conf = Mock(spec=['view'])
        t.conf.view = Mock(spec=['source_dir'])
        t.conf.view.source_dir = '~/a-source-dir'

    def test_result(t):
        t.backfill_all.return_value = {
            'work.md': ['a', 'b'],
            'chores.md': ['c'],
        }

        stamped = backfill_items(t.conf, t.now)

        # A count per changed list, in name order.
        t.assertEqual(stamped, 'chores.md: stamped 1\nwork.md: stamped 2')

    def test_forwarded(t):
        t.backfill_all.return_value = {}

        backfill_items(t.conf, t.now)

        args = t.backfill_all.call_args[0]
        t.assertEqual(args[0], SOURCE)
        t.assertEqual(args[1], t.today)

    def test_nothing_stamped(t):
        t.backfill_all.return_value = {}
        stamped = backfill_items(t.conf, t.now)
        t.assertEqual(stamped, 'nothing to backfill')
