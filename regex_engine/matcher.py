"""Top-level entry point: compiles a pattern (parser -> NFA -> lazy DFA)
and runs it against an input string, never raising for bad input -
everything is reported back through `MatchResult`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from threading import RLock

from . import parser as ast_parser
from .nfa import build_nfa, NFA
from .dfa import LazyDFA
from .errors import RegexSyntaxError, RegexLimitError

MAX_INPUT_LENGTH = 2_000_000
MAX_REPORTED_STEPS = 500  # cap the trace returned to callers/UI


@dataclass
class CompiledPattern:
    pattern: str
    ast: ast_parser.Node
    nfa: NFA
    dfa: LazyDFA
    lock: RLock = field(default_factory=RLock, repr=False, compare=False)


@dataclass
class MatchResult:
    matches: bool
    error: str | None = None
    error_type: str | None = None  # "syntax" | "limit" | None
    dfa_states_explored: int = 0
    steps: list = field(default_factory=list)
    steps_truncated: bool = False


@lru_cache(maxsize=256)
def compile_pattern(pattern: str) -> CompiledPattern:
    """Parse + Thompson-construct + wrap in a lazy DFA.

    Raises RegexSyntaxError for ambiguous/malformed patterns and
    RegexLimitError if the pattern itself exceeds a safety limit
    (length or nesting depth). Results are cached per pattern string so
    repeated dashboard queries against the same regex don't redo work.
    """
    node = ast_parser.parse(pattern)
    nfa = build_nfa(node)
    dfa = LazyDFA(nfa)
    return CompiledPattern(pattern=pattern, ast=node, nfa=nfa, dfa=dfa)


def match(pattern: str, text: str) -> MatchResult:
    """Check whether `text` matches `pattern`. Never raises: all failure
    modes (bad regex, oversized input, pattern too complex) come back as
    a `MatchResult` with `matches=False` and an explanatory `error`."""
    try:
        compiled = compile_pattern(pattern)
    except RegexSyntaxError as e:
        return MatchResult(matches=False, error=e.message, error_type="syntax")
    except RegexLimitError as e:
        return MatchResult(matches=False, error=e.message, error_type="limit")

    if len(text) > MAX_INPUT_LENGTH:
        return MatchResult(
            matches=False,
            error=f"input too long ({len(text)} chars, limit is {MAX_INPUT_LENGTH})",
            error_type="limit",
        )

    with compiled.lock:
        dfa = compiled.dfa
        state = dfa.start
        steps = [{"char": None, "dfa_state": state.id, "accept": state.is_accept}]
        truncated = False

        try:
            for ch in text:
                next_state = dfa.step(state, ch)
                if next_state is None:
                    state = None
                    break
                state = next_state
                if len(steps) < MAX_REPORTED_STEPS:
                    steps.append({"char": ch, "dfa_state": state.id, "accept": state.is_accept})
                else:
                    truncated = True
        except RegexLimitError as e:
            return MatchResult(
                matches=False,
                error=e.message,
                error_type="limit",
                dfa_states_explored=dfa.explored_state_count,
                steps=steps,
                steps_truncated=True,
            )

        matches = state is not None and state.is_accept
        return MatchResult(
            matches=matches,
            dfa_states_explored=dfa.explored_state_count,
            steps=steps,
            steps_truncated=truncated,
        )
