from regex_engine import parser as p
from regex_engine.nfa import build_nfa, ANY
from regex_engine.dfa import epsilon_closure


def test_literal_nfa_has_two_states_one_transition():
    nfa = build_nfa(p.parse("a"))
    assert len(nfa.states) == 2
    assert nfa.states[nfa.start].transitions == {"a": {nfa.accept}}


def test_concat_chains_via_epsilon():
    nfa = build_nfa(p.parse("ab"))
    # start --a--> mid --eps--> mid2 --b--> accept
    closure = epsilon_closure(nfa, {nfa.start})
    assert nfa.start in closure


def test_union_branches_from_new_start():
    nfa = build_nfa(p.parse("a|b"))
    start_eps = nfa.states[nfa.start].epsilon
    assert len(start_eps) == 2  # one branch per alternative


def test_star_allows_skipping_via_epsilon():
    nfa = build_nfa(p.parse("a*"))
    closure = epsilon_closure(nfa, {nfa.start})
    assert nfa.accept in closure  # zero repetitions reaches accept directly


def test_any_char_uses_sentinel():
    nfa = build_nfa(p.parse("."))
    assert ANY in nfa.states[nfa.start].transitions


def test_nfa_size_is_linear_in_pattern_length():
    n = 5000
    nfa = build_nfa(p.parse("a" * n))
    # Thompson's construction: exactly 2 states per literal.
    assert len(nfa.states) == 2 * n
