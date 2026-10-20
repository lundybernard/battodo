"""The values a caller supplies to a write, read before any write.

Each class reads one supplied input and refuses a value that does not
read: the fields, title and description an update names, a title, a
description, the fields of a task, and the attributes of an event. A
write object reads them before it writes anything, so a refusal leaves
the source as it was.
"""

import re
from collections.abc import Mapping
from datetime import date
from typing import Any

from .parser import (
    CHECKBOX_RE,
    SCHEMA_FIELDS,
    TaskNode,
    join_description,
    parse_date,
)
from .repeat import next_due

LOE_VALUES = ('1', '2', '3', '5', '8')
# The fields a top-level task owns. SCHEMA.md gives a subtask no `P` of
# its own, because only a top-level task is ranked.
ROOT_ONLY_FIELDS = ('P',)
# The clear token: the value an update names to clear what an option
# writes (ADR 0028). A word of the CLI, not a credential.
CLEAR_TOKEN = 'None'  # noqa: S105
# The fields the clear token clears. Any other field reads it as a value.
CLEARABLE_FIELDS = ('DUE', 'REPEAT', 'TAGS')
# An attribute key: a letter, then letters, digits or underscores.
ATTRIBUTE_KEY = re.compile(r'[a-z][a-z0-9_]*')
# The one place `--attrs` splits: a comma, spaces or tabs, then the next
# `key=`. A line break does not split, so the value refuses it.
ATTRIBUTE_SEPARATOR = re.compile(rf',[ \t]*(?={ATTRIBUTE_KEY.pattern}=)')
# The key the text of `--note` enters the attributes under.
NOTE_KEY = 'note'


class SuppliedEdit:
    """The fields, the title and the description an update names.

    Each value is read before any write. The clear token is decoded here
    alone. A value the task holds is no change (ADR 0028), so each
    comparison takes the task as the update finds it.
    """

    def __init__(
        self,
        fields: dict[str, str],
        title: str | None,
        description: str | None,
        today: date,
    ) -> None:
        self.fields = fields
        self.title = title
        self.description = description
        self.today = today

    @property
    def changed(self) -> dict[str, str | None]:
        """The named fields, read, a cleared one None.

        A cleared field is not read.

        Raises
        ------
        ValueError
            A supplied value does not read.
        """
        changed: dict[str, str | None] = {**self.supplied.checked}
        for name in self.cleared:
            changed[name] = None
        return changed

    @property
    def cleared(self) -> list[str]:
        """The named fields that the clear token clears, in order."""
        return [
            name
            for name, value in self.fields.items()
                if value == CLEAR_TOKEN and name in CLEARABLE_FIELDS
        ]  # fmt: skip

    @property
    def supplied(self) -> 'SuppliedFields':
        """The named fields to read against `today`.

        A cleared field is not read, so it is left out.
        """
        cleared = self.cleared
        read = {
            name: value
            for name, value in self.fields.items()
                if name not in cleared
        }  # fmt: skip
        return SuppliedFields(read, self.today)

    @property
    def checked_title(self) -> str | None:
        """The named title, read, or None where none is named.

        Raises
        ------
        ValueError
            The title holds a line break.
        """
        if self.title is None:
            return None
        return SuppliedTitle(self.title).checked

    @property
    def checked_description(self) -> list[str] | None:
        """The lines of the named description, or None where none is named.

        An empty description, or the clear token, holds no line, so it
        clears the description.

        Raises
        ------
        ValueError
            A description line is refused.
        """
        if self.description is None:
            return None
        text = '' if self.description == CLEAR_TOKEN else self.description
        return SuppliedDescription(text).lines

    def changes(self, node: TaskNode) -> dict[str, str | None]:
        """The named fields that change `node`, read, a cleared one None.

        A value the task holds is no change, and a clear of a field the
        task does not carry, or carries empty, is no change either.
        """
        held = node.fields
        return {
            name: value
            for name, value in self.changed.items()
                if value != held.get(name)
                and (value is not None or held.get(name))
        }  # fmt: skip

    def new_title(self, node: TaskNode) -> str | None:
        """The named title where it changes `node`, or None.

        The list reads a title back without its outer spaces, so they
        are no change.
        """
        title = self.checked_title
        if title is None or title.strip() == node.title:
            return None
        return title

    def new_description(self, node: TaskNode) -> list[str] | None:
        """The named description lines where they change `node`, or None."""
        lines = self.checked_description
        return None if lines == node.description_lines else lines

    def refuse_root_fields(self) -> None:
        """Refuse a named field that only the top-level task carries.

        Raises
        ------
        ValueError
            The fields name one.
        """
        self.supplied.refuse_root_fields()

    def delta(
        self,
        node: TaskNode,
        written: Mapping[str, str | None],
    ) -> dict[str, list[Any]]:
        """Each written field, title and description that changes `node`.

        Each stands against the one it replaces. A cleared field or
        description stands as None.
        """
        delta: dict[str, list[Any]] = {
            name: [node.fields.get(name), value]
            for name, value in written.items()
        }
        new_title = self.new_title(node)
        if new_title is not None:
            delta['title'] = [node.title, new_title]
        new_description = self.new_description(node)
        if new_description is not None:
            text = join_description(new_description)
            delta['description'] = [node.description, text]
        return delta


class SuppliedTitle:
    """A title a caller supplies to a write, read before any write."""

    def __init__(self, text: str) -> None:
        self.text = text

    @property
    def checked(self) -> str:
        """The title, whole on its task line.

        Raises
        ------
        ValueError
            The title holds a line feed or a carriage return. Either
            ends the task line when the list is read again.
        """
        if '\n' in self.text or '\r' in self.text:
            raise ValueError(
                f'title must hold no line break, not {self.text!r}'
            )
        return self.text


class SuppliedDescription:
    """A description a caller supplies to a write, read before any write.

    Each line of the text is one description line. An empty text holds
    no line, so an update that supplies one clears the description.
    """

    def __init__(self, text: str) -> None:
        self.text = text

    @property
    def lines(self) -> list[str]:
        """The description lines, each stripped of its indent.

        Raises
        ------
        ValueError
            A line is blank, reads as a task line, a heading or a
            comment, or holds a carriage return. The parser reads such
            a line back as something other than a description line.
        """
        if not self.text:
            return []
        return [DescriptionLine(line).text for line in self.text.split('\n')]


class DescriptionLine:
    """One line of a supplied description.

    `_raw_text` holds the line as the caller gave it.
    """

    def __init__(self, text: str) -> None:
        self._raw_text = text

    @property
    def text(self) -> str:
        """The line, stripped of its indent.

        Raises
        ------
        ValueError
            The line has a refusal. The message names the line as the
            caller gave it.
        """
        if self._refusal is not None:
            raise ValueError(
                f'description line {self._raw_text!r} {self._refusal}'
            )
        return self._stripped

    @property
    def _refusal(self) -> str | None:
        """Why the parser reads the line back as no description line.

        A blank line, a task line, a heading or a comment, checked in
        that order, then a carriage return. None for a description line.
        The carriage-return check reads the line as given, because the
        strip removes a trailing one.
        """
        if not self._stripped:
            return 'is blank'
        if CHECKBOX_RE.match(self._stripped):
            return 'reads as a task line'
        if self._stripped.startswith('## '):
            return 'reads as a heading'
        if self._stripped.startswith('<!--'):
            return 'reads as a comment'
        if '\r' in self._raw_text:
            return 'holds a carriage return'
        return None

    @property
    def _stripped(self) -> str:
        """The line without its indent and its trailing white space."""
        return self._raw_text.strip()


class SuppliedFields:
    """The fields a caller supplies to a write, read before any write.

    Only the values with a grammar btodo depends on are checked: a
    `TAGS` string is free-form and cannot be wrong.
    """

    def __init__(self, fields: dict[str, str], today: date) -> None:
        self.fields = fields
        self.today = today

    @property
    def ordered(self) -> dict[str, str]:
        """The fields as read, in SCHEMA.md order."""
        checked = self.checked
        return {
            name: checked[name]
            for name in SCHEMA_FIELDS
                if name in checked
        }  # fmt: skip

    @property
    def checked(self) -> dict[str, str]:
        """The fields, each value read, a due date in ISO form.

        Raises
        ------
        ValueError
            A `P`, `LOE`, `DUE` or `REPEAT` does not read, checked in
            that order. `RepeatError`, a ValueError, covers `REPEAT`.
        """
        return {**self.fields, **self._given}

    @property
    def _given(self) -> dict[str, str]:
        """Each checked field that is given, as read."""
        return {
            name: value
            for name, value in self._read.items()
                if value is not None
        }  # fmt: skip

    @property
    def _read(self) -> dict[str, str | None]:
        """Each checked field as read, None where none is given."""
        return {
            'P': self.priority,
            'LOE': self.loe,
            'DUE': self.due,
            'REPEAT': self.repeat,
        }

    @property
    def priority(self) -> str | None:
        """The `P` value, or None without one.

        Raises
        ------
        ValueError
            The value is not a whole number.
        """
        priority = self.fields.get('P')
        if priority is not None and not priority.isdigit():
            raise ValueError(f'P must be a whole number, not {priority!r}')
        return priority

    @property
    def loe(self) -> str | None:
        """The `LOE` value, or None without one.

        Raises
        ------
        ValueError
            The value is not on the scale.
        """
        loe = self.fields.get('LOE')
        if loe is not None and loe not in LOE_VALUES:
            raise ValueError(
                f'LOE must be one of {", ".join(LOE_VALUES)}, not {loe!r}'
            )
        return loe

    @property
    def due(self) -> str | None:
        """The `DUE` date in ISO form, or None without one.

        Raises
        ------
        ValueError
            The value does not read as a date.
        """
        due = self.fields.get('DUE')
        if due is None:
            return None
        parsed = parse_date(due)
        if parsed is None:
            raise ValueError(f'DUE must be an ISO date, not {due!r}')
        # Normalised, not passed through: `date.fromisoformat` accepts
        # more spellings on newer interpreters, and a line's meaning
        # must not depend on which one wrote it.
        return parsed.isoformat()

    @property
    def repeat(self) -> str | None:
        """The `REPEAT` value, or None without one.

        Raises
        ------
        RepeatError
            The value does not read as a recurrence.
        """
        repeat = self.fields.get('REPEAT')
        if repeat is not None:
            # Validated by scheduling it and throwing the answer away: the
            # repeat parser is the only definition of a readable spec, and
            # an unreadable one must fail before a task carries it.
            next_due(repeat, self.today)
        return repeat

    def refuse_root_fields(self) -> None:
        """Refuse a field that only the top-level task carries.

        Raises
        ------
        ValueError
            The fields name one. Nothing reads such a field on a child,
            so writing it would read as a change that never happened.
        """
        for name in ROOT_ONLY_FIELDS:
            if name in self.fields:
                raise ValueError(
                    f'{name} belongs to the top-level task, not to a subtask'
                )


class SuppliedAttributes:
    """The attributes a caller supplies to a write, read before any write.

    `text` holds `key=value` segments. The text of `note` enters as the
    key `note` and never runs through the split.
    """

    def __init__(self, text: str | None, note: str | None) -> None:
        self.text = text
        self.note = note

    @property
    def checked(self) -> dict[str, str]:
        """Each key against its value, in the order given.

        Raises
        ------
        ValueError
            A key is outside the grammar, a value is empty or holds a
            line break, or a key is given twice.
        """
        checked: dict[str, str] = {}
        for key, value in self.pairs:
            if not ATTRIBUTE_KEY.fullmatch(key):
                raise ValueError(
                    f'attribute key must be a lowercase identifier, '
                    f'not {key!r}'
                )
            if not value:
                raise ValueError(f'attribute {key!r} must hold a value')
            if '\n' in value or '\r' in value:
                raise ValueError(
                    f'attribute {key!r} must hold no line break, not {value!r}'
                )
            if key in checked:
                raise ValueError(f'attribute {key!r} is given twice')
            checked[key] = value
        return checked

    @property
    def pairs(self) -> list[tuple[str, str]]:
        """Each segment split at its first `=`, then the note.

        Raises
        ------
        ValueError
            A segment holds no `=`.
        """
        pairs = []
        for segment in self.segments:
            key, sign, value = segment.partition('=')
            if not sign:
                raise ValueError(
                    f'attribute must read key=value, not {segment!r}'
                )
            pairs.append((key, value))
        if self.note is not None:
            pairs.append((NOTE_KEY, self.note))
        return pairs

    @property
    def segments(self) -> list[str]:
        """The `key=value` segments of `text`, or none without it."""
        if self.text is None:
            return []
        return ATTRIBUTE_SEPARATOR.split(self.text)
