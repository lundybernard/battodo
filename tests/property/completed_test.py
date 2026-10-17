"""Property tests for the completed log, driven by Hypothesis.

Each case writes one record through the writer `battodo.mutate` uses,
appends it to a real log, and reads the log back through the digest.
The expected record derives from the drawn task, never from the code
under test.
"""

from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from hypothesis import given
from hypothesis import strategies as st

from battodo.completed import Digest, Record
from battodo.mutate import CompletedLog, LogEntry, TaskCompletion
from battodo.parser import Ancestry, TaskNode

from .mutate_test import ATTRIBUTE_KEY, SCHEMA_FIELDS
from .strategies import grammar
from .task_test import LIST_FILE

# Title text an attribute syntax could claim: the separator, `=`, a
# comma before a key, and an attribute block or a JSON object that
# does not end the line.
CLAIMED = [' | ', '=', ', cost=', '[attrs:{"a": "b"}', '{"cost": "1"}']
# Value text a block could end at or be read from.
ENDINGS = [']', '"', '\\', '"}]', '[attrs:{}]', ', cost=5']


class LogEntryTests(TestCase):
    """Property tests for battodo.mutate.LogEntry, read back."""

    maxDiff = None

    @given(st.data())
    def test_text(t, data: st.DataObject) -> None:
        titles = data.draw(st.lists(record_titles(), min_size=1, max_size=3))
        fields = data.draw(schema_fields())
        attrs = data.draw(attribute_maps())
        day = data.draw(st.dates())
        logged = stand_in(titles, fields, day, attrs)
        expected = Record(day, 'a-list', shown(titles), attrs)

        with TemporaryDirectory() as tmp:
            source = Path(tmp)
            line = LogEntry(source / LIST_FILE, logged).text
            CompletedLog(source).append([line])
            now = datetime.combine(day, datetime.min.time())
            ret = Digest(source, now, period='today').records

        t.assertEqual(ret, [expected])


def record_titles() -> st.SearchStrategy[str]:
    """A title, rich in the text an attribute syntax could claim.

    No piece holds a closing bracket, so no title ends the line as an
    attribute block would.
    """
    pieces = st.one_of(st.sampled_from(CLAIMED), grammar.titles)
    titles = st.lists(pieces, min_size=1, max_size=4).map(''.join)
    return titles.filter(str.strip)


def schema_fields() -> st.SearchStrategy[dict[str, str]]:
    """The SCHEMA.md fields of a task, each left off or given a value."""
    return st.dictionaries(
        st.sampled_from(SCHEMA_FIELDS),
        grammar.field_values,
        max_size=3,
    )


def attribute_maps() -> st.SearchStrategy[dict[str, str]]:
    """Up to four attributes, each value on one line.

    A value holds any other character, `]`, `"` and a comma before a
    key among them: the text of `--note` never runs through the split.
    """
    text = st.text(
        st.characters(codec='utf-8', exclude_characters='\n\r'),
        min_size=1,
        max_size=6,
    )
    pieces = st.one_of(st.sampled_from(ENDINGS), text)
    values = st.lists(pieces, min_size=1, max_size=4).map(''.join)
    keys = st.from_regex(ATTRIBUTE_KEY, fullmatch=True)
    return st.dictionaries(keys, values, max_size=4)


def stand_in(
    titles: list[str],
    fields: dict[str, str],
    day: date,
    attrs: dict[str, str],
) -> TaskCompletion:
    """The completion of the last of `titles`, which carries `fields`."""
    tasks = [
        TaskNode(index, index * 2, False, title, {'LOE': '1'})
        for index, title in enumerate(titles)
    ]
    tasks[-1].fields = fields
    return TaskCompletion(Ancestry(tasks), {}, day, 'a-list', attrs)


def shown(titles: list[str]) -> str:
    """The path of `titles` as a digest shows it: spaces collapsed."""
    path = ' > '.join(titles)
    return ' '.join(path.split())
