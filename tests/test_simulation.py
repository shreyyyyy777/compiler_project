from regex_engine.simulation import simulate_dfa, simulate_nfa


def test_nfa_simulation_reports_epsilon_closures_and_transitions():
    result = simulate_nfa("a(b|c){1,2}", "abc")
    assert result.matches is True
    assert len(result.steps) == 4
    assert result.steps[0]["char"] is None
    assert result.steps[-1]["accept"] is True
    assert all("active_states" in step for step in result.steps)
    assert any(step["transitions"] for step in result.steps[1:])


def test_dfa_simulation_is_deterministic_and_shows_subset_states():
    first = simulate_dfa("[ab]*c", "abbc")
    second = simulate_dfa("[ab]*c", "abbc")
    assert first.matches is True
    assert first.steps == second.steps
    assert first.steps[-1]["accept"] is True
    assert first.steps[1]["from_state"] == 0
    assert first.dfa_states_explored > 0


def test_simulation_reports_dead_transition():
    result = simulate_dfa("ab", "ax")
    assert result.matches is False
    assert result.steps[-1]["dead"] is True


def test_simulation_returns_structured_syntax_diagnostic():
    result = simulate_nfa("[z-a]", "z")
    assert result.error_type == "syntax"
    assert result.error_code == "descending_character_range"
    assert result.error_pointer
