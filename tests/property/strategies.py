"""Hypothesis strategies for the task-list grammar `battodo.parser` reads.

Each strategy draws one construct the parser distinguishes, built from
the field vocabulary and the open heading the parser itself declares.
They feed a higher-order suite, outside the coverage and mutation gates.
Each definition is followed by the definitions it uses, so the file
reads top-down.

Every drawn character is one a UTF-8 file can hold. A list file is read
and written as UTF-8, so a surrogate code point is not a list file that
exists, and a suite that writes what it draws cannot encode one. No
drawn line holds a carriage return: a list file is read in text mode,
where a carriage return ends the line.
"""

from datetime import date
from functools import cached_property
from typing import NamedTuple

from hypothesis import strategies as st

from battodo.parser import FIELD_NAMES, OPEN_HEADING


# `Node` leads the module: the annotations below it name this type, and
# an annotation evaluates at definition time.
class Node(NamedTuple):
    """One task line, with its note lines and its child nodes.

    `subtask` is the flag the schema gives the node: a child that
    carries at least one field.
    """

    line: str
    notes: list[str]
    children: list['Node']
    subtask: bool


class Grammar:
    """The constructs of a list file that no indentation depth changes."""

    @cached_property
    def documents(self) -> st.SearchStrategy[tuple[str, list[Node]]]:
        """A whole list file and the task tree of its open section."""
        return self.draw_document(self)

    # A composite takes `draw` first, so the method is static.
    @staticmethod
    @st.composite
    def draw_document(
        draw: st.DrawFn, grammar: 'Grammar'
    ) -> tuple[str, list[Node]]:
        """Draw a whole list file and the task tree of its open section.

        A list file titles itself, opens the section, and closes it with
        Done.
        """
        lines = [f'# {draw(grammar.titles)}']
        lines.extend(draw(st.lists(grammar.comments, max_size=2)))
        lines.extend(draw(grammar.blank_runs))
        lines.append(OPEN_HEADING)
        lines.extend(draw(grammar.blank_runs))

        nodes = draw(st.lists(Level(0, grammar).nodes, max_size=6))
        for node in nodes:
            grammar.write_node(draw, lines, node)

        if draw(st.booleans()):
            lines.append('## Done')
            lines.extend(draw(st.lists(grammar.task_lines, max_size=3)))
        return '\n'.join(lines) + '\n', nodes

    @cached_property
    def titles(self) -> st.SearchStrategy[str]:
        """A title holds no brackets, so a field never hides inside it."""
        return st.text(
            alphabet=st.characters(
                codec='utf-8',
                exclude_characters='[]\n\r',
            ),
            min_size=1,
            max_size=16,
        ).filter(str.strip)

    @cached_property
    def comments(self) -> st.SearchStrategy[str]:
        """A comment holds one line of title text, so nothing ends it."""
        return self.titles.map(lambda text: f'<!-- {text} -->')

    @cached_property
    def blank_runs(self) -> st.SearchStrategy[list[str]]:
        """Zero to two blank lines.

        Blank lines mean nothing to the parser, so a run may sit after
        any entry.
        """
        return st.lists(st.just(''), max_size=2)

    def write_node(
        self, draw: st.DrawFn, lines: list[str], node: Node
    ) -> None:
        """Append the node, its notes, its subtree, then a blank run.

        Parents come before children.
        """
        lines.append(node.line)
        lines.extend(node.notes)
        for child in node.children:
            self.write_node(draw, lines, child)
        lines.extend(draw(self.blank_runs))

    @cached_property
    def task_lines(self) -> st.SearchStrategy[str]:
        """One task line at any depth the schema allows."""
        return st.integers(
            min_value=0,
            max_value=Level.MAX_DEPTH,
        ).flatmap(lambda depth: Level(depth, self).task_line)

    @cached_property
    def note_runs(self) -> st.SearchStrategy[list[str]]:
        """Zero to two notes, the run one task line carries."""
        return st.lists(self.notes, max_size=2)

    @cached_property
    def marks(self) -> st.SearchStrategy[str]:
        """The checkbox mark: open, or either case of the done mark."""
        return st.sampled_from(' xX')

    @cached_property
    def fields(self) -> st.SearchStrategy[str]:
        """Zero to four fields, each written as the parser's pattern."""
        return st.lists(
            st.tuples(st.sampled_from(FIELD_NAMES), self.field_values),
            max_size=4,
        ).map(
            lambda pairs: ''.join(
                f' [{name}:{value}]'
                for name, value in pairs  # nofmt
            )
        )

    @cached_property
    def subtask_fields(self) -> st.SearchStrategy[str]:
        """A subtask carries at least one field, per the schema."""
        return st.tuples(self.one_field, self.fields).map(''.join)

    @cached_property
    def notes(self) -> st.SearchStrategy[str]:
        """A note is indented text, never a heading and never a comment."""
        return st.builds(
            note_line,
            st.integers(min_value=2, max_value=6),
            self.titles.filter(
                lambda text: not text.strip().startswith(('#', '<!--'))
            ),
        )

    @cached_property
    def field_values(self) -> st.SearchStrategy[str]:
        """A field value is anything up to the closing bracket.

        Text that short seldom spells an ISO date or a whole number, so
        both are drawn apart. A whole number reads as an `LOE` or as a
        `P`, the legacy scale included.
        """
        return st.one_of(
            st.text(
                alphabet=st.characters(
                    codec='utf-8',
                    exclude_characters=']\n\r',
                ),
                max_size=8,
            ),
            st.dates().map(date.isoformat),
            st.integers(min_value=0, max_value=130).map(str),
        )

    @cached_property
    def one_field(self) -> st.SearchStrategy[str]:
        """One field, written as the parser's field pattern."""
        return st.builds(
            field_text,
            st.sampled_from(FIELD_NAMES),
            self.field_values,
        )


class Level:
    """One indentation depth, and every construct the schema puts there."""

    # Three levels exercise the recursion the schema declares.
    MAX_DEPTH: int = 2

    def __init__(self, depth: int, grammar: Grammar) -> None:
        self.depth = depth
        self.grammar = grammar

    @cached_property
    def nodes(self) -> st.SearchStrategy[Node]:
        """A task at this depth: its line, its notes, then its children.

        A note belongs to the task line above it, so the two travel
        together.
        """
        return st.builds(
            Node,
            self.task_line,
            self.grammar.note_runs,
            self.children,
            st.just(False),
        )

    @cached_property
    def task_line(self) -> st.SearchStrategy[str]:
        """One task line at this depth, with zero to four fields."""
        return st.builds(
            task_text,
            self.indent,
            self.grammar.marks,
            self.grammar.titles,
            self.grammar.fields,
        )

    @cached_property
    def children(self) -> st.SearchStrategy[list[Node]]:
        """The children of a task at this depth.

        A task has subtasks or a checklist, never both, per the schema.
        """
        if self.depth >= self.MAX_DEPTH:
            return st.builds(list)
        return st.one_of(
            st.builds(list),
            st.lists(self.below.subtask_nodes, min_size=1, max_size=3),
            st.lists(self.below.checklist_nodes, min_size=1, max_size=3),
        )

    @cached_property
    def indent(self) -> st.SearchStrategy[str]:
        """The two-space indent the schema gives this depth."""
        return st.just('  ' * self.depth)

    @cached_property
    def below(self) -> 'Level':
        """The level one indent deeper than this one."""
        return Level(self.depth + 1, self.grammar)

    @cached_property
    def subtask_nodes(self) -> st.SearchStrategy[Node]:
        """A subtask at this depth: at least one field, per the schema."""
        return st.builds(
            Node,
            self.subtask_line,
            self.grammar.note_runs,
            self.children,
            st.just(True),
        )

    @cached_property
    def checklist_nodes(self) -> st.SearchStrategy[Node]:
        """A checklist item at this depth: no field and no children."""
        return st.builds(
            Node,
            self.checklist_line,
            self.grammar.note_runs,
            st.builds(list),
            st.just(False),
        )

    @cached_property
    def subtask_line(self) -> st.SearchStrategy[str]:
        """One subtask line at this depth, with at least one field."""
        return st.builds(
            task_text,
            self.indent,
            self.grammar.marks,
            self.grammar.titles,
            self.grammar.subtask_fields,
        )

    @cached_property
    def checklist_line(self) -> st.SearchStrategy[str]:
        """One checklist line at this depth, with no field."""
        return st.builds(
            task_text,
            self.indent,
            self.grammar.marks,
            self.grammar.titles,
            st.just(''),
        )


def task_text(indent: str, mark: str, title: str, field_run: str) -> str:
    """One task line: the indent, the checkbox, the title, then fields."""
    return f'{indent}- [{mark}] {title}{field_run}'


def note_line(indent: int, text: str) -> str:
    """One note line: the indent, then the text."""
    return f'{" " * indent}{text}'


def field_text(name: str, value: str) -> str:
    """One field, written as the parser's field pattern."""
    return f' [{name}:{value}]'


def document(lines: list[str]) -> str:
    """The lines as one list file with a single Open section."""
    return f'{OPEN_HEADING}\n\n' + '\n'.join(lines) + '\n'


grammar = Grammar()
