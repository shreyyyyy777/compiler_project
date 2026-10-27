import pytest

from regex_engine import match


@pytest.mark.parametrize(
    "pattern, text, expected",
    [
        # From the project brief's worked examples.
        ("a*", "", True),
        ("a*", "a", True),
        ("a*", "aa", True),
        ("a*", "aaa", True),
        ("a*", "ab", False),
        ("a|b", "a", True),
        ("a|b", "b", True),
        ("a|b", "c", False),
        ("a*b", "aaab", True),
        ("a*b", "aaba", False),
        # Additional operators.
        ("a+", "", False),
        ("a+", "aaa", True),
        ("a?", "", True),
        ("a?", "a", True),
        ("a?", "aa", False),
        ("(ab)+", "ababab", True),
        ("(ab)+", "aba", False),
        (".", "x", True),
        (".", "", False),
        ("a.c", "abc", True),
        ("a.c", "ac", False),
        ("", "", True),
        ("", "x", False),
    ],
)
def test_match_examples(pattern, text, expected):
    result = match(pattern, text)
    assert result.matches is expected, result.error


def test_match_reports_dfa_states_explored():
    result = match("a*b", "aaab")
    assert result.matches
    assert result.dfa_states_explored > 0


def test_invalid_regex_reports_syntax_error_not_exception():
    result = match("a(b", "ab")
    assert result.matches is False
    assert result.error_type == "syntax"
    assert result.error is not None


def test_unrecognized_character_in_input_is_clean_no_match():
    result = match("a*b", "aa#b")
    assert result.matches is False
    assert result.error is None  # not an error - just doesn't match


def test_stacked_operators_report_syntax_error_not_recursion_error():
    result = match("a" + "*" * 1_500, "")
    assert result.matches is False
    assert result.error_type == "syntax"
