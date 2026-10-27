"""Lazy (on-the-fly) subset construction: NFA -> DFA, one state at a time.

This is the piece that actually prevents NFA/DFA "state explosion". A
classic eager subset construction enumerates the full power set of NFA
states up front - for an n-state NFA that's up to 2^n DFA states, which
is fine for small textbook examples and unusable for real patterns.

`LazyDFA` instead treats each DFA state as a `frozenset` of NFA state ids
and only computes a transition (via epsilon-closure + move) the first
time it is actually needed while matching, caching the result. So the
work and memory used are bounded by the DFA states a given input actually
visits, not by the theoretical worst case - and a hard cap on the number
of cached states turns any remaining pathological pattern into a clean
error instead of unbounded memory growth.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .errors import RegexLimitError
from .nfa import NFA, ANY

MAX_DFA_STATES = 20_000

# All characters that do not occur as literals in a pattern are equivalent:
# only ANY transitions can consume them. Cache that whole character class
# under one key so wildcard-heavy inputs cannot create one entry per distinct
# Unicode character.
OTHER = object()


@dataclass
class DFAState:
    id: int
    nfa_states: frozenset
    is_accept: bool
    # char -> frozenset key of the target DFA state, filled in lazily
    transitions: dict = field(default_factory=dict)


def epsilon_closure(nfa: NFA, start_ids) -> frozenset:
    """Iterative (stack-based) epsilon closure - no recursion, so it is
    safe for NFAs with many states (long/large patterns)."""
    closure = set(start_ids)
    stack = list(start_ids)
    while stack:
        sid = stack.pop()
        for target in nfa.states[sid].epsilon:
            if target not in closure:
                closure.add(target)
                stack.append(target)
    return frozenset(closure)


def move(nfa: NFA, state_ids: frozenset, char: str) -> set:
    result = set()
    for sid in state_ids:
        trans = nfa.states[sid].transitions
        if char in trans:
            result.update(trans[char])
        if ANY in trans:
            result.update(trans[ANY])
    return result


class LazyDFA:
    def __init__(self, nfa: NFA):
        self.nfa = nfa
        self._literal_alphabet = {
            symbol
            for state in nfa.states.values()
            for symbol in state.transitions
            if symbol is not ANY
        }
        self._cache: dict[frozenset, DFAState] = {}
        start_key = epsilon_closure(nfa, {nfa.start})
        self.start = self._register(start_key)

    def _register(self, key: frozenset) -> DFAState:
        state = self._cache.get(key)
        if state is not None:
            return state
        if len(self._cache) >= MAX_DFA_STATES:
            raise RegexLimitError(
                f"pattern too complex to evaluate safely - exceeded "
                f"{MAX_DFA_STATES} distinct DFA states"
            )
        state = DFAState(
            id=len(self._cache),
            nfa_states=key,
            is_accept=self.nfa.accept in key,
        )
        self._cache[key] = state
        return state

    def step(self, state: DFAState, char: str) -> DFAState | None:
        """Return the DFA state reached from `state` on `char`, computing
        and caching the transition the first time it's needed."""
        cache_key = char if char in self._literal_alphabet else OTHER
        target_key = state.transitions.get(cache_key)
        if target_key is None:
            next_ids = move(self.nfa, state.nfa_states, char)
            target_key = epsilon_closure(self.nfa, next_ids) if next_ids else frozenset()
            state.transitions[cache_key] = target_key
        if not target_key:
            return None
        return self._register(target_key)

    @property
    def explored_state_count(self) -> int:
        return len(self._cache)

    def all_states(self):
        """All DFA states materialized so far (for visualization)."""
        return list(self._cache.values())
