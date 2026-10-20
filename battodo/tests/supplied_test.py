from datetime import date
from unittest import TestCase
from unittest.mock import (
    MagicMock,
    PropertyMock,
    patch,
)

from ..supplied import (
    AttributePair,
    AttributeSegment,
    DescriptionLine,
    SuppliedAttributes,
    SuppliedDescription,
    SuppliedEdit,
    SuppliedFields,
    SuppliedTitle,
)
from .mutate_test import TODAY, parent_node

SRC = 'battodo.supplied'


class SuppliedEditTests(TestCase):
    """Unit tests for battodo.supplied.SuppliedEdit."""

    def setUp(t) -> None:
        t.node = parent_node()
        t.se = SuppliedEdit({'P': '5'}, 'A new title', 'A line.', TODAY)

    @patch(f'{SRC}.next_due', autospec=True)
    def test_changed(t, next_due: MagicMock) -> None:
        with t.subTest('no clear: the fields, each value read'):
            ret = t.se.changed
            t.assertEqual(ret, {'P': '5'})

        with t.subTest('a repeat is read as add reads it'):
            t.se.fields = {'REPEAT': '14d'}

            ret = t.se.changed

            next_due.assert_called_once_with('14d', TODAY)
            t.assertEqual(ret, {'REPEAT': '14d'})

        with t.subTest('a repeat of None clears the field, unread'):
            next_due.reset_mock()
            t.se.fields = {'P': '3', 'REPEAT': 'None'}

            ret = t.se.changed

            next_due.assert_not_called()
            t.assertEqual(ret, {'P': '3', 'REPEAT': None})

        with t.subTest('an empty repeat is no clear: the read refuses it'):
            t.se.fields = {'REPEAT': ''}
            next_due.side_effect = ValueError("unrecognised REPEAT value: ''")

            with t.assertRaises(ValueError) as caught:
                _ = t.se.changed

            t.assertEqual(
                str(caught.exception), "unrecognised REPEAT value: ''"
            )

        with t.subTest('a due date and tags of None clear each field'):
            next_due.side_effect = None
            t.se.fields = {'P': '3', 'DUE': 'None', 'TAGS': 'None'}
            ret = t.se.changed
            t.assertEqual(ret, {'P': '3', 'DUE': None, 'TAGS': None})

    def test_cleared(t) -> None:
        with t.subTest('none, where no field names the clear token'):
            ret = t.se.cleared
            t.assertEqual(ret, [])

        with t.subTest('each due date, repeat and tags it names'):
            t.se.fields = {
                'P': '3',
                'DUE': 'None',
                'REPEAT': 'None',
                'TAGS': 'None',
            }

            ret = t.se.cleared

            t.assertEqual(ret, ['DUE', 'REPEAT', 'TAGS'])

        with t.subTest('not a priority, which reads the token as a value'):
            t.se.fields = {'P': 'None'}
            ret = t.se.cleared
            t.assertEqual(ret, [])

        with t.subTest('not an empty value'):
            t.se.fields = {'TAGS': ''}
            ret = t.se.cleared
            t.assertEqual(ret, [])

    @patch(f'{SRC}.SuppliedFields', autospec=True)
    def test_supplied(t, supplied_fields: MagicMock) -> None:
        with t.subTest('the named fields, against the day'):
            ret = t.se.supplied
            supplied_fields.assert_called_once_with({'P': '5'}, TODAY)
            t.assertIs(ret, supplied_fields.return_value)

        with t.subTest('a cleared field is left out, unread'):
            supplied_fields.reset_mock()
            t.se.fields = {'P': '5', 'DUE': 'None', 'TAGS': 'None'}

            _ = t.se.supplied

            supplied_fields.assert_called_once_with({'P': '5'}, TODAY)

    @patch(f'{SRC}.SuppliedTitle', autospec=True)
    def test_checked_title(t, supplied_title: MagicMock) -> None:
        with t.subTest('the named title, read'):
            ret = t.se.checked_title
            supplied_title.assert_called_once_with('A new title')
            t.assertIs(ret, supplied_title.return_value.checked)

        with t.subTest('none, where none is named'):
            supplied_title.reset_mock()
            t.se.title = None

            ret = t.se.checked_title

            supplied_title.assert_not_called()
            t.assertIsNone(ret)

    @patch(f'{SRC}.SuppliedDescription', autospec=True)
    def test_checked_description(t, supplied_description: MagicMock) -> None:
        supplied_description.return_value.lines = ['A line.']

        with t.subTest('the lines of the named description, read'):
            ret = t.se.checked_description
            supplied_description.assert_called_once_with('A line.')
            t.assertEqual(ret, ['A line.'])

        with t.subTest('a description of None clears, as an empty one'):
            supplied_description.reset_mock()
            t.se.description = 'None'

            _ = t.se.checked_description

            supplied_description.assert_called_once_with('')

        with t.subTest('none, where none is named'):
            supplied_description.reset_mock()
            t.se.description = None

            ret = t.se.checked_description

            supplied_description.assert_not_called()
            t.assertIsNone(ret)

    @patch.object(SuppliedEdit, 'changed', new_callable=PropertyMock)
    def test_changes(t, changed: PropertyMock) -> None:
        t.node.fields = {'P': '4', 'DUE': '2026-08-01', 'REPEAT': '7d'}
        cases = {
            'a new value is a change': ({'P': '5'}, {'P': '5'}),
            'the value the task holds is no change': ({'P': '4'}, {}),
            'a value read as the one it holds is no change': (
                {'P': '5', 'DUE': '2026-08-01'},
                {'P': '5'},
            ),
            'a clear of a field the task carries is a change': (
                {'REPEAT': None},
                {'REPEAT': None},
            ),
        }
        for name, (read, expected) in cases.items():
            with t.subTest(name):
                changed.return_value = read
                ret = t.se.changes(t.node)
                t.assertEqual(ret, expected)

        held = {
            'a clear of a field the task does not carry is no change': (
                {},
                {'REPEAT': None},
            ),
            'nor is a clear of a field it carries empty': (
                {'REPEAT': ''},
                {'REPEAT': None},
            ),
            'nor is an empty value the task holds': (
                {'TAGS': ''},
                {'TAGS': ''},
            ),
        }
        for name, (fields, read) in held.items():
            with t.subTest(name):
                t.node.fields = fields
                changed.return_value = read

                ret = t.se.changes(t.node)

                t.assertEqual(ret, {})

    @patch.object(SuppliedEdit, 'checked_title', new_callable=PropertyMock)
    def test_new_title(t, checked_title: PropertyMock) -> None:
        cases = {
            'a title that changes the task': ('A new title', 'A new title'),
            'none, where the task holds that title': ('A task', None),
            'none, where it holds the title spaces aside': (' A task ', None),
            'none, where none is named': (None, None),
        }
        for name, (title, expected) in cases.items():
            with t.subTest(name):
                checked_title.return_value = title
                ret = t.se.new_title(t.node)
                t.assertEqual(ret, expected)

    @patch.object(
        SuppliedEdit, 'checked_description', new_callable=PropertyMock
    )
    def test_new_description(t, checked_description: PropertyMock) -> None:
        t.node.description_lines = ['A line.']
        cases = {
            'lines that change the task': (['A new line.'], ['A new line.']),
            'a clear of the lines the task holds': ([], []),
            'none, where the task holds those lines': (['A line.'], None),
            'none, where none is named': (None, None),
        }
        for name, (lines, expected) in cases.items():
            with t.subTest(name):
                checked_description.return_value = lines
                ret = t.se.new_description(t.node)
                t.assertEqual(ret, expected)

        with t.subTest('none, where it clears a task with no description'):
            t.node.description_lines = []
            checked_description.return_value = []

            ret = t.se.new_description(t.node)

            t.assertIsNone(ret)

    @patch.object(SuppliedEdit, 'supplied', new_callable=PropertyMock)
    def test_refuse_root_fields(t, supplied: PropertyMock) -> None:
        supplied.return_value = MagicMock(spec=['refuse_root_fields'])
        t.se.refuse_root_fields()
        supplied.return_value.refuse_root_fields.assert_called_once_with()

    @patch.object(SuppliedEdit, 'new_description', autospec=True)
    @patch.object(SuppliedEdit, 'new_title', autospec=True)
    def test_delta(
        t,
        new_title: MagicMock,
        new_description: MagicMock,
    ) -> None:
        t.node.description_lines = ['A line.']
        new_title.return_value = 'A new title'
        new_description.return_value = ['A first line.', 'A second line.']

        with t.subTest('each written field, the title, the description'):
            ret = t.se.delta(t.node, {'P': '5', 'DUE': '2026-09-01'})

            new_title.assert_called_once_with(t.se, t.node)
            new_description.assert_called_once_with(t.se, t.node)
            t.assertEqual(
                ret,
                {
                    'P': ['4', '5'],
                    'DUE': [None, '2026-09-01'],
                    'title': ['A task', 'A new title'],
                    'description': [
                        'A line.',
                        'A first line.\nA second line.',
                    ],
                },
            )

        with t.subTest('a cleared description, against null'):
            new_title.return_value = None
            new_description.return_value = []
            ret = t.se.delta(t.node, {})
            t.assertEqual(ret, {'description': ['A line.', None]})

        with t.subTest('nothing that changes the task'):
            new_description.return_value = None
            ret = t.se.delta(t.node, {})
            t.assertEqual(ret, {})


class SuppliedTitleTests(TestCase):
    """Unit tests for battodo.supplied.SuppliedTitle."""

    def setUp(t) -> None:
        t.st = SuppliedTitle('A title')

    def test_checked(t) -> None:
        with t.subTest('a title on one line'):
            ret = t.st.checked
            t.assertEqual(ret, 'A title')

        broken = {
            'a line feed': (
                'A\ntitle',
                "title must hold no line break, not 'A\\ntitle'",
            ),
            'a carriage return': (
                'A\rtitle',
                "title must hold no line break, not 'A\\rtitle'",
            ),
        }
        for name, (text, message) in broken.items():
            with t.subTest(name):
                t.st.text = text

                with t.assertRaises(ValueError) as caught:
                    _ = t.st.checked

                t.assertEqual(str(caught.exception), message)


class SuppliedDescriptionTests(TestCase):
    """Unit tests for battodo.supplied.SuppliedDescription."""

    def setUp(t) -> None:
        t.sd = SuppliedDescription('A line.\n  An indented line.  ')

    def test_lines(t) -> None:
        with t.subTest('each line, stripped of its indent'):
            ret = t.sd.lines
            t.assertEqual(ret, ['A line.', 'An indented line.'])

        with t.subTest('an empty text is no description'):
            t.sd.text = ''
            ret = t.sd.lines
            t.assertEqual(ret, [])

        refused = {
            'a blank line': (
                'A line.\n  \nAnother line.',
                "description line '  ' is blank",
            ),
            'a line that reads as a task': (
                'A line.\n  - [x] A done task',
                "description line '  - [x] A done task' reads as a task line",
            ),
            'a line that reads as a heading': (
                '## A heading',
                "description line '## A heading' reads as a heading",
            ),
            'a line that reads as a comment': (
                '  <!-- A comment -->',
                "description line '  <!-- A comment -->' reads as a comment",
            ),
            'a carriage return': (
                'A line.\r',
                "description line 'A line.\\r' holds a carriage return",
            ),
            'an earlier line is read first': (
                'A line.\r\n## A heading',
                "description line 'A line.\\r' holds a carriage return",
            ),
            'a heading is read before a carriage return': (
                '## A heading\r',
                "description line '## A heading\\r' reads as a heading",
            ),
        }
        for name, (text, message) in refused.items():
            with t.subTest(name):
                t.sd.text = text

                with t.assertRaises(ValueError) as caught:
                    _ = t.sd.lines

                t.assertEqual(str(caught.exception), message)


class DescriptionLineTests(TestCase):
    """Unit tests for battodo.supplied.DescriptionLine."""

    def setUp(t) -> None:
        t.dl = DescriptionLine('  An indented line.  ')

    @patch.object(DescriptionLine, '_refusal', new_callable=PropertyMock)
    def test_text(t, refusal: PropertyMock) -> None:
        with t.subTest('the line, stripped of its indent'):
            refusal.return_value = None
            ret = t.dl.text
            t.assertEqual(ret, 'An indented line.')

        with t.subTest('a refusal names the line as given'):
            refusal.return_value = 'reads as a heading'

            with t.assertRaises(ValueError) as caught:
                _ = t.dl.text

            t.assertEqual(
                str(caught.exception),
                "description line '  An indented line.  ' reads as a heading",
            )

    def test_refusal(t) -> None:
        cases = {
            'a description line': ('  An indented line.  ', None),
            'a blank line': ('  ', 'is blank'),
            'a task line': ('  - [x] A done task', 'reads as a task line'),
            'a heading': ('## A heading', 'reads as a heading'),
            'a comment': ('  <!-- A comment -->', 'reads as a comment'),
            'a carriage return': ('A line.\r', 'holds a carriage return'),
            'a heading before a carriage return': (
                '## A heading\r',
                'reads as a heading',
            ),
        }
        for name, (text, expected) in cases.items():
            with t.subTest(name):
                t.dl._raw_text = text
                ret = t.dl._refusal
                t.assertEqual(ret, expected)

    def test_stripped(t) -> None:
        cases = {
            'the indent and the trailing spaces go': (
                '  An indented line.  ',
                'An indented line.',
            ),
            'a carriage return goes too': ('A line.\r', 'A line.'),
        }
        for name, (text, expected) in cases.items():
            with t.subTest(name):
                t.dl._raw_text = text
                ret = t.dl._stripped
                t.assertEqual(ret, expected)


class SuppliedFieldsTests(TestCase):
    """Unit tests for battodo.supplied.SuppliedFields."""

    def setUp(t) -> None:
        t.sf = SuppliedFields({'TAGS': 'a-tag', 'P': '3'}, TODAY)

    @patch.object(SuppliedFields, 'checked', new_callable=PropertyMock)
    def test_ordered(t, checked: PropertyMock) -> None:
        checked.return_value = {
            'TAGS': 'a-tag',
            'REPEAT': '7d',
            'DUE': '2026-09-01',
            'LOE': '2',
            'P': '3',
        }

        ret = t.sf.ordered

        # The fields as read, in SCHEMA.md order.
        t.assertEqual(
            list(ret.items()),
            [
                ('P', '3'),
                ('LOE', '2'),
                ('DUE', '2026-09-01'),
                ('REPEAT', '7d'),
                ('TAGS', 'a-tag'),
            ],
        )

    @patch.object(SuppliedFields, '_given', new_callable=PropertyMock)
    def test_checked(t, given: PropertyMock) -> None:
        with t.subTest('the supplied fields, each value as read'):
            given.return_value = {'P': '3'}
            ret = t.sf.checked
            t.assertEqual(ret, {'TAGS': 'a-tag', 'P': '3'})

        with t.subTest('a value read in another form replaces the given one'):
            t.sf.fields = {'DUE': 'a due date', 'TAGS': 'a-tag'}
            given.return_value = {'DUE': '2026-09-01'}

            ret = t.sf.checked

            t.assertEqual(
                list(ret.items()),
                [('DUE', '2026-09-01'), ('TAGS', 'a-tag')],
            )

    @patch.object(SuppliedFields, '_read', new_callable=PropertyMock)
    def test_given(t, read: PropertyMock) -> None:
        cases = {
            'each value read, none where none is given': (
                {'P': '3', 'LOE': None, 'DUE': '2026-09-01', 'REPEAT': None},
                {'P': '3', 'DUE': '2026-09-01'},
            ),
            'nothing given: nothing': (
                {'P': None, 'LOE': None, 'DUE': None, 'REPEAT': None},
                {},
            ),
        }
        for name, (found, expected) in cases.items():
            with t.subTest(name):
                read.return_value = found
                ret = t.sf._given
                t.assertEqual(ret, expected)

    @patch(f'{SRC}.parse_date', autospec=True)
    @patch(f'{SRC}.next_due', autospec=True)
    def test_read(t, next_due: MagicMock, parse_date: MagicMock) -> None:
        with t.subTest('each field in order, None where none is given'):
            ret = t.sf._read
            t.assertEqual(
                list(ret.items()),
                [('P', '3'), ('LOE', None), ('DUE', None), ('REPEAT', None)],
            )

        with t.subTest('a due date as the parser reads it'):
            t.sf.fields = {'DUE': 'a due date'}
            parse_date.return_value = date(2026, 9, 1)
            ret = t.sf._read
            t.assertEqual(ret['DUE'], '2026-09-01')

        parse_date.return_value = None
        next_due.side_effect = ValueError('unrecognised REPEAT value')
        refused = {
            'a priority is read first, a recurrence last': (
                {'REPEAT': 'often', 'DUE': 'x', 'LOE': '4', 'P': 'high'},
                "P must be a whole number, not 'high'",
            ),
            'a level of effort is read before a due date': (
                {'REPEAT': 'often', 'DUE': 'x', 'LOE': '4'},
                "LOE must be one of 1, 2, 3, 5, 8, not '4'",
            ),
            'a due date is read before a recurrence': (
                {'REPEAT': 'often', 'DUE': 'x'},
                "DUE must be an ISO date, not 'x'",
            ),
        }
        for name, (fields, message) in refused.items():
            with t.subTest(name):
                t.sf.fields = fields

                with t.assertRaises(ValueError) as caught:
                    _ = t.sf._read

                t.assertEqual(str(caught.exception), message)

    def test_priority(t) -> None:
        with t.subTest('the priority, as given'):
            ret = t.sf.priority
            t.assertEqual(ret, '3')

        with t.subTest('none given: none'):
            t.sf.fields = {}
            ret = t.sf.priority
            t.assertIsNone(ret)

        refused = {
            'a priority that is not a number': (
                'high',
                "P must be a whole number, not 'high'",
            ),
            'an empty priority': ('', "P must be a whole number, not ''"),
        }
        for name, (value, message) in refused.items():
            with t.subTest(name):
                t.sf.fields = {'P': value}

                with t.assertRaises(ValueError) as caught:
                    _ = t.sf.priority

                t.assertEqual(str(caught.exception), message)

    def test_loe(t) -> None:
        for value in ('1', '2', '3', '5', '8'):
            with t.subTest('a level of effort on the scale', value=value):
                t.sf.fields = {'LOE': value}
                ret = t.sf.loe
                t.assertEqual(ret, value)

        with t.subTest('none given: none'):
            t.sf.fields = {}
            ret = t.sf.loe
            t.assertIsNone(ret)

        with t.subTest('a level of effort off the scale'):
            t.sf.fields = {'LOE': '4'}

            with t.assertRaises(ValueError) as caught:
                _ = t.sf.loe

            t.assertEqual(
                str(caught.exception),
                "LOE must be one of 1, 2, 3, 5, 8, not '4'",
            )

    @patch(f'{SRC}.parse_date', autospec=True)
    def test_due(t, parse_date: MagicMock) -> None:
        with t.subTest('a due date, as the parser reads it'):
            t.sf.fields = {'DUE': 'a due date'}
            parse_date.return_value = date(2026, 9, 1)

            ret = t.sf.due

            parse_date.assert_called_once_with('a due date')
            t.assertEqual(ret, '2026-09-01')

        with t.subTest('none given: none, and nothing is read'):
            parse_date.reset_mock()
            t.sf.fields = {}

            ret = t.sf.due

            parse_date.assert_not_called()
            t.assertIsNone(ret)

        with t.subTest('a due date that does not read'):
            t.sf.fields = {'DUE': 'someday'}
            parse_date.return_value = None

            with t.assertRaises(ValueError) as caught:
                _ = t.sf.due

            t.assertEqual(
                str(caught.exception), "DUE must be an ISO date, not 'someday'"
            )

    @patch(f'{SRC}.next_due', autospec=True)
    def test_repeat(t, next_due: MagicMock) -> None:
        with t.subTest('a recurrence, read against the day'):
            t.sf.fields = {'REPEAT': 'a recurrence'}

            ret = t.sf.repeat

            next_due.assert_called_once_with('a recurrence', TODAY)
            t.assertEqual(ret, 'a recurrence')

        with t.subTest('none given: none, and nothing is read'):
            next_due.reset_mock()
            t.sf.fields = {}

            ret = t.sf.repeat

            next_due.assert_not_called()
            t.assertIsNone(ret)

        with t.subTest('a recurrence the scheduler cannot read'):
            t.sf.fields = {'REPEAT': 'often'}
            next_due.side_effect = ValueError('unrecognised REPEAT value')

            with t.assertRaisesRegex(ValueError, 'unrecognised REPEAT'):
                _ = t.sf.repeat

    def test_refuse_root_fields(t) -> None:
        with t.subTest('the fields a subtask carries, a repeat among them'):
            # Nothing to refuse: the call returns.
            t.sf.fields = {
                'LOE': '2',
                'DUE': '2026-09-01',
                'REPEAT': '7d',
                'TAGS': 'a-tag',
            }
            t.sf.refuse_root_fields()

        refused = {
            'a priority, which the top-level task owns': (
                {'P': '3'},
                'P belongs to the top-level task, not to a subtask',
            ),
            'a priority beside a repeat': (
                {'REPEAT': '7d', 'P': '3'},
                'P belongs to the top-level task, not to a subtask',
            ),
        }
        for name, (fields, message) in refused.items():
            with t.subTest(name):
                t.sf.fields = fields

                with t.assertRaises(ValueError) as caught:
                    t.sf.refuse_root_fields()

                t.assertEqual(str(caught.exception), message)


class SuppliedAttributesTests(TestCase):
    """Unit tests for battodo.supplied.SuppliedAttributes."""

    def setUp(t) -> None:
        t.sa = SuppliedAttributes('a_key=a value', 'a note')

    @patch.object(SuppliedAttributes, 'pairs', new_callable=PropertyMock)
    def test_checked(t, pairs: PropertyMock) -> None:
        with t.subTest('each key against its value, in the order given'):
            pairs.return_value = [('cost', '45.00'), ('note', 'a note')]
            ret = t.sa.checked
            t.assertEqual(list(ret.items()), pairs.return_value)

        with t.subTest('no pair: no attribute'):
            pairs.return_value = []
            ret = t.sa.checked
            t.assertEqual(ret, {})

        refused = {
            'a key with a capital': (
                [('Place', 'Main St')],
                "attribute key must be a lowercase identifier, not 'Place'",
            ),
            'a key that starts with a digit': (
                [('1st', 'Main St')],
                "attribute key must be a lowercase identifier, not '1st'",
            ),
            'a key with a line break': (
                [('cost\n', '45.00')],
                "attribute key must be a lowercase identifier, not 'cost\\n'",
            ),
            'an empty value': (
                [('cost', '')],
                "attribute 'cost' must hold a value",
            ),
            'a value with a line feed': (
                [('note', 'a\nnote')],
                "attribute 'note' must hold no line break, not 'a\\nnote'",
            ),
            'a value with a carriage return': (
                [('note', 'a\rnote')],
                "attribute 'note' must hold no line break, not 'a\\rnote'",
            ),
            'a key given twice': (
                [('note', 'a note'), ('cost', '45.00'), ('note', 'another')],
                "attribute 'note' is given twice",
            ),
            'a key is read before its value': (
                [('Place', '')],
                "attribute key must be a lowercase identifier, not 'Place'",
            ),
            'an earlier pair is read first': (
                [('cost', ''), ('Place', 'Main St')],
                "attribute 'cost' must hold a value",
            ),
            'a key given twice before a later key outside the grammar': (
                [('note', 'a note'), ('note', 'another'), ('Place', 'x')],
                "attribute 'note' is given twice",
            ),
        }
        for name, (given, message) in refused.items():
            with t.subTest(name):
                pairs.return_value = given

                with t.assertRaises(ValueError) as caught:
                    _ = t.sa.checked

                t.assertEqual(str(caught.exception), message)

    @patch.object(
        SuppliedAttributes, '_segment_pairs', new_callable=PropertyMock
    )
    def test_pairs(t, segment_pairs: PropertyMock) -> None:
        segment_pairs.return_value = [('a_key', 'a value')]

        with t.subTest('each segment pair, then the note'):
            ret = t.sa.pairs
            t.assertEqual(ret, [('a_key', 'a value'), ('note', 'a note')])

        with t.subTest('the note enters whole, never split'):
            t.sa.note = 'a note, cost=45.00'
            ret = t.sa.pairs
            t.assertEqual(
                ret, [('a_key', 'a value'), ('note', 'a note, cost=45.00')]
            )

        with t.subTest('no note: the segment pairs alone'):
            t.sa.note = None
            ret = t.sa.pairs
            t.assertEqual(ret, [('a_key', 'a value')])

    @patch.object(SuppliedAttributes, 'segments', new_callable=PropertyMock)
    def test_segment_pairs(t, segments: PropertyMock) -> None:
        with t.subTest('each segment split at its first ='):
            segments.return_value = ['a_key=a value', 'sum=1+1=2']
            ret = t.sa._segment_pairs
            t.assertEqual(ret, [('a_key', 'a value'), ('sum', '1+1=2')])

        refused = {
            'a segment with no = is refused': (
                ['a value'],
                "attribute must read key=value, not 'a value'",
            ),
            'an earlier segment is read first': (
                ['a_key=a value', 'one value', 'another'],
                "attribute must read key=value, not 'one value'",
            ),
        }
        for name, (found, message) in refused.items():
            with t.subTest(name):
                segments.return_value = found

                with t.assertRaises(ValueError) as caught:
                    _ = t.sa._segment_pairs

                t.assertEqual(str(caught.exception), message)

    def test_segments(t) -> None:
        with t.subTest('the text the write was given'):
            ret = t.sa.segments
            t.assertEqual(ret, ['a_key=a value'])

        with t.subTest('no text: no segment'):
            t.sa.text = None
            ret = t.sa.segments
            t.assertEqual(ret, [])

        split = {
            'one segment': ('place=Main St', ['place=Main St']),
            'a value holds commas and =': (
                'place=Main St, Suite 4, sum=1+1=2',
                ['place=Main St, Suite 4', 'sum=1+1=2'],
            ),
            'the split takes every space after the comma': (
                'a_key=a value,  cost=45.00',
                ['a_key=a value', 'cost=45.00'],
            ),
            'and needs none': (
                'a_key=a value,cost=45.00',
                ['a_key=a value', 'cost=45.00'],
            ),
            'a line feed after the comma stays': (
                'a_key=a value,\ncost=45.00',
                ['a_key=a value,\ncost=45.00'],
            ),
            'a carriage return after the comma stays': (
                'a_key=a value,\r\ncost=45.00',
                ['a_key=a value,\r\ncost=45.00'],
            ),
            'a comma before a key outside the grammar stays': (
                'a_key=a value, Cost=45.00, 2nd=b',
                ['a_key=a value, Cost=45.00, 2nd=b'],
            ),
            'a comma before a word with no = stays': (
                'a_key=a value, cost',
                ['a_key=a value, cost'],
            ),
            'an empty text is one empty segment': ('', ['']),
        }
        for name, (text, expected) in split.items():
            with t.subTest(name):
                t.sa.text = text
                ret = t.sa.segments
                t.assertEqual(ret, expected)


class AttributePairTests(TestCase):
    """Unit tests for battodo.supplied.AttributePair."""

    def setUp(t) -> None:
        t.ap = AttributePair('cost', '45.00')

    def test_checked(t) -> None:
        with t.subTest('the key against its value'):
            ret = t.ap.checked
            t.assertEqual(ret, ('cost', '45.00'))

        refused = {
            'a key with a capital': (
                ('Place', 'Main St'),
                "attribute key must be a lowercase identifier, not 'Place'",
            ),
            'an empty value': (
                ('cost', ''),
                "attribute 'cost' must hold a value",
            ),
            'a value with a line feed': (
                ('note', 'a\nnote'),
                "attribute 'note' must hold no line break, not 'a\\nnote'",
            ),
            'a value with a carriage return': (
                ('note', 'a\rnote'),
                "attribute 'note' must hold no line break, not 'a\\rnote'",
            ),
            'a key is read before its value': (
                ('Place', ''),
                "attribute key must be a lowercase identifier, not 'Place'",
            ),
        }
        for name, ((key, value), message) in refused.items():
            with t.subTest(name):
                t.ap.key, t.ap.value = key, value

                with t.assertRaises(ValueError) as caught:
                    _ = t.ap.checked

                t.assertEqual(str(caught.exception), message)


class AttributeSegmentTests(TestCase):
    """Unit tests for battodo.supplied.AttributeSegment."""

    def setUp(t) -> None:
        t.as_ = AttributeSegment('a_key=a value')

    def test_pair(t) -> None:
        split = {
            'the key against its value': (
                'a_key=a value',
                ('a_key', 'a value'),
            ),
            'split at the first =': ('sum=1+1=2', ('sum', '1+1=2')),
            'an empty value': ('cost=', ('cost', '')),
        }
        for name, (text, expected) in split.items():
            with t.subTest(name):
                t.as_.text = text
                ret = t.as_.pair
                t.assertEqual(ret, expected)

        with t.subTest('a segment with no = is refused'):
            t.as_.text = 'a value'

            with t.assertRaises(ValueError) as caught:
                _ = t.as_.pair

            t.assertEqual(
                str(caught.exception),
                "attribute must read key=value, not 'a value'",
            )
