"""Predefined valid / invalid / boundary test cases run through the engine
and surfaced on the dashboard's "Test Suite" tab - this table doubles as
the testing evidence the Review 2 guide asks for (valid, invalid,
boundary, and project-specific cases with expected vs. actual results).
"""

from __future__ import annotations

from regex_engine import match

CASES = [
    # -- category, description, pattern, input, expected_match --
    ("valid", "zero repetitions of a*", "a*", "", True),
    ("valid", "several a's for a*", "a*", "aaa", True),
    ("valid", "alternation left branch", "a|b", "a", True),
    ("valid", "alternation right branch", "a|b", "b", True),
    ("valid", "a*b with a run of a's", "a*b", "aaab", True),
    ("valid", "one-or-more with repetition", "(ab)+", "ababab", True),
    ("valid", "optional present", "colou?r", "color", True),
    ("valid", "optional absent", "colou?r", "colour", True),
    ("valid", "wildcard matches any char", "a.c", "abc", True),
    ("invalid", "a*b does not match trailing extra char", "a*b", "aaba", False),
    ("invalid", "alternation rejects unlisted char", "a|b", "c", False),
    ("invalid", "wildcard still needs a char", ".", "", False),
    ("invalid", "character outside pattern's alphabet", "abc", "xyz", False),
    ("boundary", "empty pattern matches only empty string", "", "", True),
    ("boundary", "empty pattern rejects non-empty input", "", "x", False),
    ("boundary", "one-or-more rejects zero repetitions", "a+", "", False),
    ("boundary", "long input against a*", "a*", "a" * 10_000, True),
    ("malformed-regex", "unmatched opening paren", "a(b", "ab", None),
    ("malformed-regex", "unmatched closing paren", "a)b", "ab", None),
    ("malformed-regex", "dangling star", "*a", "a", None),
    ("malformed-regex", "empty alternation branch", "a|", "a", None),
    ("malformed-regex", "trailing backslash", "a\\", "a", None),
    ("malformed-regex", "unknown escape", "\\q", "q", None),
]


def run_test_suite() -> list[dict]:
    """Run every predefined case and report pass/fail.

    For "malformed-regex" cases, expected_match is None and the case
    passes if the engine reports a syntax/limit error (i.e. it *rejected*
    the pattern) instead of matching, and crucially without raising.
    """
    results = []
    for category, description, pattern, text, expected in CASES:
        result = match(pattern, text)
        if expected is None:
            passed = result.error_type is not None
            actual = f"error: {result.error}" if result.error else "matched"
        else:
            passed = result.matches == expected
            actual = "MATCH" if result.matches else "NO MATCH"
        results.append(
            {
                "category": category,
                "description": description,
                "pattern": pattern,
                "input": text if len(text) <= 40 else f"{text[:40]}... ({len(text)} chars)",
                "expected": "MATCH" if expected else ("rejected" if expected is None else "NO MATCH"),
                "actual": actual,
                "passed": passed,
            }
        )
    return results
