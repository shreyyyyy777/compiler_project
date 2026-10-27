import pytest

from regex_engine import parser as p
from regex_engine.errors import RegexSyntaxError, RegexLimitError


def test_literal():
    assert p.parse("a") == p.Literal("a")


def test_concat():
    node = p.parse("ab")
    assert isinstance(node, p.Concat)
    assert node.parts == [p.Literal("a"), p.Literal("b")]


def test_union():
    node = p.parse("a|b")
    assert isinstance(node, p.Union)
    assert node.branches == [p.Literal("a"), p.Literal("b")]


def test_star_plus_optional():
    assert p.parse("a*") == p.Star(p.Literal("a"))
    assert p.parse("a+") == p.Plus(p.Literal("a"))
    assert p.parse("a?") == p.Optional(p.Literal("a"))


def test_group():
    node = p.parse("(a|b)c")
    assert isinstance(node, p.Concat)
    assert isinstance(node.parts[0], p.Union)


def test_any_char():
    assert p.parse(".") == p.AnyChar()


def test_empty_pattern_is_valid():
    assert p.parse("") == p.Empty()


def test_escaped_metachar():
    assert p.parse(r"\*") == p.Literal("*")
    assert p.parse(r"\(") == p.Literal("(")


@pytest.mark.parametrize(
    "pattern",
    [
        "(a",
        "a)",
        "((a)",
        "*a",
        "a|*b",
        "a|",
        "|a",
        "\\",
        "a\\",
        "\\q",
        "a**",
        "a++",
        "a??",
        "a*+",
    ],
)
def test_invalid_regex_raises_syntax_error(pattern):
    with pytest.raises(RegexSyntaxError):
        p.parse(pattern)


def test_deep_nesting_raises_limit_error():
    pattern = "(" * (p.MAX_GROUP_NESTING + 5) + "a" + ")" * (p.MAX_GROUP_NESTING + 5)
    with pytest.raises(RegexLimitError):
        p.parse(pattern)


def test_too_long_pattern_raises_limit_error():
    with pytest.raises(RegexLimitError):
        p.parse("a" * (p.MAX_PATTERN_LENGTH + 1))


def test_long_flat_pattern_does_not_crash():
    # Many literals in a row must parse without hitting recursion limits.
    pattern = "a" * 10_000
    node = p.parse(pattern)
    assert isinstance(node, p.Concat)
    assert len(node.parts) == 10_000


def test_many_stacked_operators_are_rejected_without_recursion():
    with pytest.raises(RegexSyntaxError):
        p.parse("a" + "*" * 1_500)
