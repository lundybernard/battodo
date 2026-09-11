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
