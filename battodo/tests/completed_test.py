from datetime import date, datetime, timezone
from json import loads
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, Mock

from ..completed import (
    DEFAULT_PERIOD,
    CompletedError,
    Digest,
    DigestView,
    Group,
    Record,
    Table,
    read_record,
)

TODAY = date(2026, 8, 5)
NOW = datetime(2026, 8, 5, 10, 30, tzinfo=timezone.utc)
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
# Wide enough to lay a short record out.
WIDTHS = [10, 20]


class ReadRecordTests(TestCase):
    """Unit tests for battodo.completed.read_record."""

    def test_read_record(t) -> None:
        with t.subTest('a DONE line is a record'):
            t.assertEqual(
                read_record('2026-08-04 | chores | DONE | A completed task'),
                Record(date(2026, 8, 4), 'chores', 'A completed task'),
            )

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
                t.assertEqual(
                    read_record(line), Record(date(2026, 8, 4), 'work', title)
                )

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
                t.assertIsNone(read_record(line))


class RecordTests(TestCase):
    """Unit tests for battodo.completed.Record."""

    def setUp(t) -> None:
        t.r = Record(date(2026, 8, 4), 'chores', 'Deck > Chip it')

    def test_cells(t) -> None:
        t.assertEqual(t.r.cells, ('2026-08-04', 'Deck > Chip it'))

    def test_entry(t) -> None:
        t.assertEqual(
            t.r.entry, {'date': '2026-08-04', 'title': 'Deck > Chip it'}
        )


class GroupTests(TestCase):
    """Unit tests for battodo.completed.Group."""

    def setUp(t) -> None:
        t.g = Group(
            'side-quests',
            [Record(date(2026, 8, 4), 'side-quests', 'A record')],
        )

    def test_title(t) -> None:
        t.assertEqual(t.g.title, 'Side quests')

    def test_entries(t) -> None:
        t.assertEqual(
            t.g.entries, [{'date': '2026-08-04', 'title': 'A record'}]
        )


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
        t.assertEqual(t.d.today, TODAY)

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
                t.assertEqual(digest.start, expected)

        with (
            t.subTest('a period with no definition is an error'),
            t.assertRaises(ValueError),
        ):
            _ = Digest(t.directory, NOW, period='fortnight').start

    def test_end(t) -> None:
        t.assertEqual(t.d.end, TODAY)

    def test_path(t) -> None:
        with t.subTest('the log sits beside the lists'):
            t.assertIs(t.d.path, t.log)
            t.directory.expanduser.return_value.__truediv__.assert_called_with(
                'completed.md'
            )

        with t.subTest('a source with no log is an error, not an empty day'):
            t.log.is_file.return_value = False
            with t.assertRaises(CompletedError) as caught:
                _ = Digest(t.directory, NOW, period='week').path
            t.assertIn('completed log not found', str(caught.exception))

    def test_text(t) -> None:
        t.assertEqual(t.d.text, LOG)
        t.log.read_text.assert_called_once_with(encoding='utf-8')

    def test_records(t) -> None:
        with t.subTest('the DONE records of the period, oldest first'):
            t.assertEqual(
                [found.title for found in t.d.records],
                [
                    'Oldest in the week',
                    'In the other category',
                    'Completed today',
                ],
            )

        with t.subTest('a shorter period holds fewer of them'):
            digest = Digest(t.directory, NOW, period='today')
            t.assertEqual(
                [found.title for found in digest.records],
                ['Completed today'],
            )

    def test_groups(t) -> None:
        with t.subTest('one group per category, in the view order'):
            t.assertEqual(
                [group.name for group in t.d.groups],
                ['work', 'unlisted'],
            )

        with t.subTest('each holding its own records'):
            t.assertEqual(
                [found.title for found in t.d.groups[0].records],
                ['Oldest in the week', 'Completed today'],
            )

    def test_data(t) -> None:
        t.assertEqual(
            t.d.data,
            {
                'period': 'week',
                'start': '2026-07-30',
                'end': '2026-08-05',
                'total': 3,
                'categories': [
                    {
                        'name': 'work',
                        'entries': [
                            {
                                'date': '2026-07-30',
                                'title': 'Oldest in the week',
                            },
                            {
                                'date': '2026-08-05',
                                'title': 'Completed today',
                            },
                        ],
                    },
                    {
                        'name': 'unlisted',
                        'entries': [
                            {
                                'date': '2026-08-02',
                                'title': 'In the other category',
                            }
                        ],
                    },
                ],
            },
        )

    def test_json(t) -> None:
        with t.subTest('what comes back is the digest, serialized'):
            t.assertEqual(loads(t.d.json), t.d.data)

        with t.subTest('indented for a person to read as well'):
            t.assertIn('\n  "period": "week"', t.d.json)


class DigestFromConfigTests(TestCase):
    """Unit tests for battodo.completed.Digest.from_config.

    The decode from configuration values to what a digest takes.
    """

    def setUp(t) -> None:
        # spec models batconf: an option the user did not supply is
        # absent from the Configuration, not None.
        t.conf = Mock(spec=['view', 'period'])
        t.conf.view = Mock(spec=['source_dir'])
        t.conf.view.source_dir = '~/todo'
        t.conf.period = 'month'

    def test_from_config(t) -> None:
        digest = Digest.from_config(t.conf, NOW)

        with t.subTest('the source directory is left unexpanded'):
            t.assertEqual(digest.directory, Path('~/todo'))

        with t.subTest('the clock is the one it was given'):
            t.assertEqual(digest.now, NOW)

        with t.subTest('and the period is the configured one'):
            t.assertEqual(digest.period, 'month')

        with t.subTest('an unsupplied period reads as the default'):
            conf = Mock(spec=['view'])
            conf.view = Mock(spec=['source_dir'])
            conf.view.source_dir = '~/todo'

            t.assertEqual(Digest.from_config(conf, NOW).period, DEFAULT_PERIOD)


class TableTests(TestCase):
    """Unit tests for battodo.completed.Table."""

    def setUp(t) -> None:
        t.group = Group('work', [Record(date(2026, 8, 5), 'work', 'Ship it')])
        t.table = Table(t.group, WIDTHS)

    def test_heading(t) -> None:
        with t.subTest('a titled rule spanning the table'):
            t.assertEqual(t.table.heading, '── Work ' + '─' * 26)

        with t.subTest('a title of its own length rules no further'):
            wide = Table(Group('a' * 40, []), WIDTHS)
            t.assertEqual(wide.heading, f'── {"A" + "a" * 39} ')

    def test_line(t) -> None:
        with t.subTest('each cell padded to its column'):
            t.assertEqual(t.table.line(('a', 'b')), '  a' + ' ' * 11 + 'b')

        with t.subTest('trailing space is stripped'):
            t.assertEqual(t.table.line(('', '')), '')

    def test_lines(t) -> None:
        t.assertEqual(
            t.table.lines,
            [
                '  DATE        TASK',
                '  2026-08-05  Ship it',
            ],
        )


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
            t.assertEqual(t.v.span, '2026-07-30 to 2026-08-05')

        with t.subTest('a single day reads as one date'):
            t.digest.start = TODAY
            t.assertEqual(t.v.span, '2026-08-05')

    def test_header(t) -> None:
        t.assertEqual(
            t.v.header, 'Completed week: 2026-07-30 to 2026-08-05 — 2 done'
        )

    def test_widths(t) -> None:
        with t.subTest('each column as wide as its widest cell'):
            t.assertEqual(
                t.v.widths, [10, len('A record of another category')]
            )

        with t.subTest('the column name counts too'):
            t.digest.records = [Record(date(2026, 8, 5), 'work', 'Go')]
            t.assertEqual(DigestView(t.digest).widths, [10, len('TASK')])

    def test_tables(t) -> None:
        t.assertEqual([table.group for table in t.v.tables], t.digest.groups)
        t.assertEqual([table.widths for table in t.v.tables], [t.v.widths] * 2)

    def test_text(t) -> None:
        t.assertEqual(
            t.v.text,
            '\n'.join(
                (
                    'Completed week: 2026-07-30 to 2026-08-05 — 2 done',
                    '',
                    '── Work ' + '─' * 34,
                    '  DATE        TASK',
                    '  2026-07-30  A record of the week',
                    '',
                    '── Unlisted ' + '─' * 30,
                    '  DATE        TASK',
                    '  2026-08-02  A record of another category',
                )
            ),
        )

    def test___str__(t) -> None:
        t.assertEqual(str(t.v), t.v.text)
