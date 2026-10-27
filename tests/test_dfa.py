from regex_engine import parser as p
from regex_engine.nfa import build_nfa
from regex_engine.dfa import LazyDFA


def _dfa(pattern):
    return LazyDFA(build_nfa(p.parse(pattern)))


def test_lazy_dfa_only_materializes_visited_states():
    dfa = _dfa("a*b")
    assert dfa.explored_state_count == 1  # only the start state so far
    state = dfa.start
    for ch in "aaab":
        state = dfa.step(state, ch)
    assert state.is_accept
    # Should have discovered only a handful of states, not 2^n of the NFA.
    assert dfa.explored_state_count < 10


def test_transition_cache_is_reused():
    dfa = _dfa("a*b")
    s1 = dfa.step(dfa.start, "a")
    count_after_first = dfa.explored_state_count
    s2 = dfa.step(dfa.start, "a")
    assert s1 is s2
    assert dfa.explored_state_count == count_after_first  # no new state made


def test_dead_transition_returns_none():
    dfa = _dfa("ab")
    s = dfa.step(dfa.start, "a")
    dead = dfa.step(s, "z")
    assert dead is None


def test_non_literal_characters_share_one_transition_cache_entry():
    dfa = _dfa(".*")
    state = dfa.start
    for codepoint in range(0x1000, 0x1000 + 10_000):
        state = dfa.step(state, chr(codepoint))
    assert state is not None and state.is_accept
    assert sum(len(s.transitions) for s in dfa.all_states()) <= 2
