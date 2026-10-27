import itertools
import re

import pytest

from regex_engine import match
from regex_engine import parser as p
from regex_engine.dfa import build_minimized_dfa
from regex_engine.errors import RegexLimitError, RegexSyntaxError
from regex_engine.nfa import build_nfa


@pytest.mark.parametrize(
    "pattern,text,expected",
    [
        ("[abc]+", "cab", True),
        ("[a-c]+", "cab", True),
        ("[^a-c]+", "XYZ", True),
        ("[^a-c]+", "XbZ", False),
        (r"[\]\-\\]+", "]-\\", True),
        ("a{3}", "aaa", True),
        ("a{2,4}", "aa", True),
        ("a{2,4}", "aaaa", True),
        ("a{2,4}", "aaaaa", False),
        ("(ab){2,}", "ababab", True),
        ("a{0}", "", True),
        ("a{0,1}", "a", True),
    ],
)
def test_character_classes_and_numeric_quantifiers(pattern, text, expected):
    result = match(pattern, text)
    assert result.error is None
    assert result.matches is expected


@pytest.mark.parametrize(
    "pattern,code",
    [
        ("[abc", "unterminated_character_class"),
        ("[]", "empty_character_class"),
        ("[z-a]", "descending_character_range"),
        ("a{,3}", "invalid_quantifier"),
        ("a{3,2}", "reversed_quantifier_range"),
        ("a{2", "unterminated_quantifier"),
        ("a{2}*", "stacked_quantifier"),
        ("[-a]", "unescaped_class_hyphen"),
    ],
)
def test_new_syntax_errors_are_typed_and_located(pattern, code):
    with pytest.raises(RegexSyntaxError) as exc_info:
        p.parse(pattern)
    error = exc_info.value
    assert error.code == code
    assert error.position is not None
    assert error.diagnostic(pattern).pointer


def test_numeric_quantifier_budget_is_enforced():
    with pytest.raises(RegexLimitError):
        p.parse(f"a{{{p.MAX_REPEAT_COUNT + 1}}}")
    with pytest.raises(RegexLimitError):
        p.parse("a{" + "9" * 10_000 + "}")


def test_minimization_reduces_redundant_dfa_and_preserves_language():
    minimized = build_minimized_dfa(build_nfa(p.parse("a*")))
    before = sum(len(state.original_state_ids) for state in minimized.states)
    assert before == 3
    assert len(minimized.states) == 2  # accepting loop plus complete dead state
    for text, expected in [("a", True), ("", True), ("aa", True), ("b", False)]:
        state = minimized.start
        for char in text:
            state = minimized.step(state, char)
        assert state.is_accept is expected


def test_character_classes_keep_unicode_wildcard_cache_bounded():
    result = match("[^a]*", "".join(chr(0x1000 + index) for index in range(10_000)))
    assert result.matches is True
    assert result.dfa_states_explored <= 2


def test_v2_syntax_matches_python_fullmatch_on_supported_subset():
    patterns = [
        "[ab]",
        "[^ab]",
        "[a-c]+",
        "[ab]{0}",
        "[ab]{1,2}",
        "a{2,}",
        "(ab){1,3}",
        "[a-c]?x",
        "([ab]|x){2}",
        "[^x]{2,4}",
    ]
    texts = [""] + [
        "".join(chars)
        for length in range(1, 5)
        for chars in itertools.product("abcx", repeat=length)
    ]
    for pattern in patterns:
        for text in texts:
            expected = re.fullmatch(pattern, text) is not None
            result = match(pattern, text)
            assert result.error is None
            assert result.matches is expected, (pattern, text)


def test_minimized_and_lazy_dfas_agree_on_supported_v2_patterns():
    for pattern in ("a*", "[ab]{1,3}", "[^x]*x", "(ab|c){2,}"):
        nfa = build_nfa(p.parse(pattern))
        minimized = build_minimized_dfa(nfa)
        for text in ("", "a", "aa", "ab", "abc", "cc", "abab", "yyx"):
            state = minimized.start
            for char in text:
                state = minimized.step(state, char)
            assert state.is_accept is match(pattern, text).matches
