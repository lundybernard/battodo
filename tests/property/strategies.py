"""Hypothesis strategies for the task-list grammar `battodo.parser` reads.

Each strategy draws one construct the parser distinguishes, built from
the field vocabulary and the open heading the parser itself declares.
They feed a higher-order suite, outside the coverage and mutation gates.
"""

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
def task_lines(draw: st.DrawFn, max_depth: int = 2) -> str:
    """One task line: indent, checkbox, title, then fields."""
    depth = draw(
        st.integers(
            min_value=0,
            max_value=max_depth,
        )
    )
    return f'{"  " * depth}- [{draw(marks)}] {draw(titles)}{draw(fields)}'


def document(lines: list[str]) -> str:
    """The lines as one list file with a single Open section."""
    return f'{OPEN_HEADING}\n\n' + '\n'.join(lines) + '\n'


# A comment holds one line of title text, so nothing ends it early.
comments = titles.map(lambda text: f'<!-- {text} -->')

# A note is indented text, never a heading and never a comment.
notes = st.builds(
    lambda indent, text: f'{" " * indent}{text}',
    st.integers(min_value=2, max_value=6),
    titles.filter(lambda text: not text.strip().startswith(('#', '<!--'))),
)


# A note belongs to the task line above it, so the two travel together.
@st.composite
def entries(draw: st.DrawFn) -> tuple[str, list[str]]:
    """One task line and its note lines."""
    return draw(task_lines()), draw(st.lists(notes, max_size=2))


# A list file titles itself, opens the section, and closes it with Done.
@st.composite
def documents(draw: st.DrawFn) -> tuple[str, list[tuple[str, list[str]]]]:
    """A whole list file and the entries of its open section."""
    blanks = st.lists(st.just(''), max_size=2)
    lines = [f'# {draw(titles)}']
    lines.extend(draw(st.lists(comments, max_size=2)))
    lines.extend(draw(blanks))
    lines.append(OPEN_HEADING)
    lines.extend(draw(blanks))

    open_entries = draw(st.lists(entries(), max_size=6))
    for task_line, note_lines in open_entries:
        lines.append(task_line)
        lines.extend(note_lines)
        # Blank lines mean nothing, so a run may sit after any entry.
        lines.extend(draw(blanks))

    if draw(st.booleans()):
        lines.append('## Done')
        lines.extend(draw(st.lists(task_lines(), max_size=3)))
    return '\n'.join(lines) + '\n', open_entries
