"""Contract tests for the write objects, against real files.

Inputs are real directories holding real todo lists. Each object
derives the list text, the log entries and the journal events from
them, and this layer asserts those values. Interaction checks stay in
the isolation tests beside the code.
"""

from datetime import date
from os import utime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import TestCase

from battodo.conf import TZ
from battodo.journal import Journal
from battodo.mutate import (
    Addition,
    Annotation,
    Backfill,
    Changeset,
    CompletedLog,
    Completion,
    Event,
    ListError,
    Reopen,
    SubtaskAddition,
    Update,
)
from battodo.repeat import RepeatError
from battodo.selector import SelectionError
from battodo.task import Task

TODAY = date(2026, 8, 8)
# A completion day the user gives, earlier than TODAY.
GIVEN_DAY = date(2026, 8, 1)
# A list holding every case the writes tell apart. The titles name the
# role each line plays.
A_LIST = """# A list

## Open

- [ ] A task [P:4] [LOE:8] [ADDED:2026-07-06] [ID:9o71lx]
      A note that stays put.
  - [ ] A subtask of it [LOE:2]
  - [ ] A checklist item
- [ ] A task with no id [P:2]
- [ ] A recurring task [P:3] [DUE:2026-08-05] [REPEAT:7d] [ID:rr01ab]
  - [ ] A subtask that does not recur [LOE:1]

- [ ] A task between blank lines [P:1] [ID:bb01cd]

## Done
"""
A_TASK = '- [ ] A task [P:4] [LOE:8] [ADDED:2026-07-06] [ID:9o71lx]'
A_CHILD = '  - [ ] A subtask of it [LOE:2]'
NO_ID_TASK = '- [ ] A task with no id [P:2]'
RENAMED_TASK = (
    '- [ ] A renamed task [P:5] [LOE:8] [ADDED:2026-07-06] [ID:9o71lx] '
    '[DUE:2026-09-01]'
)
# A description, and its lines as a top-level task carries them.
DESCRIPTION = 'A first line.\n  A second line.'
DESCRIPTION_LINES = ['      A first line.', '      A second line.']
# A recurring task with a description line and a child, before and
# after its completion on TODAY.
DESCRIBED_RECURRENCE = (
    '## Open\n'
    '- [ ] A described recurring task [DUE:2026-08-05] [REPEAT:7d] '
    '[ID:dr01ab]\n'
    '      A description line.\n'
    '  - [ ] A subtask that does not recur [LOE:1]\n'
)
RESCHEDULED_RECURRENCE = (
    '## Open\n'
    '- [ ] A described recurring task [DUE:2026-08-15] [REPEAT:7d] '
    '[ID:dr01ab] [ADDED:2026-08-08]\n'
    '      A description line.\n'
)
# The children of A task, as its snapshot records them.
A_TASK_CHILDREN = [
    {'title': 'A subtask of it', 'done': False, 'fields': {'LOE': '2'}},
    {'title': 'A checklist item', 'done': False, 'fields': {}},
]
# The attributes of a note.
A_NOTE = {'note': 'Waiting on the vendor'}
# A second list, its open section empty.
ANOTHER_LIST = '# Another list\n\n## Open\n'
# A list whose one task carries an `[ID:]` with nothing in it.
EMPTY_ID_TASK = '- [ ] A task with an empty id [P:2] [ID:]'
EMPTY_ID_LIST = f'## Open\n\n{EMPTY_ID_TASK}\n'
# A list whose task has no id and two checklist items, so a write to one
# item leaves the task in the list. The titles name the role each line
# plays.
OWNER_LIST = (
    '## Open\n\n- [ ] A checklist owner with no id [P:3]\n'
    '  - [ ] A checklist item to write\n'
    '  - [ ] A checklist item that stays open\n'
)
# The owner as the file states it before a write.
OWNER_SNAPSHOT = {
    'list': 'an-owner-list',
    'title': 'A checklist owner with no id',
    'done': False,
    'fields': {'P': '3'},
    'children': [
        {'title': 'A checklist item to write', 'done': False, 'fields': {}},
        {
            'title': 'A checklist item that stays open',
            'done': False,
            'fields': {},
        },
    ],
}


# A list of chores with repeating steps. The titles name the role each
# line plays.
STEPPED_LIST = (
    '## Open\n'
    '- [ ] A chore [P:2] [ID:ch01ab]\n'
    '  - [ ] A repeating step [DUE:2026-08-05] [REPEAT:7d] [ID:rs01ab]\n'
    '  - [ ] A plain step [LOE:1] [ID:ps01ab]\n'
    '  - [ ] A repeating step with a step [DUE:2026-08-05] [REPEAT:1w] '
    '[ID:rw01ab]\n'
    '    - [ ] A step below it [LOE:2] [ID:sb01ab]\n'
    '- [ ] A chore with one open step [P:1] [ID:co01ab]\n'
    '  - [ ] Its only open step [DUE:2026-08-05] [REPEAT:monthly:5] '
    '[ID:os01ab]\n'
    '  - [x] A finished step [LOE:1]\n'
    '- [ ] A chore with a deep step [P:1] [ID:cd01ab]\n'
    '  - [ ] A plain step above [LOE:1] [ID:pa01ab]\n'
    '    - [ ] A repeating step below [DUE:2026-08-05] [REPEAT:3d] '
    '[ID:rb01ab]\n'
)


# A list whose top-level task keeps a closed subtask, and a closed
# subtask below that. The titles name the role each line plays.
HELD_LIST = (
    '## Open\n\n'
    '- [ ] A task with a closed step [P:2] [ID:hp01ab]\n'
    '  - [x] A closed step [LOE:1] [ID:ds02cd]\n'
    '    - [x] A closed step below it [LOE:1] [ID:db03ef]\n'
)
# The last snapshot of a finished top-level task with a description, a
# subtask and a checklist item.
FINISHED_SNAPSHOT = {
    'title': 'A finished task',
    'done': False,
    'fields': {'P': '2', 'ADDED': '2026-07-01', 'ID': 'ft01ab'},
    'description': 'Its note.',
    'children': [
        {
            'title': 'Its subtask',
            'done': True,
            'fields': {'LOE': '1', 'ID': 'fs02cd'},
        },
        {'title': 'Its checklist item', 'done': True, 'fields': {}},
    ],
    'list': 'a-list',
}
# The finished task as a reopen restores it: closed, each child closed.
FINISHED_BLOCK = [
    '- [x] A finished task [P:2] [ADDED:2026-07-01] [ID:ft01ab]',
    '      Its note.',
    '  - [x] Its subtask [LOE:1] [ID:fs02cd]',
    '  - [x] Its checklist item',
]
# Where a block restored to `a-list` goes: after its last open entry.
RESTORED_INDEX = 13
# Each event of the closed-task journal: type, stream and payload.
CLOSED_EVENTS = (
    (
        'TaskCompleted',
        'task/fs02cd',
        {
            'delta': {'done': [False, True]},
            'snapshot': {
                'title': 'Its subtask',
                'done': False,
                'fields': {'LOE': '1', 'ID': 'fs02cd'},
                'list': 'a-list',
            },
            'ancestry': 'A finished task > Its subtask',
        },
    ),
    (
        'TaskCompleted',
        'task/ft01ab',
        {
            'delta': {'done': [False, True]},
            'snapshot': {
                'title': 'Its checklist item',
                'done': False,
                'fields': {},
                'list': 'a-list',
            },
            'ancestry': 'A finished task > Its checklist item',
            'checklist_item': True,
        },
    ),
    (
        'TaskCompleted',
        'task/ft01ab',
        {
            'delta': {'done': [False, True]},
            'snapshot': FINISHED_SNAPSHOT,
            'ancestry': 'A finished task',
        },
    ),
    (
        'TaskScratched',
        'task/sc01ab',
        {
            'delta': {'removed': [False, True]},
            'snapshot': {
                'title': 'A scratched task',
                'done': False,
                'fields': {'P': '1', 'ID': 'sc01ab'},
                'list': 'a-list',
            },
            'ancestry': 'A scratched task',
        },
    ),
    (
        'TaskCompleted',
        'task/db03ef',
        {
            'delta': {'done': [False, True]},
            'snapshot': {
                'title': 'A closed step below it',
                'done': False,
                'fields': {'LOE': '1', 'ID': 'db03ef'},
                'list': 'a-held-list',
            },
            'ancestry': (
                'A task with a closed step > A closed step > '
                'A closed step below it'
            ),
        },
    ),
    (
        'TaskCompleted',
        'task/ds02cd',
        {
            'delta': {'done': [False, True]},
            'snapshot': {
                'title': 'A closed step',
                'done': False,
                'fields': {'LOE': '1', 'ID': 'ds02cd'},
                'list': 'a-held-list',
            },
            'ancestry': 'A task with a closed step > A closed step',
        },
    ),
    (
        'TaskAdded',
        'task/ls01ab',
        {
            'delta': {},
            'snapshot': {'title': 'A lost subtask', 'fields': {'LOE': '1'}},
            'parent': 'lp00ab',
        },
    ),
    (
        'TaskCompleted',
        'task/ls01ab',
        {
            'delta': {'done': [False, True]},
            'snapshot': {
                'title': 'A lost subtask',
                'fields': {'LOE': '1', 'ID': 'ls01ab'},
                'list': 'a-list',
            },
            'ancestry': 'A lost parent > A lost subtask',
        },
    ),
    (
        'TaskCompleted',
        'task/tw01ab',
        {
            'delta': {'done': [False, True]},
            'snapshot': {
                'title': 'A twin task',
                'fields': {},
                'list': 'a-list',
            },
            'ancestry': 'A twin task',
            'completed_on': '2026-08-01',
        },
    ),
    (
        'TaskCompleted',
        'task/tw02cd',
        {
            'delta': {'done': [False, True]},
            'snapshot': {
                'title': 'A twin task',
                'fields': {},
                'list': 'a-list',
            },
            'ancestry': 'A twin task',
            'completed_on': '2026-08-03',
        },
    ),
)


class AdditionTests(TestCase):
    """Contract tests for battodo.mutate.Addition."""

    maxDiff = None

    def setUp(t) -> None:
        t.source = a_source(t)
        t.ad = Addition(
            t.source,
            'a-list',
            'A new task',
            {'TAGS': 'a-tag', 'P': '3'},
            TODAY,
        )

    def test_write(t) -> None:
        t.ad.write()

        written = (t.source / 'a-list.md').read_text(encoding='utf-8')

        # The list holds the text the add derives, the journal its event.
        t.assertEqual(written, t.ad.text)
        t.assertEqual(journaled(t.source), as_journaled(t.ad.events))

    def test_path(t) -> None:
        with t.subTest('the list whose file the name stems'):
            ret = t.ad.path
            t.assertEqual(ret, t.source / 'a-list.md')

        with t.subTest('a name no list carries'):
            missing = Addition(t.source, 'a-missing-list', 'X', {}, TODAY)

            with t.assertRaises(ListError) as caught:
                _ = missing.path

            t.assertEqual(
                str(caught.exception),
                f"no list named 'a-missing-list' in {t.source}; "
                'available: a-list, another-list',
            )

    def test_text(t) -> None:
        with t.subTest('the task last in Open, every other line kept'):
            ret = t.ad.text
            t.assertEqual(ret, with_line(A_LIST, 13, t.ad.entry))

        with t.subTest('an empty open section takes it under its heading'):
            empty = Addition(t.source, 'another-list', 'X', {}, TODAY)
            ret = empty.text
            t.assertEqual(ret, f'{ANOTHER_LIST}{empty.entry}\n')

        with t.subTest('a description goes under the task line'):
            described = described_addition(t.source, DESCRIPTION)

            ret = described.text

            lines = [described.entry, *DESCRIPTION_LINES]
            t.assertEqual(ret, with_lines(A_LIST, 13, lines))

        with t.subTest('an empty description writes no line'):
            undescribed = described_addition(t.source, '')

            ret = undescribed.text

            t.assertEqual(ret, with_line(A_LIST, 13, undescribed.entry))

        with t.subTest('a description with a blank line is refused'):
            blank = described_addition(t.source, 'A line.\n\nA line.')

            with t.assertRaises(ValueError) as caught:
                _ = blank.text

            t.assertEqual(
                str(caught.exception),
                "description line '' is blank",
            )

        refused = {
            'a priority that is not a number': (
                {'P': 'high'},
                "P must be a whole number, not 'high'",
            ),
            'a level of effort off the scale': (
                {'LOE': '4'},
                "LOE must be one of 1, 2, 3, 5, 8, not '4'",
            ),
            'a due date that does not read': (
                {'DUE': 'someday'},
                "DUE must be an ISO date, not 'someday'",
            ),
            'a recurrence the scheduler cannot read': (
                {'REPEAT': 'often'},
                "unrecognised REPEAT value: 'often'",
            ),
        }
        for name, (fields, message) in refused.items():
            with t.subTest(name):
                refusal = Addition(t.source, 'a-list', 'X', fields, TODAY)

                with t.assertRaises(ValueError) as caught:
                    _ = refusal.text

                t.assertEqual(str(caught.exception), message)

        broken = {
            'a title with a line feed': (
                'A new\ntask',
                "title must hold no line break, not 'A new\\ntask'",
            ),
            'a title with a carriage return': (
                'A new\rtask',
                "title must hold no line break, not 'A new\\rtask'",
            ),
        }
        for name, (title, message) in broken.items():
            with t.subTest(name):
                refusal = Addition(t.source, 'a-list', title, {}, TODAY)

                with t.assertRaises(ValueError) as caught:
                    _ = refusal.text

                t.assertEqual(str(caught.exception), message)

    def test_entry(t) -> None:
        ret = t.ad.entry
        # The supplied fields in SCHEMA.md order, then the stamps.
        t.assertRegex(
            ret,
            r'^- \[ \] A new task \[P:3\] \[TAGS:a-tag\] '
            r'\[ADDED:2026-08-08\] \[ID:[0-9a-z]{6}\]$',
        )

    def test_events(t) -> None:
        with t.subTest('one TaskAdded, on the stream of the new task'):
            task_id = id_on(t.ad.entry)

            (ret,) = t.ad.events

            t.assertEqual(
                ret,
                (
                    'TaskAdded',
                    f'task/{task_id}',
                    {
                        'delta': {
                            'P': [None, '3'],
                            'TAGS': [None, 'a-tag'],
                            'ADDED': [None, '2026-08-08'],
                            'ID': [None, task_id],
                        },
                        'snapshot': {
                            'list': 'a-list',
                            'title': 'A new task',
                            'done': False,
                            'fields': {
                                'P': '3',
                                'TAGS': 'a-tag',
                                'ADDED': '2026-08-08',
                                'ID': task_id,
                            },
                        },
                    },
                ),
            )

        with t.subTest('the snapshot holds the description, not the delta'):
            described = described_addition(t.source, DESCRIPTION)

            (ret,) = described.events

            t.assertEqual(
                ret.payload['snapshot']['description'],
                'A first line.\nA second line.',
            )
            t.assertNotIn('description', ret.payload['delta'])

        with t.subTest('the attributes go on its event'):
            added = Addition(
                t.source,
                'a-list',
                'A new task',
                {},
                TODAY,
                attrs={'cost': '45.00'},
            )

            (event,) = added.events

            t.assertEqual(event.payload['attrs'], {'cost': '45.00'})

    def test_block(t) -> None:
        with t.subTest('the task line alone, where it has no description'):
            ret = t.ad.block
            t.assertEqual(ret, t.ad.entry)

        with t.subTest('and its description lines under it'):
            described = described_addition(t.source, DESCRIPTION)

            ret = described.block

            lines = [described.entry, *DESCRIPTION_LINES]
            t.assertEqual(ret, '\n'.join(lines))

    def test_description_lines(t) -> None:
        with t.subTest('none, where no description is given'):
            ret = t.ad.description_lines
            t.assertEqual(ret, [])

        with t.subTest('the lines of the description, stripped'):
            described = described_addition(t.source, DESCRIPTION)
            ret = described.description_lines
            t.assertEqual(ret, ['A first line.', 'A second line.'])


class SubtaskAdditionTests(TestCase):
    """Contract tests for battodo.mutate.SubtaskAddition."""

    maxDiff = None

    def setUp(t) -> None:
        t.source = a_source(t)
        t.sa = SubtaskAddition(
            Task(t.source, '9o71lx', TODAY),
            'a-list',
            'A new subtask',
            {'LOE': '2'},
        )

    def test_write(t) -> None:
        t.sa.write()

        written = (t.source / 'a-list.md').read_text(encoding='utf-8')

        # The list holds the text the add derives, the journal its event.
        t.assertEqual(written, t.sa.text)
        t.assertEqual(journaled(t.source), as_journaled(t.sa.events))

    def test_path(t) -> None:
        ret = t.sa.path
        t.assertEqual(ret, t.source / 'a-list.md')

    def test_text(t) -> None:
        with t.subTest('last in its parent block, one level deeper'):
            ret = t.sa.text
            t.assertEqual(ret, with_line(A_LIST, 8, t.sa.entry))

        with t.subTest('a parent with no id is stamped first'):
            unidentified = subtask(t.source, 'A task with no id')

            ret = unidentified.text

            stamp = f'{NO_ID_TASK} [ID:{unidentified.parent_id}]'
            expected = A_LIST.replace(NO_ID_TASK, stamp)
            t.assertEqual(ret, with_line(expected, 9, unidentified.entry))

        with t.subTest('a description goes under the subtask line'):
            described = subtask(t.source, '9o71lx', description=DESCRIPTION)

            ret = described.text

            lines = [
                described.entry,
                '        A first line.',
                '        A second line.',
            ]
            t.assertEqual(ret, with_lines(A_LIST, 8, lines))

        with t.subTest('a subtask takes a repeat of its own'):
            repeating = subtask(t.source, '9o71lx', fields={'REPEAT': '7d'})
            ret = repeating.entry
            t.assertRegex(
                ret,
                r'^  - \[ \] A new subtask \[REPEAT:7d\] \[ID:[0-9a-z]{6}\]$',
            )

        with t.subTest('a subtask nests one level under a subtask'):
            deeper = subtask(t.source, 'A subtask of it')
            ret = deeper.entry
            t.assertRegex(
                ret,
                r'^    - \[ \] A new subtask \[ID:[0-9a-z]{6}\]$',
            )

        refused = {
            'a list no file carries': (
                subtask(t.source, '9o71lx', list_name='a-missing-list'),
                ListError,
                "no list named 'a-missing-list'",
            ),
            'a field only the top-level task carries': (
                subtask(t.source, '9o71lx', fields={'P': '3'}),
                ValueError,
                'P belongs to the top-level task, not to a subtask',
            ),
            'a parent in another list': (
                subtask(t.source, '9o71lx', list_name='another-list'),
                ValueError,
                "'9o71lx' names a task in a-list.md, not another-list.md",
            ),
            'a checklist item, which a field would promote': (
                subtask(t.source, 'A checklist item'),
                ValueError,
                "'A checklist item' is a checklist item",
            ),
            'a parent no selector reaches': (
                subtask(t.source, 'nothing'),
                SelectionError,
                "no open task matches 'nothing'",
            ),
            'a title with a line break': (
                subtask(t.source, '9o71lx', title='A new\nsubtask'),
                ValueError,
                'title must hold no line break',
            ),
            'a description line that reads as a heading': (
                subtask(t.source, '9o71lx', description='## A heading'),
                ValueError,
                "description line '## A heading' reads as a heading",
            ),
        }
        for name, (refusal, error, message) in refused.items():
            with t.subTest(name), t.assertRaisesRegex(error, message):
                _ = refusal.text

        with t.subTest('a parent whose id is empty is stamped too'):
            unrecorded = under_an_empty_id(t.source)

            ret = unrecorded.text

            stamp = EMPTY_ID_TASK.replace(
                '[ID:]',
                f'[ID:{unrecorded.parent_id}]',
            )
            t.assertEqual(ret, f'## Open\n\n{stamp}\n{unrecorded.entry}\n')

    def test_entry(t) -> None:
        ret = t.sa.entry
        t.assertRegex(ret, r'^  - \[ \] A new subtask \[LOE:2\] \[ID:\w{6}\]$')

    def test_block(t) -> None:
        with t.subTest('the subtask line alone, where it has no description'):
            ret = t.sa.block
            t.assertEqual(ret, t.sa.entry)

        with t.subTest('and its description lines under it'):
            described = subtask(t.source, '9o71lx', description='A line.')
            ret = described.block
            t.assertEqual(ret, f'{described.entry}\n        A line.')

    def test_description_lines(t) -> None:
        with t.subTest('none, where no description is given'):
            ret = t.sa.description_lines
            t.assertEqual(ret, [])

        with t.subTest('the lines of the description, stripped'):
            described = subtask(t.source, '9o71lx', description=DESCRIPTION)
            ret = described.description_lines
            t.assertEqual(ret, ['A first line.', 'A second line.'])

    def test_events(t) -> None:
        with t.subTest('one TaskAdded, which names the parent by id'):
            child_id = id_on(t.sa.entry)

            (ret,) = t.sa.events

            t.assertEqual(
                ret,
                (
                    'TaskAdded',
                    f'task/{child_id}',
                    {
                        'delta': {'LOE': [None, '2'], 'ID': [None, child_id]},
                        'snapshot': {
                            'list': 'a-list',
                            'title': 'A new subtask',
                            'done': False,
                            'fields': {'LOE': '2', 'ID': child_id},
                        },
                        'parent': '9o71lx',
                    },
                ),
            )

        with t.subTest('the snapshot carries the description'):
            described = subtask(t.source, '9o71lx', description=DESCRIPTION)

            (event,) = described.events

            t.assertEqual(
                event.payload['snapshot']['description'],
                'A first line.\nA second line.',
            )

        with t.subTest('a parent stamped first records the stamp first'):
            unidentified = subtask(t.source, 'A task with no id')

            stamp, added = unidentified.events

            parent_id = unidentified.parent_id
            t.assertEqual(
                stamp,
                (
                    'TaskUpdated',
                    f'task/{parent_id}',
                    {
                        'delta': {'ID': [None, parent_id]},
                        'snapshot': {
                            'list': 'a-list',
                            'title': 'A task with no id',
                            'done': False,
                            'fields': {'P': '2'},
                        },
                    },
                ),
            )
            t.assertEqual(added.payload['parent'], parent_id)

        with t.subTest('the attributes go on the TaskAdded alone'):
            unidentified = SubtaskAddition(
                Task(t.source, 'A task with no id', TODAY),
                'a-list',
                'A new subtask',
                {},
                attrs={'cost': '45.00'},
            )

            stamp, added = unidentified.events

            t.assertNotIn('attrs', stamp.payload)
            t.assertEqual(added.payload['attrs'], {'cost': '45.00'})

        with t.subTest('a parent whose id is empty is stamped first too'):
            unrecorded = under_an_empty_id(t.source)

            streams = [event.stream for event in unrecorded.events]

            t.assertEqual(
                streams,
                [
                    f'task/{unrecorded.parent_id}',
                    f'task/{unrecorded.task_id}',
                ],
            )


class UpdateTests(TestCase):
    """Contract tests for battodo.mutate.Update."""

    maxDiff = None

    def setUp(t) -> None:
        t.source = a_source(t)
        t.up = Update(
            Task(t.source, '9o71lx', TODAY),
            {'P': '5', 'DUE': '2026-09-01'},
            title='A renamed task',
        )

    def test_write(t) -> None:
        t.up.write()

        written = (t.source / 'a-list.md').read_text(encoding='utf-8')

        # The list holds the text the update derives, the journal its
        # event.
        t.assertEqual(written, t.up.text)
        t.assertEqual(journaled(t.source), as_journaled(t.up.events))

    def test_text(t) -> None:
        with t.subTest('the fields and title written, every other line kept'):
            ret = t.up.text
            t.assertEqual(ret, A_LIST.replace(A_TASK, RENAMED_TASK))

        with t.subTest('a task with no id is given one'):
            unidentified = Update(
                Task(t.source, 'A task with no id', TODAY),
                {'P': '5'},
            )

            ret = unidentified.text

            line = f'- [ ] A task with no id [P:5] [ID:{unidentified.task_id}]'
            t.assertEqual(ret, A_LIST.replace(NO_ID_TASK, line))

        with t.subTest('a description replaces the description lines'):
            described = described_update(t.source, '9o71lx', DESCRIPTION)

            ret = described.text

            replaced = with_lines(without(A_LIST, 5), 5, DESCRIPTION_LINES)
            t.assertEqual(ret, replaced)

        with t.subTest('an empty description clears them'):
            cleared = described_update(t.source, '9o71lx', '')
            ret = cleared.text
            t.assertEqual(ret, without(A_LIST, 5))

        with t.subTest('a description of None clears them too'):
            cleared = described_update(t.source, '9o71lx', 'None')
            ret = cleared.text
            t.assertEqual(ret, without(A_LIST, 5))

        with t.subTest('a task with none takes them before its children'):
            described = described_update(t.source, 'rr01ab', DESCRIPTION)
            ret = described.text
            t.assertEqual(ret, with_lines(A_LIST, 10, DESCRIPTION_LINES))

        with t.subTest('a new repeat replaces the one the task carries'):
            changed = Update(
                Task(t.source, 'rr01ab', TODAY), {'REPEAT': '14d'}
            )
            ret = changed.text
            t.assertEqual(ret, A_LIST.replace('[REPEAT:7d]', '[REPEAT:14d]'))

        with t.subTest('a repeat of None clears it, the due date kept'):
            cleared = Update(
                Task(t.source, 'rr01ab', TODAY), {'REPEAT': 'None'}
            )
            ret = cleared.text
            t.assertEqual(ret, A_LIST.replace(' [REPEAT:7d]', ''))

        with t.subTest('a repeat on a subtask, the due date kept'):
            changed = Update(
                Task(a_stepped_source(t), 'ps01ab', TODAY), {'REPEAT': '1w'}
            )
            ret = changed.text
            t.assertEqual(
                ret,
                STEPPED_LIST.replace(
                    '[LOE:1] [ID:ps01ab]', '[LOE:1] [ID:ps01ab] [REPEAT:1w]'
                ),
            )

        with t.subTest('and None clears the repeat of a subtask'):
            cleared = Update(
                Task(a_stepped_source(t), 'rs01ab', TODAY), {'REPEAT': 'None'}
            )
            ret = cleared.text
            t.assertEqual(ret, STEPPED_LIST.replace(' [REPEAT:7d]', ''))

        refused = {
            'an update that names nothing': (
                Update(Task(t.source, '9o71lx', TODAY), {}),
                ValueError,
                'nothing to update',
            ),
            'a value that does not read': (
                Update(Task(t.source, '9o71lx', TODAY), {'DUE': 'x'}),
                ValueError,
                "DUE must be an ISO date, not 'x'",
            ),
            'an empty repeat, which is no clear': (
                Update(Task(t.source, 'rr01ab', TODAY), {'REPEAT': ''}),
                RepeatError,
                "unrecognised REPEAT value: ''",
            ),
            'the repeat the task carries, and no other change': (
                Update(Task(t.source, 'rr01ab', TODAY), {'REPEAT': '7d'}),
                ValueError,
                'nothing to update',
            ),
            'a clear of a task with no repeat, and no other change': (
                Update(Task(t.source, '9o71lx', TODAY), {'REPEAT': 'None'}),
                ValueError,
                'nothing to update',
            ),
            'a clear of a subtask with no repeat, and no other change': (
                Update(
                    Task(t.source, 'A subtask that does not', TODAY),
                    {'REPEAT': 'None'},
                ),
                ValueError,
                'nothing to update',
            ),
            'a field only the top-level task carries': (
                Update(Task(t.source, 'A subtask of', TODAY), {'P': '5'}),
                ValueError,
                'P belongs to the top-level task',
            ),
            'an open task with its subtasks': (
                Update(
                    Task(t.source, '9o71lx', TODAY),
                    {},
                    with_subtasks=True,
                ),
                ValueError,
                "'9o71lx' names an open task: --with-subtasks reopens",
            ),
            'a checklist item, which a field would promote': (
                Update(
                    Task(t.source, 'A checklist item', TODAY),
                    {'DUE': '2026-09-01'},
                ),
                ValueError,
                'is a checklist item',
            ),
            'a selector that names no task': (
                Update(Task(t.source, 'nothing', TODAY), {'P': '5'}),
                SelectionError,
                "no open task matches 'nothing'",
            ),
            'a list that is not there': (
                Update(
                    Task(t.source, '9o71lx', TODAY),
                    {},
                    list_name='wrk',
                ),
                ListError,
                "no list named 'wrk'",
            ),
            'the list the task is in, and no other change': (
                Update(
                    Task(t.source, '9o71lx', TODAY),
                    {},
                    list_name='a-list',
                ),
                ValueError,
                'nothing to update',
            ),
            'a subtask, which moves with its top-level task': (
                Update(
                    Task(t.source, 'A subtask of it', TODAY),
                    {},
                    list_name='another-list',
                ),
                ValueError,
                "'A subtask of it' is a subtask",
            ),
            'a title with a line break': (
                Update(
                    Task(t.source, '9o71lx', TODAY),
                    {},
                    title='A renamed\rtask',
                ),
                ValueError,
                'title must hold no line break',
            ),
            'a description line that reads as a task': (
                described_update(t.source, '9o71lx', '- [ ] A task'),
                ValueError,
                r"description line '- \[ \] A task' reads as a task line",
            ),
            'a checklist item, which takes no description': (
                described_update(t.source, 'A checklist item', 'A line.'),
                ValueError,
                'is a checklist item',
            ),
        }
        for name, (refusal, error, message) in refused.items():
            with t.subTest(name), t.assertRaisesRegex(error, message):
                _ = refusal.text

    def test_entry(t) -> None:
        ret = t.up.entry
        t.assertEqual(ret, RENAMED_TASK)

    def test_lists(t) -> None:
        with t.subTest('an update in place writes the list of the task'):
            ret = t.up.lists
            t.assertEqual(ret, {t.source / 'a-list.md': t.up.text})

        with t.subTest('a move takes the whole block to the other list'):
            moved = Update(
                Task(t.source, '9o71lx', TODAY),
                {'P': '5'},
                list_name='another-list',
            )

            ret = moved.lists

            block = [
                A_TASK.replace('[P:4]', '[P:5]'),
                '      A note that stays put.',
                A_CHILD,
                '  - [ ] A checklist item',
            ]
            t.assertEqual(
                ret,
                {
                    t.source / 'a-list.md': without(A_LIST, 4, 5, 6, 7),
                    t.source / 'another-list.md': '\n'.join(
                        ['# Another list', '', '## Open', *block, '']
                    ),
                },
            )

    def test_events(t) -> None:
        with t.subTest('one TaskUpdated: what changed, and from what'):
            ret = t.up.events
            t.assertEqual(
                ret,
                [
                    (
                        'TaskUpdated',
                        'task/9o71lx',
                        {
                            'delta': {
                                'P': ['4', '5'],
                                'DUE': [None, '2026-09-01'],
                                'title': ['A task', 'A renamed task'],
                            },
                            'snapshot': {
                                'list': 'a-list',
                                'title': 'A task',
                                'done': False,
                                'fields': {
                                    'P': '4',
                                    'LOE': '8',
                                    'ADDED': '2026-07-06',
                                    'ID': '9o71lx',
                                },
                                'description': 'A note that stays put.',
                                'children': A_TASK_CHILDREN,
                            },
                        },
                    )
                ],
            )

        with t.subTest('a description, against the one it replaced'):
            described = described_update(t.source, '9o71lx', DESCRIPTION)

            (event,) = described.events

            t.assertEqual(
                event.payload['delta'],
                {
                    'description': [
                        'A note that stays put.',
                        'A first line.\nA second line.',
                    ],
                },
            )

        with t.subTest('a cleared description, against null'):
            cleared = described_update(t.source, '9o71lx', '')

            (event,) = cleared.events

            t.assertEqual(
                event.payload['delta'],
                {'description': ['A note that stays put.', None]},
            )

        with t.subTest('a cleared repeat, against null'):
            cleared = Update(
                Task(t.source, 'rr01ab', TODAY), {'REPEAT': 'None'}
            )

            (event,) = cleared.events

            t.assertEqual(event.stream, 'task/rr01ab')
            t.assertEqual(event.payload['delta'], {'REPEAT': ['7d', None]})

        with t.subTest('a repeat that is no change stays out of the delta'):
            kept = Update(
                Task(t.source, 'rr01ab', TODAY),
                {'P': '5', 'REPEAT': '7d'},
            )
            absent = Update(
                Task(t.source, '9o71lx', TODAY),
                {'P': '5', 'REPEAT': 'None'},
            )

            (kept_event,) = kept.events
            (absent_event,) = absent.events

            t.assertEqual(kept_event.payload['delta'], {'P': ['3', '5']})
            t.assertEqual(absent_event.payload['delta'], {'P': ['4', '5']})

        with t.subTest('a subtask records where it sits, and its new id'):
            child = Update(
                Task(t.source, 'A subtask of it', TODAY),
                {'DUE': '2026-09-01'},
            )

            (event,) = child.events

            t.assertEqual(event.stream, f'task/{child.task_id}')
            t.assertEqual(event.payload['delta']['ID'], [None, child.task_id])
            t.assertEqual(
                event.payload['ancestry'],
                'A task > A subtask of it',
            )

        with t.subTest('the attributes go on its event'):
            updated = Update(
                Task(t.source, '9o71lx', TODAY),
                {'P': '5'},
                attrs={'cost': '45.00'},
            )

            (event,) = updated.events

            t.assertEqual(event.payload['attrs'], {'cost': '45.00'})

        with t.subTest('a move records the list it leaves and joins'):
            moved = Update(
                Task(t.source, '9o71lx', TODAY),
                {},
                list_name='another-list',
            )

            (event,) = moved.events

            t.assertEqual(
                event.payload['delta'],
                {'list': ['a-list', 'another-list']},
            )
            t.assertEqual(event.payload['snapshot']['list'], 'a-list')


class ReopenTests(TestCase):
    """Contract tests for battodo.mutate.Reopen."""

    maxDiff = None

    def setUp(t) -> None:
        t.source = a_closed_source(t)
        t.ro = reopen_of(t.source, 'ft01ab', {'P': '5'})

    def test_write(t) -> None:
        # Read before the write: once written, the task is open.
        text, events = t.ro.text, t.ro.events
        before = journaled(t.source)

        t.ro.write()

        written = (t.source / 'a-list.md').read_text(encoding='utf-8')
        # The list holds the text the reopen derives, the journal its
        # events after the events it read.
        t.assertEqual(written, text)
        t.assertEqual(journaled(t.source), before + as_journaled(events))

    def test_text(t) -> None:
        opened = [
            FINISHED_BLOCK[0].replace('[x]', '[ ]').replace('[P:2]', '[P:5]'),
            *FINISHED_BLOCK[1:],
        ]
        cases = {
            'a top-level task, open, its children closed': (
                t.ro,
                'a-list.md',
                with_lines(A_LIST, RESTORED_INDEX, opened),
            ),
            'a reopen that names nothing reopens the task unchanged': (
                reopen_of(t.source, 'A finished task'),
                'a-list.md',
                with_lines(
                    A_LIST,
                    RESTORED_INDEX,
                    [FINISHED_BLOCK[0].replace('[x]', '[ ]')]
                    + FINISHED_BLOCK[1:],
                ),
            ),
            'a description replaces the recorded one': (
                reopen_of(t.source, 'ft01ab', description='A new note.'),
                'a-list.md',
                with_lines(
                    A_LIST,
                    RESTORED_INDEX,
                    [
                        FINISHED_BLOCK[0].replace('[x]', '[ ]'),
                        '      A new note.',
                        *FINISHED_BLOCK[2:],
                    ],
                ),
            ),
            'a repeat of None, on a task with none, writes none': (
                reopen_of(t.source, 'ft01ab', {'REPEAT': 'None'}),
                'a-list.md',
                with_lines(
                    A_LIST,
                    RESTORED_INDEX,
                    [FINISHED_BLOCK[0].replace('[x]', '[ ]')]
                    + FINISHED_BLOCK[1:],
                ),
            ),
            'a scratched task, to the list a reopen names': (
                reopen_of(t.source, 'sc01ab', list_name='another-list'),
                'another-list.md',
                ANOTHER_LIST + '- [ ] A scratched task [P:1] [ID:sc01ab]\n',
            ),
            'a subtask whose line a list holds, each closed task above': (
                reopen_of(t.source, 'db03ef'),
                'a-held-list.md',
                HELD_LIST.replace('[x]', '[ ]'),
            ),
            'a top-level task with its subtasks, a checklist item closed': (
                reopen_of(t.source, 'ft01ab', with_subtasks=True),
                'a-list.md',
                with_lines(
                    A_LIST,
                    RESTORED_INDEX,
                    [
                        FINISHED_BLOCK[0].replace('[x]', '[ ]'),
                        FINISHED_BLOCK[1],
                        FINISHED_BLOCK[2].replace('[x]', '[ ]'),
                        FINISHED_BLOCK[3],
                    ],
                ),
            ),
            'a subtask with the closed subtask below it': (
                reopen_of(t.source, 'ds02cd', with_subtasks=True),
                'a-held-list.md',
                HELD_LIST.replace('[x]', '[ ]'),
            ),
            'a subtask in the record of its top-level task': (
                reopen_of(t.source, 'fs02cd'),
                'a-list.md',
                with_lines(
                    A_LIST,
                    RESTORED_INDEX,
                    [
                        FINISHED_BLOCK[0].replace('[x]', '[ ]'),
                        FINISHED_BLOCK[1],
                        FINISHED_BLOCK[2].replace('[x]', '[ ]'),
                        FINISHED_BLOCK[3],
                    ],
                ),
            ),
        }
        for name, (reopen, list_file, expected) in cases.items():
            with t.subTest(name):
                ret = reopen.text
                t.assertEqual(reopen.path, t.source / list_file)
                t.assertEqual(ret, expected)

        refused = {
            'a value that does not read': (
                reopen_of(t.source, 'ft01ab', {'DUE': 'x'}),
                ValueError,
                "DUE must be an ISO date, not 'x'",
            ),
            'a selector that names no task at all': (
                reopen_of(t.source, 'nothing'),
                SelectionError,
                "no open task matches 'nothing'",
            ),
            'a title that names several closed tasks': (
                reopen_of(t.source, 'twin'),
                ValueError,
                (
                    "'twin' matches 2 tasks in the journal:\n"
                    'tw02cd  2026-08-03  A twin task\n'
                    'tw01ab  2026-08-01  A twin task'
                ),
            ),
            'a checklist item, named with its task': (
                reopen_of(t.source, 'Its checklist item'),
                ValueError,
                r'names a checklist item of \[ID:ft01ab\]',
            ),
            'a list that is not there': (
                reopen_of(t.source, 'ft01ab', list_name='wrk'),
                ListError,
                "no list named 'wrk'",
            ),
            'a list for a subtask': (
                reopen_of(t.source, 'fs02cd', list_name='a-list'),
                ValueError,
                "'Its subtask' is a subtask: --list moves a top-level task",
            ),
            'a field only the top-level task carries, on a subtask': (
                reopen_of(t.source, 'db03ef', {'P': '3'}),
                ValueError,
                'P belongs to the top-level task',
            ),
            'a subtask whose line no list and no record holds': (
                reopen_of(t.source, 'ls01ab'),
                ValueError,
                (
                    r"'A lost subtask' is a subtask of \[ID:lp00ab\], and "
                    'no list and no record of a closed task holds its line'
                ),
            ),
            'a title with a line break': (
                reopen_of(t.source, 'ft01ab', title='A finished\rtask'),
                ValueError,
                'title must hold no line break',
            ),
        }
        for name, (refusal, error, message) in refused.items():
            with t.subTest(name), t.assertRaisesRegex(error, message):
                _ = refusal.text

    def test_entry(t) -> None:
        ret = t.ro.entry
        t.assertEqual(
            ret,
            '- [ ] A finished task [P:5] [ADDED:2026-07-01] [ID:ft01ab]',
        )

    def test_events(t) -> None:
        restored = {
            **FINISHED_SNAPSHOT,
            'done': True,
            'children': [
                {
                    'title': 'Its subtask',
                    'done': True,
                    'fields': {'LOE': '1', 'ID': 'fs02cd'},
                },
                {'title': 'Its checklist item', 'done': True, 'fields': {}},
            ],
        }

        with t.subTest('one TaskUpdated: the opening and the changes'):
            ret = t.ro.events
            t.assertEqual(
                ret,
                [
                    (
                        'TaskUpdated',
                        'task/ft01ab',
                        {
                            'delta': {
                                'P': ['2', '5'],
                                'done': [True, False],
                            },
                            'snapshot': restored,
                        },
                    ),
                ],
            )

        with t.subTest(
            'each closed task above a subtask opens, outermost first'
        ):
            step = reopen_of(t.source, 'db03ef', attrs={'cost': '45.00'})

            above, named = step.events

            t.assertEqual(
                (above.stream, above.payload['delta']),
                ('task/ds02cd', {'done': [True, False]}),
            )
            t.assertEqual(
                above.payload['ancestry'],
                'A task with a closed step > A closed step',
            )
            t.assertEqual(named.stream, 'task/db03ef')
            t.assertEqual(named.payload['attrs'], {'cost': '45.00'})
            t.assertEqual(named.payload['snapshot']['list'], 'a-held-list')

        with t.subTest('with its subtasks, each opens on its own stream'):
            whole = reopen_of(t.source, 'ft01ab', with_subtasks=True)

            top, below = whole.events

            t.assertEqual(
                [top.stream, below.stream],
                ['task/ft01ab', 'task/fs02cd'],
            )
            t.assertEqual(below.payload['delta'], {'done': [True, False]})
            t.assertEqual(
                below.payload['ancestry'],
                'A finished task > Its subtask',
            )

        with t.subTest('a clear of a repeat it does not carry: no change'):
            cleared = reopen_of(t.source, 'ft01ab', {'REPEAT': 'None'})
            (event,) = cleared.events
            t.assertEqual(event.payload['delta'], {'done': [True, False]})

        with t.subTest('a subtask in a record opens its top-level task'):
            child = reopen_of(t.source, 'fs02cd')

            top, named = child.events

            t.assertEqual(
                [top.stream, named.stream],
                ['task/ft01ab', 'task/fs02cd'],
            )
            t.assertEqual(named.payload['delta'], {'done': [True, False]})


class CompletionTests(TestCase):
    """Contract tests for battodo.mutate.Completion."""

    maxDiff = None

    def setUp(t) -> None:
        t.source = a_source(t)

    def test_write(t) -> None:
        with t.subTest('the list, the log and the journal hold its values'):
            completion = completion_of(t.source, 'A subtask that does not')

            completion.write()

            written = (t.source / 'a-list.md').read_text(encoding='utf-8')
            logged = (t.source / 'completed.md').read_text(encoding='utf-8')
            t.assertEqual(written, completion.text)
            t.assertEqual(logged, '\n'.join(completion.entries) + '\n')
            t.assertEqual(
                journaled(t.source),
                as_journaled(completion.events),
            )

        with t.subTest('each journal line it appends names the given day'):
            source = a_source(t)
            task = Task(source, 'A subtask that does not', GIVEN_DAY)

            Completion(task).write()

            appended = Journal(source).events
            days = [event['payload']['completed_on'] for event in appended]
            t.assertEqual(days, ['2026-08-01', '2026-08-01'])

        with t.subTest('the journal line of a checklist item marks it'):
            source = a_source(t)

            completion_of(source, 'A checklist item').write()

            (event,) = Journal(source).events
            t.assertIs(event['payload']['checklist_item'], True)

        with t.subTest('a checklist item journals its owner stamp first'):
            completion = completion_of(
                an_owner_source(t), 'A checklist item to write'
            )

            completion.write()

            stream = f'task/{completion.ids[2]}'
            t.assertEqual(
                journaled(completion.source),
                [('TaskUpdated', stream), ('TaskCompleted', stream)],
            )

        with t.subTest('a scratch: the list, the log and the journal'):
            source = a_source(t)
            scratched = scratch_of(source, '9o71lx')

            scratched.write()

            written = (source / 'a-list.md').read_text(encoding='utf-8')
            logged = (source / 'completed.md').read_text(encoding='utf-8')
            t.assertEqual(written, scratched.text)
            t.assertEqual(logged, '\n'.join(scratched.entries) + '\n')
            t.assertEqual(journaled(source), as_journaled(scratched.events))

        with t.subTest('a scratched checklist item journals its owner stamp'):
            scratched = scratch_of(
                an_owner_source(t), 'A checklist item to write'
            )

            scratched.write()

            stream = f'task/{scratched.ids[2]}'
            t.assertEqual(
                journaled(scratched.source),
                [('TaskUpdated', stream), ('TaskScratched', stream)],
            )

    def test_text(t) -> None:
        with t.subTest('a finished top-level task loses its line'):
            completed = completion_of(t.source, 'A task with no id')
            ret = completed.text
            t.assertEqual(ret, without(A_LIST, 8))

        with t.subTest('a block between blank lines takes one along'):
            completed = completion_of(t.source, 'bb01cd')
            ret = completed.text
            t.assertEqual(ret, without(A_LIST, 12, 13))

        with t.subTest('a child is stamped and checked, its parent stays'):
            completed = completion_of(t.source, 'A subtask of it')

            ret = completed.text

            child_id = completed.ids[6]
            line = f'  - [x] A subtask of it [LOE:2] [ID:{child_id}]'
            t.assertEqual(ret, A_LIST.replace(A_CHILD, line))

        with t.subTest('the last open child finishes a recurring parent'):
            completed = completion_of(t.source, 'A subtask that does not')

            ret = completed.text

            # The recurrence keeps its line and its id, gains its next due
            # date and the completion day as its `[ADDED:]`, and loses its
            # children.
            rescheduled = A_LIST.replace(
                '[DUE:2026-08-05] [REPEAT:7d] [ID:rr01ab]',
                '[DUE:2026-08-15] [REPEAT:7d] [ID:rr01ab] [ADDED:2026-08-08]',
            )
            t.assertEqual(ret, without(rescheduled, 10))

        with t.subTest('a recurrence completed on a given day is added then'):
            task = Task(a_source(t), 'A subtask that does not', GIVEN_DAY)
            completed = Completion(task)

            ret = completed.text

            rescheduled = A_LIST.replace(
                '[DUE:2026-08-05] [REPEAT:7d] [ID:rr01ab]',
                '[DUE:2026-08-08] [REPEAT:7d] [ID:rr01ab] [ADDED:2026-08-01]',
            )
            t.assertEqual(ret, without(rescheduled, 10))

        with t.subTest('a recurrence that does not read is refused'):
            odd = t.source / 'a-list.md'
            odd.write_text('## Open\n- [ ] An odd one [REPEAT:often]\n')
            completed = completion_of(t.source, 'An odd one')

            with t.assertRaises(RepeatError) as caught:
                _ = completed.text

            t.assertEqual(
                str(caught.exception),
                "unrecognised REPEAT value: 'often'",
            )

        with t.subTest('a rescheduled task keeps its description lines'):
            described = t.source / 'a-list.md'
            described.write_text(DESCRIBED_RECURRENCE, encoding='utf-8')
            completed = completion_of(t.source, 'dr01ab')

            ret = completed.text

            t.assertEqual(ret, RESCHEDULED_RECURRENCE)

        with t.subTest('a repeating subtask is rescheduled, its parent open'):
            completed = completion_of(a_stepped_source(t), 'rs01ab')

            ret = completed.text

            # The subtask stays open with its next due date, and takes no
            # `[ADDED:]`.
            t.assertEqual(
                ret,
                STEPPED_LIST.replace(
                    '[DUE:2026-08-05] [REPEAT:7d]',
                    '[DUE:2026-08-15] [REPEAT:7d]',
                ),
            )

        with t.subTest('from the given day'):
            task = Task(a_stepped_source(t), 'rs01ab', GIVEN_DAY)
            completed = Completion(task)

            ret = completed.text

            t.assertEqual(
                ret,
                STEPPED_LIST.replace(
                    '[DUE:2026-08-05] [REPEAT:7d]',
                    '[DUE:2026-08-08] [REPEAT:7d]',
                ),
            )

        with t.subTest('the last open subtask, rescheduled, ends no parent'):
            completed = completion_of(a_stepped_source(t), 'os01ab')

            ret = completed.text

            t.assertEqual(
                ret,
                STEPPED_LIST.replace(
                    '[DUE:2026-08-05] [REPEAT:monthly:5]',
                    '[DUE:2026-09-05] [REPEAT:monthly:5]',
                ),
            )

        with t.subTest('the last plain subtask beside a repeating one'):
            completed = completion_of(a_stepped_source(t), 'ps01ab')

            ret = completed.text

            t.assertEqual(
                ret,
                STEPPED_LIST.replace(
                    '  - [ ] A plain step [LOE:1]',
                    '  - [x] A plain step [LOE:1]',
                ),
            )

        with t.subTest('a rescheduled subtask loses its children'):
            completed = completion_of(a_stepped_source(t), 'rw01ab')

            ret = completed.text

            rescheduled = STEPPED_LIST.replace(
                '[DUE:2026-08-05] [REPEAT:1w]',
                '[DUE:2026-08-15] [REPEAT:1w]',
            )
            t.assertEqual(ret, without(rescheduled, 5))

        with t.subTest('and its last open child reschedules it'):
            completed = completion_of(a_stepped_source(t), 'sb01ab')

            ret = completed.text

            rescheduled = STEPPED_LIST.replace(
                '[DUE:2026-08-05] [REPEAT:1w]',
                '[DUE:2026-08-15] [REPEAT:1w]',
            )
            t.assertEqual(ret, without(rescheduled, 5))

        with t.subTest('a task that a repeating subtask holds open'):
            completed = completion_of(a_stepped_source(t), 'ch01ab')

            with t.assertRaises(ValueError) as refused:
                _ = completed.text

            t.assertEqual(
                str(refused.exception),
                "'A chore' has a repeating subtask, 'A repeating step' "
                '[ID:rs01ab]: remove its repeat first with update rs01ab '
                '--repeat None',
            )

        with t.subTest('and one that a deeper repeating subtask holds'):
            completed = completion_of(a_stepped_source(t), 'cd01ab')

            with t.assertRaises(ValueError) as refused:
                _ = completed.text

            t.assertEqual(
                str(refused.exception),
                "'A chore with a deep step' has a repeating subtask, "
                "'A repeating step below' [ID:rb01ab]: remove its repeat "
                'first with update rb01ab --repeat None',
            )

        with t.subTest('a subtask that a repeating subtask holds open'):
            completed = completion_of(a_stepped_source(t), 'pa01ab')

            with t.assertRaises(ValueError) as refused:
                _ = completed.text

            t.assertEqual(
                str(refused.exception),
                "'A plain step above' has a repeating subtask, "
                "'A repeating step below' [ID:rb01ab]: remove its repeat "
                'first with update rb01ab --repeat None',
            )

        with t.subTest('a recurring task, and a subtask with no id'):
            held = t.source / 'a-list.md'
            held.write_text(
                '## Open\n- [ ] A recurring chore [REPEAT:7d]\n'
                '  - [ ] A hand-written repeating step [REPEAT:3d]\n',
                encoding='utf-8',
            )
            completed = completion_of(t.source, 'A recurring chore')

            with t.assertRaises(ValueError) as refused:
                _ = completed.text

            t.assertEqual(
                str(refused.exception),
                "'A recurring chore' has a repeating subtask, "
                "'A hand-written repeating step': remove its repeat first "
                "with update 'A hand-written repeating step' --repeat None",
            )

        with t.subTest('a scratch drops a block that a repeat holds open'):
            scratched = scratch_of(a_stepped_source(t), 'ch01ab')
            ret = scratched.text
            t.assertEqual(ret, without(STEPPED_LIST, 1, 2, 3, 4, 5))

        with t.subTest('a scratch drops the task, its note and its children'):
            scratched = scratch_of(a_source(t), '9o71lx')
            ret = scratched.text
            t.assertEqual(ret, without(A_LIST, 4, 5, 6, 7))

        with t.subTest('a scratched subtask goes, and its parent stays'):
            scratched = scratch_of(a_source(t), 'A subtask of')
            ret = scratched.text
            t.assertEqual(ret, without(A_LIST, 6))

        with t.subTest('a scratch of the last open child ends no parent'):
            scratched = scratch_of(a_source(t), 'A subtask that does not')
            ret = scratched.text
            t.assertEqual(ret, without(A_LIST, 10))

        with t.subTest('a scratched recurring task goes, not rescheduled'):
            scratched = scratch_of(a_source(t), 'rr01ab')
            ret = scratched.text
            t.assertEqual(ret, without(A_LIST, 9, 10))

    def test_entries(t) -> None:
        with t.subTest('the task and each ancestor it ends, deepest first'):
            completed = completion_of(t.source, 'A subtask that does not')
            ret = completed.entries
            t.assertEqual(
                ret,
                [
                    (
                        '2026-08-08 | a-list | DONE | A recurring task > '
                        'A subtask that does not recur [LOE:1]'
                    ),
                    (
                        '2026-08-08 | a-list | DONE | A recurring task [P:3] '
                        '[DUE:2026-08-05] [REPEAT:7d]'
                    ),
                ],
            )

        with t.subTest('a checklist item is not logged'):
            completed = completion_of(t.source, 'A checklist item')
            ret = completed.entries
            t.assertEqual(ret, [])

        with t.subTest('a rescheduled subtask: one record, no ancestor'):
            completed = completion_of(a_stepped_source(t), 'os01ab')
            ret = completed.entries
            t.assertEqual(
                ret,
                [
                    (
                        '2026-08-08 | a-stepped-list | DONE | A chore with '
                        'one open step > Its only open step '
                        '[DUE:2026-08-05] [REPEAT:monthly:5]'
                    )
                ],
            )

        with t.subTest('a scratch: one SCRATCHED record, and no ancestor'):
            scratched = scratch_of(t.source, 'A subtask that does not')
            ret = scratched.entries
            t.assertEqual(
                ret,
                [
                    (
                        '2026-08-08 | a-list | SCRATCHED | A recurring task > '
                        'A subtask that does not recur [LOE:1]'
                    )
                ],
            )

        with t.subTest('a scratched checklist item is not logged'):
            scratched = scratch_of(t.source, 'A checklist item')
            ret = scratched.entries
            t.assertEqual(ret, [])

    def test_events(t) -> None:
        with t.subTest('one TaskCompleted a completion, deepest first'):
            completed = completion_of(t.source, 'A subtask that does not')

            child, parent = completed.events

            t.assertEqual(child.type, 'TaskCompleted')
            t.assertEqual(
                child.payload['ancestry'],
                'A recurring task > A subtask that does not recur',
            )
            t.assertEqual(child.payload['completed_on'], '2026-08-08')
            t.assertEqual(
                parent,
                (
                    'TaskCompleted',
                    'task/rr01ab',
                    {
                        'delta': {
                            'done': [False, True],
                            'DUE': ['2026-08-05', '2026-08-15'],
                            'ADDED': [None, '2026-08-08'],
                        },
                        'snapshot': {
                            'list': 'a-list',
                            'title': 'A recurring task',
                            'done': False,
                            'fields': {
                                'P': '3',
                                'DUE': '2026-08-05',
                                'REPEAT': '7d',
                                'ID': 'rr01ab',
                            },
                            'children': [
                                {
                                    'title': 'A subtask that does not recur',
                                    'done': False,
                                    'fields': {'LOE': '1'},
                                },
                            ],
                        },
                        'ancestry': 'A recurring task',
                        'completed_on': '2026-08-08',
                    },
                ),
            )

        with t.subTest('a rescheduled subtask: its new due date, no ADDED'):
            completed = completion_of(a_stepped_source(t), 'os01ab')
            events = completed.events
            t.assertEqual(
                events,
                [
                    (
                        'TaskCompleted',
                        'task/os01ab',
                        {
                            'delta': {
                                'done': [False, True],
                                'DUE': ['2026-08-05', '2026-09-05'],
                            },
                            'snapshot': {
                                'list': 'a-stepped-list',
                                'title': 'Its only open step',
                                'done': False,
                                'fields': {
                                    'DUE': '2026-08-05',
                                    'REPEAT': 'monthly:5',
                                    'ID': 'os01ab',
                                },
                            },
                            'ancestry': (
                                'A chore with one open step > '
                                'Its only open step'
                            ),
                            'completed_on': '2026-08-08',
                        },
                    )
                ],
            )

        with t.subTest('a checklist item lands on its owner stream'):
            completed = completion_of(t.source, 'A checklist item')

            (ret,) = completed.events

            t.assertEqual(ret.stream, 'task/9o71lx')
            t.assertEqual(ret.payload['ancestry'], 'A task > A checklist item')
            t.assertIs(ret.payload['checklist_item'], True)

        with t.subTest('an owner with no id is stamped first, on its own'):
            completed = completion_of(
                an_owner_source(t), 'A checklist item to write'
            )

            stamp, item = completed.events

            task_id = completed.ids[2]
            t.assertEqual(
                stamp,
                (
                    'TaskUpdated',
                    f'task/{task_id}',
                    {
                        'delta': {'ID': [None, task_id]},
                        'snapshot': OWNER_SNAPSHOT,
                    },
                ),
            )
            t.assertEqual(item.stream, f'task/{task_id}')

        with t.subTest('the attributes go on the named task alone'):
            completed = completion_of(
                t.source,
                'A subtask that does not',
                attrs={'cost': '45.00'},
            )

            child, parent = completed.events

            t.assertEqual(child.payload['attrs'], {'cost': '45.00'})
            t.assertNotIn('attrs', parent.payload)

        with t.subTest('a checklist item takes no attributes'):
            completed = completion_of(
                t.source,
                'A checklist item',
                attrs={'note': 'a note'},
            )

            with t.assertRaises(ValueError) as caught:
                _ = completed.events

            t.assertEqual(
                str(caught.exception),
                'a checklist item takes no attributes',
            )

        with t.subTest('a scratch: one TaskScratched, on its stream'):
            scratched = scratch_of(t.source, '9o71lx', attrs={'cost': '0'})
            events = scratched.events
            t.assertEqual(
                events,
                [
                    (
                        'TaskScratched',
                        'task/9o71lx',
                        {
                            'delta': {'removed': [False, True]},
                            'snapshot': {
                                'list': 'a-list',
                                'title': 'A task',
                                'done': False,
                                'fields': {
                                    'P': '4',
                                    'LOE': '8',
                                    'ADDED': '2026-07-06',
                                    'ID': '9o71lx',
                                },
                                'description': 'A note that stays put.',
                                'children': A_TASK_CHILDREN,
                            },
                            'ancestry': 'A task',
                            'attrs': {'cost': '0'},
                            'completed_on': '2026-08-08',
                        },
                    )
                ],
            )

        with t.subTest('a scratched task with no id takes no stamp'):
            # Its line goes, so no line keeps the new id.
            scratched = scratch_of(t.source, 'A task with no id')

            (ret,) = scratched.events

            t.assertEqual(ret.stream, f'task/{scratched.ids[8]}')

        with t.subTest('a scratched checklist item: its owner stamp first'):
            scratched = scratch_of(
                an_owner_source(t), 'A checklist item to write'
            )

            stamp, item = scratched.events

            task_id = scratched.ids[2]
            t.assertEqual(stamp.type, 'TaskUpdated')
            t.assertEqual(
                (item.type, item.stream, item.payload['checklist_item']),
                ('TaskScratched', f'task/{task_id}', True),
            )

        with t.subTest('a scratched checklist item takes no attributes'):
            scratched = scratch_of(
                t.source,
                'A checklist item',
                attrs={'note': 'a note'},
            )

            with t.assertRaises(ValueError) as caught:
                _ = scratched.events

            t.assertEqual(
                str(caught.exception),
                'a checklist item takes no attributes',
            )


class AnnotationTests(TestCase):
    """Contract tests for battodo.mutate.Annotation."""

    maxDiff = None

    def setUp(t) -> None:
        t.source = a_source(t)
        t.an = annotation_of(t.source, '9o71lx')

    def test_write(t) -> None:
        with t.subTest('the list and the journal hold its values'):
            unidentified = annotation_of(t.source, 'A task with no id')

            unidentified.write()

            written = (t.source / 'a-list.md').read_text(encoding='utf-8')
            t.assertEqual(written, unidentified.text)
            t.assertEqual(
                journaled(t.source),
                as_journaled(unidentified.events),
            )

        with t.subTest('a task with an id: the list is not written again'):
            source = a_source(t)
            path = source / 'a-list.md'
            # A known mtime, so a rewrite shows without a wait.
            utime(path, ns=(0, 0))
            noted = annotation_of(source, '9o71lx')

            noted.write()

            t.assertEqual(path.stat().st_mtime_ns, 0)
            t.assertEqual(journaled(source), as_journaled(noted.events))

    def test_text(t) -> None:
        with t.subTest('a task with an id: the list as read'):
            ret = t.an.text
            t.assertEqual(ret, A_LIST)

        with t.subTest('a task with no id is given one'):
            unidentified = annotation_of(t.source, 'A task with no id')

            ret = unidentified.text

            line = f'{NO_ID_TASK} [ID:{unidentified.task_id}]'
            t.assertEqual(ret, A_LIST.replace(NO_ID_TASK, line))

        refused = {
            'a note that carries nothing, before the selector': (
                Annotation(Task(t.source, 'nothing', TODAY), {}),
                ValueError,
                'nothing to note: give a note or an attribute',
            ),
            'a checklist item, which takes no attributes': (
                annotation_of(t.source, 'A checklist item'),
                ValueError,
                'a checklist item takes no attributes',
            ),
            'a selector that names no open task': (
                annotation_of(t.source, 'nothing'),
                SelectionError,
                "no open task matches 'nothing'",
            ),
        }
        for name, (refusal, error, message) in refused.items():
            with t.subTest(name), t.assertRaisesRegex(error, message):
                _ = refusal.text

    def test_entry(t) -> None:
        ret = t.an.entry
        t.assertEqual(ret, A_TASK)

    def test_events(t) -> None:
        with t.subTest('one TaskAnnotated, on the stream of the task'):
            ret = t.an.events
            t.assertEqual(
                ret,
                [
                    (
                        'TaskAnnotated',
                        'task/9o71lx',
                        {
                            'snapshot': {
                                'list': 'a-list',
                                'title': 'A task',
                                'done': False,
                                'fields': {
                                    'P': '4',
                                    'LOE': '8',
                                    'ADDED': '2026-07-06',
                                    'ID': '9o71lx',
                                },
                                'description': 'A note that stays put.',
                                'children': A_TASK_CHILDREN,
                            },
                            'attrs': {'note': 'Waiting on the vendor'},
                        },
                    )
                ],
            )

        with t.subTest('a task with no id is stamped first, on its own'):
            unidentified = annotation_of(t.source, 'A task with no id')

            stamp, annotated = unidentified.events

            task_id = unidentified.task_id
            t.assertEqual(
                stamp,
                (
                    'TaskUpdated',
                    f'task/{task_id}',
                    {
                        'delta': {'ID': [None, task_id]},
                        'snapshot': {
                            'list': 'a-list',
                            'title': 'A task with no id',
                            'done': False,
                            'fields': {'P': '2'},
                        },
                    },
                ),
            )
            t.assertEqual(annotated.stream, f'task/{task_id}')

        with t.subTest('a subtask records where it sits'):
            child = annotation_of(t.source, 'A subtask of it')

            _, annotated = child.events

            t.assertEqual(
                annotated.payload['ancestry'],
                'A task > A subtask of it',
            )


class BackfillTests(TestCase):
    """Contract tests for battodo.mutate.Backfill."""

    maxDiff = None

    def setUp(t) -> None:
        t.source = a_source(t)
        (t.source / 'a-template.md').write_text(
            '## Open\n- [ ] A task dated YYYY-MM-DD [DUE:YYYY-MM-DD]\n',
            encoding='utf-8',
        )

    def test_write(t) -> None:
        backfill = Backfill(t.source, TODAY)

        backfill.write()

        (listed,) = backfill.lists
        written = listed.path.read_text(encoding='utf-8')
        # The one list with a task to stamp holds the text its backfill
        # derives, and the journal holds its events.
        t.assertEqual(written, listed.text)
        t.assertEqual(journaled(t.source), as_journaled(listed.events))

    def test_lists(t) -> None:
        (ret,) = Backfill(t.source, TODAY).lists

        with t.subTest('only a list with an undated task to stamp'):
            t.assertEqual(ret.path, t.source / 'a-list.md')
            t.assertEqual(
                [task.title for task in ret.tasks],
                [
                    'A task with no id',
                    'A recurring task',
                    'A task between blank lines',
                ],
            )

        with t.subTest('each gains its add date, and an id if it has none'):
            stamped = (
                A_LIST.replace(
                    NO_ID_TASK,
                    f'{NO_ID_TASK} [ADDED:2026-08-08] [ID:{ret.ids[8]}]',
                )
                .replace('[ID:rr01ab]', '[ID:rr01ab] [ADDED:2026-08-08]')
                .replace('[ID:bb01cd]', '[ID:bb01cd] [ADDED:2026-08-08]')
            )
            t.assertEqual(ret.text, stamped)

        with t.subTest('one TaskAdded a stamp, marked as a backfill'):
            t.assertEqual(
                [event.stream for event in ret.events],
                [f'task/{ret.ids[8]}', 'task/rr01ab', 'task/bb01cd'],
            )
            t.assertEqual(
                ret.events[0].payload,
                {
                    'delta': {'ADDED': [None, '2026-08-08']},
                    'snapshot': {
                        'list': 'a-list',
                        'title': 'A task with no id',
                        'done': False,
                        'fields': {'P': '2'},
                    },
                    'backfilled': True,
                },
            )


class CompletedLogTests(TestCase):
    """Contract tests for battodo.mutate.CompletedLog."""

    def setUp(t) -> None:
        t.source = a_source(t)
        t.cl = CompletedLog(t.source)
        t.path = t.source / 'completed.md'

    def test_append(t) -> None:
        with t.subTest('a log not there yet is created to hold them'):
            t.cl.append(['a record', 'another record'])
            ret = t.path.read_text(encoding='utf-8')
            t.assertEqual(ret, 'a record\nanother record\n')

        with t.subTest('a log that ends mid-line gains a newline first'):
            t.path.write_text('# A log', encoding='utf-8')

            t.cl.append(['a record'])

            ret = t.path.read_text(encoding='utf-8')
            t.assertEqual(ret, '# A log\na record\n')

        with t.subTest('no record leaves an absent log absent'):
            t.path.unlink()
            t.cl.append([])
            t.assertFalse(t.path.exists())


class ChangesetTests(TestCase):
    """Contract tests for battodo.mutate.Changeset."""

    def setUp(t) -> None:
        t.source = a_source(t)
        t.path = t.source / 'a-list.md'
        t.cs = Changeset(
            {
                t.path: 'the list as written\n',
                t.source / 'another-list.md': 'the other list as written\n',
            },
            ['a record'],
            [Event('TaskAdded', 'task/zz01ab', {'delta': {}})],
            t.path,
            t.source,
        )

    def test_write(t) -> None:
        with t.subTest('the list, the log and the journal take its values'):
            t.cs.write()

            written = t.path.read_text(encoding='utf-8')
            other = t.source / 'another-list.md'
            logged = (t.source / 'completed.md').read_text(encoding='utf-8')
            (event,) = Journal(t.source).events
            t.assertEqual(written, 'the list as written\n')
            t.assertEqual(
                other.read_text(encoding='utf-8'),
                'the other list as written\n',
            )
            t.assertEqual(logged, 'a record\n')
            t.assertEqual(
                (event['type'], event['stream_id'], event['payload']),
                ('TaskAdded', 'task/zz01ab', {'delta': {}}),
            )
            t.assertEqual(
                event['metadata'],
                {'actor': 'agent', 'source_file': 'a-list.md'},
            )

        with t.subTest('a list that holds the text already is not written'):
            source = a_source(t)
            path = source / 'a-list.md'
            # A known mtime, so a rewrite shows without a wait.
            utime(path, ns=(0, 0))
            unchanged = Changeset(
                {path: A_LIST},
                ['a record'],
                [Event('TaskAdded', 'task/zz01ab', {'delta': {}})],
                path,
                source,
            )

            unchanged.write()

            logged = (source / 'completed.md').read_text(encoding='utf-8')
            t.assertEqual(path.stat().st_mtime_ns, 0)
            t.assertEqual(logged, 'a record\n')
            t.assertEqual(journaled(source), [('TaskAdded', 'task/zz01ab')])


def a_source(t: TestCase) -> Path:
    """A source directory holding both lists, removed at the end."""
    tmp = TemporaryDirectory()
    t.addCleanup(tmp.cleanup)
    source = Path(tmp.name)
    (source / 'a-list.md').write_text(A_LIST, encoding='utf-8')
    (source / 'another-list.md').write_text(ANOTHER_LIST, encoding='utf-8')
    return source


def a_closed_source(t: TestCase) -> Path:
    """A source whose journal holds CLOSED_EVENTS, beside HELD_LIST."""
    source = a_source(t)
    held = source / 'a-held-list.md'
    held.write_text(HELD_LIST, encoding='utf-8')
    journal = Journal(source)
    for event_type, stream_id, payload in CLOSED_EVENTS:
        journal.append(
            event_type,
            stream_id,
            payload,
            actor='agent',
            source_file='a-list.md',
        )
    return source


def reopen_of(
    source: Path,
    selector: str,
    fields: dict[str, str] | None = None,
    **named: Any,
) -> Reopen:
    """A reopen of the closed task `selector` names in `source`."""
    return Reopen(Task(source, selector, TODAY), TZ, fields or {}, **named)


def an_owner_source(t: TestCase) -> Path:
    """A source directory holding both lists and the owner list."""
    source = a_source(t)
    owner = source / 'an-owner-list.md'
    owner.write_text(OWNER_LIST, encoding='utf-8')
    return source


def a_stepped_source(t: TestCase) -> Path:
    """A source directory holding both lists and the stepped list."""
    source = a_source(t)
    stepped = source / 'a-stepped-list.md'
    stepped.write_text(STEPPED_LIST, encoding='utf-8')
    return source


def with_line(text: str, index: int, line: str) -> str:
    """`text` with `line` inserted at `index`."""
    lines = text.split('\n')
    lines.insert(index, line)
    return '\n'.join(lines)


def with_lines(text: str, index: int, lines: list[str]) -> str:
    """`text` with `lines` inserted in order from `index`."""
    found = text.split('\n')
    found[index:index] = lines
    return '\n'.join(found)


def described_addition(source: Path, description: str) -> Addition:
    """A new task in `a-list` that carries `description`."""
    return Addition(
        source,
        'a-list',
        'A new task',
        {},
        TODAY,
        description=description,
    )


def described_update(source: Path, selector: str, description: str) -> Update:
    """An update that names only a description."""
    return Update(Task(source, selector, TODAY), {}, description=description)


def id_on(line: str) -> str:
    """The `[ID:]` value a write stamped on `line`."""
    return line.split('[ID:')[1].removesuffix(']')


def subtask(
    source: Path,
    parent: str,
    *,
    list_name: str = 'a-list',
    fields: dict[str, str] | None = None,
    title: str = 'A new subtask',
    description: str | None = None,
) -> SubtaskAddition:
    """A new subtask under the task `parent` names."""
    return SubtaskAddition(
        Task(source, parent, TODAY),
        list_name,
        title,
        fields or {},
        description=description,
    )


def without(text: str, *indices: int) -> str:
    """`text` without the lines at `indices`."""
    return '\n'.join(
        line
        for index, line in enumerate(text.split('\n'))
            if index not in indices
    )  # fmt: skip


def completion_of(
    source: Path,
    selector: str,
    attrs: dict[str, str] | None = None,
) -> Completion:
    """The completion of the task `selector` names."""
    return Completion(Task(source, selector, TODAY), attrs=attrs)


def scratch_of(
    source: Path,
    selector: str,
    attrs: dict[str, str] | None = None,
) -> Completion:
    """The scratch of the task `selector` names."""
    task = Task(source, selector, TODAY)
    return Completion(task, attrs=attrs, scratched=True)


def annotation_of(source: Path, selector: str) -> Annotation:
    """A note on the task `selector` names."""
    return Annotation(Task(source, selector, TODAY), A_NOTE)


def under_an_empty_id(source: Path) -> SubtaskAddition:
    """A new subtask under a parent whose `[ID:]` holds nothing."""
    list_file = source / 'an-empty-id-list.md'
    list_file.write_text(EMPTY_ID_LIST, encoding='utf-8')
    return subtask(
        source,
        'A task with an empty id',
        list_name='an-empty-id-list',
    )


def journaled(source: Path) -> list[tuple[str, str]]:
    """The type and stream of each event the journal of `source` holds."""
    return [
        (event['type'], event['stream_id']) for event in Journal(source).events
    ]


def as_journaled(events: list[Event]) -> list[tuple[str, str]]:
    """The type and stream of each of `events`."""
    return [(event.type, event.stream) for event in events]
