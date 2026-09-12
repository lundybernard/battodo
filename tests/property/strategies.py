"""Hypothesis strategies for the task-list grammar `battodo.parser` reads.

Each strategy draws one construct the parser distinguishes, built from
the field vocabulary and the open heading the parser itself declares.
They feed a higher-order suite, outside the coverage and mutation gates.
"""

from typing import NamedTuple

from hypothesis import strategies as st

from battodo.parser import FIELD_NAMES, OPEN_HEADING

# A field value is anything up to the closing bracket.
field_values = st.text(
    alphabet=st.characters(exclude_characters=']\n'),
    max_size=8,
)

# Zero to four fields, each written as the parser's field pattern.
fields = st.lists(
    st.tuples(st.sampled_from(FIELD_NAMES), field_values),
    max_size=4,
).map(
    lambda pairs: ''.join(
        f' [{name}:{value}]'
        for name, value in pairs  # nofmt
    )
)

# A title holds no brackets, so a field never hides inside it.
titles = st.text(
    alphabet=st.characters(exclude_characters='[]\n'),
    min_size=1,
    max_size=16,
).filter(str.strip)

marks = st.sampled_from(' xX')


@st.composite
def task_lines(
    draw: st.DrawFn,
    max_depth: int = 2,
    depth: int | None = None,
    field_run: st.SearchStrategy[str] = fields,
) -> str:
    """One task line: indent, checkbox, title, then fields.

    `depth` fixes the indentation level; the default draws it.
    """
    if depth is None:
        depth = draw(
            st.integers(
                min_value=0,
                max_value=max_depth,
            )
        )
    return f'{"  " * depth}- [{draw(marks)}] {draw(titles)}{draw(field_run)}'


def document(lines: list[str]) -> str:
    """The lines as one list file with a single Open section."""
    return f'{OPEN_HEADING}\n\n' + '\n'.join(lines) + '\n'


# A comment holds one line of title text, so nothing ends it early.
comments = titles.map(lambda text: f'<!-- {text} -->')


def note_line(indent: int, text: str) -> str:
    """One note line: the indent, then the text."""
    return f'{" " * indent}{text}'


# A note is indented text, never a heading and never a comment.
notes = st.builds(
    note_line,
    st.integers(min_value=2, max_value=6),
    titles.filter(lambda text: not text.strip().startswith(('#', '<!--'))),
)


def field_text(name: str, value: str) -> str:
    """One field, written as the parser's field pattern."""
    return f' [{name}:{value}]'


one_field = st.builds(field_text, st.sampled_from(FIELD_NAMES), field_values)

# A subtask carries at least one field, per the schema.
subtask_fields = st.tuples(one_field, fields).map(''.join)

# A checklist item carries no field, per the schema.
no_fields = st.just('')

# Three levels exercise the recursion the schema declares.
MAX_DEPTH = 2


class Node(NamedTuple):
    """One task line, with its note lines and its child nodes.

    `subtask` is the flag the schema gives the node: a child that
    carries at least one field.
    """

    line: str
    notes: list[str]
    children: list['Node']
    subtask: bool


def checklist_nodes(depth: int) -> st.SearchStrategy[Node]:
    """A checklist item at `depth`: no field and no children."""
    return st.builds(
        Node,
        task_lines(depth=depth, field_run=no_fields),
        st.lists(notes, max_size=2),
        st.builds(list),
        st.just(False),
    )


def child_nodes(depth: int) -> st.SearchStrategy[list[Node]]:
    """The children of a task at `depth`.

    A task has subtasks or a checklist, never both, per the schema.
    """
    if depth >= MAX_DEPTH:
        return st.builds(list)
    return st.one_of(
        st.builds(list),
        st.lists(
            task_nodes(depth + 1, subtask_fields, subtask=True),
            min_size=1,
            max_size=3,
        ),
        st.lists(checklist_nodes(depth + 1), min_size=1, max_size=3),
    )


# A note belongs to the task line above it, so the two travel together.
@st.composite
def task_nodes(
    draw: st.DrawFn,
    depth: int = 0,
    field_run: st.SearchStrategy[str] = fields,
    subtask: bool = False,
) -> Node:
    """One task at `depth`: its line, its notes, then its children.

    The caller sets `subtask`, because it chooses the field run.
    """
    line = draw(task_lines(depth=depth, field_run=field_run))
    note_lines = draw(st.lists(notes, max_size=2))
    return Node(line, note_lines, draw(child_nodes(depth)), subtask)


# A list file titles itself, opens the section, and closes it with Done.
@st.composite
def documents(draw: st.DrawFn) -> tuple[str, list[Node]]:
    """A whole list file and the task tree of its open section."""
    blanks = st.lists(st.just(''), max_size=2)
    lines = [f'# {draw(titles)}']
    lines.extend(draw(st.lists(comments, max_size=2)))
    lines.extend(draw(blanks))
    lines.append(OPEN_HEADING)
    lines.extend(draw(blanks))

    def write(node: Node) -> None:
        """Append the node and its subtree, parents before children."""
        lines.append(node.line)
        lines.extend(node.notes)
        for child in node.children:
            write(child)
        # Blank lines mean nothing, so a run may sit after any entry.
        lines.extend(draw(blanks))

    nodes = draw(st.lists(task_nodes(), max_size=6))
    for node in nodes:
        write(node)

    if draw(st.booleans()):
        lines.append('## Done')
        lines.extend(draw(st.lists(task_lines(), max_size=3)))
    return '\n'.join(lines) + '\n', nodes
