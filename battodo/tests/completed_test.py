from datetime import UTC, date, datetime
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, Mock, PropertyMock, call, patch, sentinel

from ..completed import (
    CompletedError,
    Digest,
    DigestJsonView,
    DigestView,
    Group,
    GroupJsonView,
    Record,
    RecordJsonView,
    RecordView,
    Table,
    read_attributes,
    read_record,
    split_attributes,
)

SRC = 'battodo.completed'
TODAY = date(2026, 8, 5)
NOW = datetime(2026, 8, 5, 10, 30, tzinfo=UTC)
# Two records of one category, one of another, one outside every
# period, and one abandoned. The dates are out of order on purpose.
LOG = """\
# Completed Tasks
2026-06-14 | unlisted | DONE | Outside every period [P:7]
2026-08-05 | work | DONE | Completed today
2026-07-30 | work | DONE | Oldest in the week
2026-08-02 | unlisted | DONE | In the other category
2026-08-03 | work | SCRATCHED | Abandoned, not completed
"""


class DigestTests(TestCase):
    """Unit tests for battodo.completed.Digest."""

    def setUp(t) -> None:
        t.log = MagicMock(spec=Path)
        t.log.is_file.return_value = True
        t.log.read_text.return_value = LOG
        t.directory = MagicMock(spec=Path)
        t.directory.expanduser.return_value.__truediv__.return_value = t.log

        t.d = Digest(t.directory, NOW, period='week')

    def test_today(t) -> None:
        ret = t.d.today
        t.assertEqual(ret, TODAY)

    def test_start(t) -> None:
        cases = {
            'today is the day itself': ('today', TODAY),
            'the week reaches back seven days, today included': (
                'week',
                date(2026, 7, 30),
            ),
            'and the month to its first day': ('month', date(2026, 8, 1)),
        }

        for name, (period, expected) in cases.items():
            with t.subTest(name):
                digest = Digest(t.directory, NOW, period=period)
                ret = digest.start
                t.assertEqual(ret, expected)

        with (
            t.subTest('a period with no definition is an error'),
            t.assertRaises(ValueError),
        ):
            _ = Digest(t.directory, NOW, period='fortnight').start

    def test_end(t) -> None:
        ret = t.d.end
        t.assertEqual(ret, TODAY)

    def test_path(t) -> None:
        with t.subTest('the log sits beside the lists'):
            ret = t.d.path

            t.assertIs(ret, t.log)
            t.directory.expanduser.return_value.__truediv__.assert_called_with(
                'completed.md'
            )

        with t.subTest('a source with no log is an error, not an empty day'):
            t.log.is_file.return_value = False

            with t.assertRaises(CompletedError) as caught:
                _ = Digest(t.directory, NOW, period='week').path

            t.assertIn('completed log not found', str(caught.exception))

    def test_text(t) -> None:
        ret = t.d.text
        t.assertEqual(ret, LOG)
        t.log.read_text.assert_called_once_with(encoding='utf-8')

    def test_records(t) -> None:
        with t.subTest('the DONE records of the period, oldest first'):
            ret = t.d.records

            t.assertEqual(
                [found.title for found in ret],
                [
                    'Oldest in the week',
                    'In the other category',
                    'Completed today',
                ],
            )

        with t.subTest('a shorter period holds fewer of them'):
            digest = Digest(t.directory, NOW, period='today')

            ret = digest.records

            t.assertEqual(
                [found.title for found in ret],
                ['Completed today'],
            )

        with t.subTest('a line ends at a line feed, and nowhere else'):
            # The list parser splits at line feeds alone, so a title
            # may hold any other line break. The title shows it as the
            # space it collapses to.
            t.log.read_text.return_value = (
                '2026-08-05 | work | DONE | Pay\u2028the bill\n'
                '2026-08-05 | work | DONE | Fix\x85it\n'
            )
            digest = Digest(t.directory, NOW, period='today')

            ret = digest.records

            t.assertEqual(
                [found.title for found in ret],
                ['Pay the bill', 'Fix it'],
            )

    def test_groups(t) -> None:
        ret = t.d.groups

        with t.subTest('one group per category, in the view order'):
            t.assertEqual(
                [group.name for group in ret],
                ['work', 'unlisted'],
            )

        with t.subTest('each holding its own records'):
            t.assertEqual(
                [found.title for found in ret[0].records],
                ['Oldest in the week', 'Completed today'],
            )


class DigestFromConfigTests(TestCase):
    """Unit tests for battodo.completed.Digest.from_config.

    The decode from configuration values to what a digest takes.
    """

    def setUp(t) -> None:
        t.conf = Mock(spec=['view'])
        t.conf.view = Mock(spec=['source_dir'])
        t.conf.view.source_dir = '~/a-source-dir'

    def test_from_config(t) -> None:
        digest = Digest.from_config(t.conf, NOW, period='month')

        with t.subTest('the source directory is left unexpanded'):
            t.assertEqual(digest.directory, Path('~/a-source-dir'))

        with t.subTest('the clock is the one it was given'):
            t.assertEqual(digest.now, NOW)

        with t.subTest('and the period is the one given'):
            t.assertEqual(digest.period, 'month')


class ReadRecordTests(TestCase):
    """Unit tests for battodo.completed.read_record."""

    def test_record(t) -> None:
        ret = read_record('2026-08-04 | chores | DONE | A completed task')

        t.assertEqual(
            ret,
            Record(date(2026, 8, 4), 'chores', 'A completed task'),
        )

    def test_title(t) -> None:
        titles = {
            'the title keeps its ancestry, and loses its fields': (
                '2026-08-04 | work | DONE | Deck > Chip [LOE:2] [P:4]',
                'Deck > Chip',
            ),
            'a field inside a title leaves no gap behind': (
                '2026-08-04 | work | DONE | Ship [P:4] it',
                'Ship it',
            ),
            'a separator inside a title is part of the title': (
                '2026-08-04 | work | DONE | Ship it | today',
                'Ship it | today',
            ),
        }

        for name, (line, title) in titles.items():
            with t.subTest(name):
                ret = read_record(line)

                t.assertEqual(
                    ret,
                    Record(date(2026, 8, 4), 'work', title),
                )

    def test_skipped(t) -> None:
        skipped = {
            'an abandoned task is no completion': (
                '2026-08-04 | work | SCRATCHED | Drop it'
            ),
            'a comment carries no date': (
                '<!-- YYYY-MM-DD | CATEGORY | DONE | TITLE -->'
            ),
            'a heading is not a record': '# Completed Tasks',
            'a blank line holds nothing': '',
            'and neither does prose': 'this line is not a record',
        }

        for name, line in skipped.items():
            with t.subTest(name):
                ret = read_record(line)
                t.assertIsNone(ret)

    def test_attributes(t) -> None:
        line = (
            '2026-08-04 | work | DONE | Deck > Chip [LOE:2] '
            '[attrs:{"cost": "45.00"}]'
        )

        ret = read_record(line)

        t.assertEqual(
            ret,
            Record(date(2026, 8, 4), 'work', 'Deck > Chip', {'cost': '45.00'}),
        )


class SplitAttributesTests(TestCase):
    """Unit tests for battodo.completed.split_attributes."""

    def test_block(t) -> None:
        cases = {
            'the block after the fields leaves the text': (
                'Ship | it, x=1 [P:4] [attrs:{"cost": "45.00"}]',
                ('Ship | it, x=1 [P:4] ', {'cost': '45.00'}),
            ),
            'a value may hold the mark and a bracket': (
                'Ship [attrs:{"note": "[attrs:{} ]"}]',
                ('Ship ', {'note': '[attrs:{} ]'}),
            ),
            'a mark in the text before the block stays text': (
                'Read [attrs:{"a": "b"} later [attrs:{"cost": "4"}]',
                ('Read [attrs:{"a": "b"} later ', {'cost': '4'}),
            ),
        }

        for name, (text, expected) in cases.items():
            with t.subTest(name):
                ret = split_attributes(text)
                t.assertEqual(ret, expected)

    def test_text(t) -> None:
        cases = {
            'a text with no mark': 'Ship it [P:4]',
            'a mark that opens no block': 'Keep [attrs:x] as text',
            'a block that is not the end of the text': (
                'Read [attrs:{"a": "b"}] later'
            ),
        }

        for name, text in cases.items():
            with t.subTest(name):
                ret = split_attributes(text)
                t.assertEqual(ret, (text, {}))


class ReadAttributesTests(TestCase):
    """Unit tests for battodo.completed.read_attributes."""

    def test_attributes(t) -> None:
        ret = read_attributes('{"cost": "45.00", "note": "Paid]"}]')
        t.assertEqual(ret, {'cost': '45.00', 'note': 'Paid]'})

    def test_unread(t) -> None:
        cases = {
            'no closing bracket': '{"cost": "45.00"}',
            'no JSON before it': '{cost=45.00}]',
            'JSON that is not an object': '["cost"]]',
            'a value that is not text': '{"cost": 45}]',
        }

        for name, block in cases.items():
            with t.subTest(name):
                ret = read_attributes(block)
                t.assertIsNone(ret)


class DigestViewTests(TestCase):
    """Unit tests for battodo.completed.DigestView."""

    def setUp(t) -> None:
        t.records = [
            Record(date(2026, 7, 30), 'work', 'A record of the week'),
            Record(
                date(2026, 8, 2),
                'unlisted',
                'A record of another category',
            ),
        ]
        t.digest = Mock(spec=Digest)
        t.digest.period = 'week'
        t.digest.start = date(2026, 7, 30)
        t.digest.end = TODAY
        t.digest.records = t.records
        t.digest.groups = [
            Group('work', t.records[:1]),
            Group('unlisted', t.records[1:]),
        ]

        t.v = DigestView(t.digest)

    def test_span(t) -> None:
        with t.subTest('the first day and the last'):
            ret = t.v.span
            t.assertEqual(ret, '2026-07-30 to 2026-08-05')

        with t.subTest('a single day reads as one date'):
            t.digest.start = TODAY
            ret = t.v.span
            t.assertEqual(ret, '2026-08-05')

    def test_header(t) -> None:
        ret = t.v.header

        t.assertEqual(
            ret,
            'Completed week: 2026-07-30 to 2026-08-05 — 2 done',
        )

    @patch(f'{SRC}.RecordView', autospec=True)
    def test_widths(t, record_view: MagicMock) -> None:
        with t.subTest('each column as wide as its widest cell'):
            record_view.return_value.cells = ('2026-08-02', 'A record cell')
            ret = t.v.widths
            t.assertEqual(ret, [10, len('A record cell')])

        with t.subTest('the cells of each record come from its view'):
            t.assertEqual(
                record_view.call_args_list,
                [call(record) for record in t.records],
            )

        with t.subTest('the column name counts too'):
            record_view.return_value.cells = ('2026-08-05', 'Go')
            ret = DigestView(t.digest).widths
            t.assertEqual(ret, [10, len('TASK')])

        with t.subTest('and with no records, the names alone'):
            t.digest.records = []
            ret = DigestView(t.digest).widths
            t.assertEqual(ret, [len('DATE'), len('TASK')])

    @patch(f'{SRC}.Table', autospec=True)
    @patch(f'{SRC}.RecordView', autospec=True)
    def test_tables(t, record_view: MagicMock, table: MagicMock) -> None:
        record_view.return_value.cells = ('2026-08-02', 'A record cell')
        t.v.widths = [10, 28]

        ret = t.v.tables

        # A table per group, at the widths of the digest, with the cells
        # of each record it holds.
        t.assertEqual(ret, [table.return_value] * 2)
        t.assertEqual(
            record_view.call_args_list,
            [call(record) for record in t.records],
        )
        t.assertEqual(
            table.call_args_list,
            [
                call(
                    'work',
                    ('DATE', 'TASK'),
                    ('<', '<'),
                    [('2026-08-02', 'A record cell')],
                    [10, 28],
                ),
                call(
                    'unlisted',
                    ('DATE', 'TASK'),
                    ('<', '<'),
                    [('2026-08-02', 'A record cell')],
                    [10, 28],
                ),
            ],
        )

    @patch(f'{SRC}.page_text', autospec=True)
    def test_text(t, page_text: MagicMock) -> None:
        t.v.tables = [Mock(spec=Table)]

        ret = t.v.text

        # The header, then the tables, laid out as one page.
        page_text.assert_called_once_with(t.v.header, t.v.tables)
        t.assertIs(ret, page_text.return_value)

    def test___str__(t) -> None:
        ret = str(t.v)
        t.assertEqual(ret, t.v.text)


class RecordViewTests(TestCase):
    """Unit tests for battodo.completed.RecordView."""

    def setUp(t) -> None:
        t.record = Record(date(2026, 8, 4), 'chores', 'A parent > A record')
        t.rv = RecordView(t.record)

    @patch.object(RecordView, 'attributes', new_callable=PropertyMock)
    def test_cells(t, attributes: PropertyMock) -> None:
        with t.subTest('the date and the title'):
            attributes.return_value = ''
            ret = t.rv.cells
            t.assertEqual(ret, ('2026-08-04', 'A parent > A record'))

        with t.subTest('the attributes follow the title'):
            attributes.return_value = 'cost=45.00'

            ret = t.rv.cells

            t.assertEqual(
                ret,
                ('2026-08-04', 'A parent > A record cost=45.00'),
            )

    def test_attributes(t) -> None:
        with t.subTest('none'):
            ret = t.rv.attributes
            t.assertEqual(ret, '')

        with t.subTest('each as key=value, in the order logged'):
            t.rv.record = Record(
                date(2026, 8, 4),
                'chores',
                'A parent > A record',
                {'place': 'Main St, Suite 4', 'cost': '45.00'},
            )

            ret = t.rv.attributes

            t.assertEqual(ret, 'place=Main St, Suite 4, cost=45.00')

    def test_record(t) -> None:
        ret = t.rv.record
        t.assertIs(ret, t.record)


class DigestJsonViewTests(TestCase):
    """Unit tests for battodo.completed.DigestJsonView."""

    def setUp(t) -> None:
        t.digest = Mock(spec=Digest)
        t.digest.period = 'week'
        t.digest.start = date(2026, 7, 30)
        t.digest.end = TODAY
        t.digest.records = [sentinel.record] * 3
        t.djv = DigestJsonView(t.digest)

    @patch(f'{SRC}.dumps', autospec=True)
    @patch.object(DigestJsonView, 'data', new_callable=PropertyMock)
    def test_json(t, data: PropertyMock, dumps: MagicMock) -> None:
        ret = t.djv.json
        # Serialized, indented for a person to read too.
        dumps.assert_called_once_with(data.return_value, indent=2)
        t.assertIs(ret, dumps.return_value)

    @patch.object(DigestJsonView, 'groups', new_callable=PropertyMock)
    def test_data(t, groups: PropertyMock) -> None:
        group = Mock(spec=GroupJsonView)
        group.data = {'name': 'work'}
        groups.return_value = [group]

        ret = t.djv.data

        # A digest abridges nothing: the total counts every record.
        t.assertEqual(
            ret,
            {
                'period': 'week',
                'start': '2026-07-30',
                'end': '2026-08-05',
                'total': 3,
                'categories': [{'name': 'work'}],
            },
        )

    @patch(f'{SRC}.GroupJsonView', autospec=True)
    def test_groups(t, group_json_view: MagicMock) -> None:
        first = Mock(spec=Group)
        second = Mock(spec=Group)
        t.digest.groups = [first, second]

        ret = t.djv.groups

        # One per group, in the digest's order.
        t.assertEqual(ret, [group_json_view.return_value] * 2)
        t.assertEqual(
            group_json_view.call_args_list,
            [call(first), call(second)],
        )


class GroupJsonViewTests(TestCase):
    """Unit tests for battodo.completed.GroupJsonView."""

    def setUp(t) -> None:
        t.group = Mock(spec=Group)
        t.group.name = 'side-quests'
        t.gjv = GroupJsonView(t.group)

    @patch.object(GroupJsonView, 'records', new_callable=PropertyMock)
    def test_data(t, records: PropertyMock) -> None:
        record = Mock(spec=RecordJsonView)
        record.data = {'title': 'A record'}
        records.return_value = [record]

        ret = t.gjv.data

        t.assertEqual(
            ret,
            {'name': 'side-quests', 'entries': [{'title': 'A record'}]},
        )

    @patch(f'{SRC}.RecordJsonView', autospec=True)
    def test_records(t, record_json_view: MagicMock) -> None:
        first = Mock(spec=Record)
        second = Mock(spec=Record)
        t.group.records = [first, second]

        ret = t.gjv.records

        # One per record, in the group's order.
        t.assertEqual(ret, [record_json_view.return_value] * 2)
        t.assertEqual(
            record_json_view.call_args_list,
            [call(first), call(second)],
        )


class RecordJsonViewTests(TestCase):
    """Unit tests for battodo.completed.RecordJsonView."""

    def setUp(t) -> None:
        t.record = Record(date(2026, 8, 4), 'chores', 'A parent > A record')
        t.rjv = RecordJsonView(t.record)

    def test_data(t) -> None:
        with t.subTest('a record without attributes holds an empty map'):
            ret = t.rjv.data
            t.assertEqual(
                ret,
                {
                    'date': '2026-08-04',
                    'title': 'A parent > A record',
                    'attrs': {},
                },
            )

        with t.subTest('and one with them holds each'):
            t.rjv.record = Record(
                date(2026, 8, 4),
                'chores',
                'A parent > A record',
                {'cost': '45.00'},
            )

            ret = t.rjv.data

            t.assertEqual(ret['attrs'], {'cost': '45.00'})
