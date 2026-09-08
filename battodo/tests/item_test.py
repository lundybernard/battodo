from datetime import date, datetime, timezone
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

from ..item import (
    TaskNode,
    build_item,
    build_item_json,
    item_data,
    render_item,
    subtask_entry,
)

SRC = 'battodo.item'
TODAY = date(2026, 8, 5)


def stand_in(t: TestCase, *targets: str) -> None:
    """Patch each `battodo.item` target and set its mock on `t`."""
    for target in targets:
        patcher = patch(f'{SRC}.{target}', autospec=True)
        setattr(t, target, patcher.start())
        t.addCleanup(patcher.stop)


def task(title: str, **fields: str) -> TaskNode:
    """A top-level open task carrying `fields`."""
    return TaskNode(
        raw_index=0,
        indent=0,
        done=False,
        title=title,
        fields=fields,
    )


def entry(title: str, **overrides: object) -> dict[str, object]:
    """One subtask as `item_data` records it."""
    return {
        'id': None,
        'title': title,
        'done': False,
        'loe': None,
        'due': None,
        'tags': [],
        'subtasks': [],
        **overrides,
    }


class SubtaskEntryTests(TestCase):
    """Unit tests for battodo.item.subtask_entry."""

    def test_fields(t) -> None:
        deep = TaskNode(
            raw_index=3,
            indent=4,
            done=True,
            title='Buy the lumber',
            fields={'DUE': '2026-09-01'},
        )
        child = TaskNode(
            raw_index=2,
            indent=2,
            done=False,
            title='Chip the brush',
            fields={'LOE': '2', 'TAGS': 'yard,summer', 'ID': 'abc123'},
            children=[deep],
        )

        # The stored fields, and the children below it.
        t.assertEqual(
            subtask_entry(child),
            entry(
                'Chip the brush',
                id='abc123',
                loe=2,
                tags=['yard', 'summer'],
                subtasks=[
                    entry('Buy the lumber', done=True, due='2026-09-01')
                ],
            ),
        )

    def test_checklist_item(t) -> None:
        # A checklist item carries no field at all.
        plain = TaskNode(
            raw_index=1, indent=2, done=False, title='Sweep', fields={}
        )
        t.assertEqual(subtask_entry(plain), entry('Sweep'))


class ItemDataTests(TestCase):
    """Unit tests for battodo.item.item_data."""

    def test_fields(t) -> None:
        # The list, the stored fields, and the children.
        subject = task(
            'Deck rebuild',
            P='4',
            LOE='8',
            DUE='2026-08-12',
            REPEAT='30d',
            TAGS='yard,summer',
            ADDED='2026-07-06',
            ID='9o71lx',
        )
        subject.children = [
            TaskNode(
                raw_index=1,
                indent=2,
                done=False,
                title='Sweep',
                fields={},
            )
        ]

        t.assertEqual(
            item_data(Path('/todo/work.md'), subject, TODAY),
            {
                'list': 'work',
                'id': '9o71lx',
                'title': 'Deck rebuild',
                'done': False,
                # One month old and one week from due: 4 x 2.5.
                'rank': 10.0,
                'priority': 4.0,
                'loe': 8,
                'due': '2026-08-12',
                'added': '2026-07-06',
                'repeat': '30d',
                'tags': ['yard', 'summer'],
                'subtasks': [entry('Sweep')],
            },
        )

    def test_absent(t) -> None:
        # An unfielded task reads as absent, not as zero.
        t.assertEqual(
            item_data(Path('/todo/work.md'), task('Bare'), TODAY),
            {
                'list': 'work',
                'id': None,
                'title': 'Bare',
                'done': False,
                'rank': 1.0,
                'priority': 1.0,
                'loe': None,
                'due': None,
                'added': None,
                'repeat': None,
                'tags': [],
                'subtasks': [],
            },
        )


class RenderItemTests(TestCase):
    """Unit tests for battodo.item.render_item."""

    maxDiff = None

    def setUp(t) -> None:
        t.data: dict[str, object] = {
            'list': 'work',
            'id': '9o71lx',
            'title': 'Deck rebuild',
            'done': False,
            'rank': 10.0,
            'priority': 4.0,
            'loe': 8,
            'due': '2026-08-12',
            'added': '2026-07-06',
            'repeat': '30d',
            'tags': ['yard', 'summer'],
            'subtasks': [],
        }

    def test_rows(t) -> None:
        # One labelled row per value, aligned.
        t.assertEqual(
            render_item(t.data),
            'Deck rebuild\n'
            '  list    work\n'
            '  id      9o71lx\n'
            '  rank    10.0\n'
            '  P       4.0\n'
            '  LOE     8\n'
            '  DUE     2026-08-12\n'
            '  REPEAT  30d\n'
            '  TAGS    yard, summer\n'
            '  ADDED   2026-07-06',
        )

    def test_absent(t) -> None:
        # An absent field has no row, an absent id a dash.
        t.data.update(
            id=None, loe=None, due=None, repeat=None, tags=[], added=None
        )
        t.assertEqual(
            render_item(t.data),
            'Deck rebuild\n  list  work\n  id    -\n  rank  10.0\n  P     4.0',
        )

    def test_subtasks(t) -> None:
        # Children follow, indented, in SCHEMA.md markup.
        t.data['subtasks'] = [
            entry(
                'Chip the brush',
                id='abc123',
                loe=2,
                due='2026-09-01',
                tags=['yard'],
                subtasks=[entry('Buy the lumber', done=True)],
            )
        ]
        t.assertEqual(
            render_item(t.data).splitlines()[-3:],
            [
                '  subtasks',
                (
                    '    [ ] Chip the brush [LOE:2] [DUE:2026-09-01] '
                    '[TAGS:yard] [ID:abc123]'
                ),
                '      [x] Buy the lumber',
            ],
        )


class BuildItemTests(TestCase):
    """Unit tests for battodo.item.build_item."""

    TaskSelection: MagicMock
    item_data: MagicMock
    render_item: MagicMock

    def setUp(t) -> None:
        stand_in(t, 'TaskSelection', 'item_data', 'render_item')
        t.directory = Path('/todo')
        t.now = datetime(2026, 8, 5, 10, 30, tzinfo=timezone.utc)
        # An autospec instance specs `record` from the descriptor, not
        # from the value it yields.
        t.record = MagicMock(spec=['path', 'task'])
        t.TaskSelection.return_value.record = t.record

    def test_selection(t) -> None:
        build_item(t.directory, 'deck', t.now)

        t.TaskSelection.assert_called_with(t.directory, 'deck')

    def test_data(t) -> None:
        build_item(t.directory, 'deck', t.now)

        # The local day of the clock decides the rank.
        t.item_data.assert_called_with(t.record.path, t.record.task, TODAY)

    def test_text(t) -> None:
        result = build_item(t.directory, 'deck', t.now)

        t.render_item.assert_called_with(t.item_data.return_value)
        t.assertEqual(result, t.render_item.return_value)


class BuildItemJsonTests(TestCase):
    """Unit tests for battodo.item.build_item_json."""

    TaskSelection: MagicMock
    item_data: MagicMock
    dumps: MagicMock

    def setUp(t) -> None:
        stand_in(t, 'TaskSelection', 'item_data', 'dumps')
        t.directory = Path('/todo')
        t.now = datetime(2026, 8, 5, 10, 30, tzinfo=timezone.utc)
        # An autospec instance specs `record` from the descriptor, not
        # from the value it yields.
        t.record = MagicMock(spec=['path', 'task'])
        t.TaskSelection.return_value.record = t.record

    def test_selection(t) -> None:
        build_item_json(t.directory, 'deck', t.now)

        # The same selection the text form describes.
        t.TaskSelection.assert_called_with(t.directory, 'deck')
        t.item_data.assert_called_with(t.record.path, t.record.task, TODAY)

    def test_json(t) -> None:
        result = build_item_json(t.directory, 'deck', t.now)

        # Serialized, indented for a person to read too.
        t.dumps.assert_called_with(t.item_data.return_value, indent=2)
        t.assertEqual(result, t.dumps.return_value)
