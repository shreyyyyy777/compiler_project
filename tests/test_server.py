from server.main import (
    AnalysisRequest,
    AutomatonRequest,
    SimulationRequest,
    api_analyze,
    api_automaton,
    api_simulate,
)


def test_automaton_rejects_stacked_operators_cleanly():
    result = api_automaton(
        AutomatonRequest(regex="a" + "*" * 1_500, kind="dfa")
    )
    assert result["error_type"] == "syntax"
    assert result["nodes"] == []
    assert result["edges"] == []


def test_minimized_dfa_endpoint_reports_reduction_metadata():
    result = api_automaton(AutomatonRequest(regex="a*", kind="min_dfa"))
    assert result["states_after"] == 2
    assert result["reachable_states_before"] > result["states_after"]
    assert result["dead_state_omitted"] is True
    assert result["states_drawn"] == 1
    assert result["classes"]
    assert all(item["id"].startswith("C") for item in result["classes"])
    assert result["nodes"]


def test_simulation_endpoint_returns_nfa_steps():
    result = api_simulate(SimulationRequest(regex="[a-c]{2}", input="ab", kind="nfa"))
    assert result["matches"] is True
    assert len(result["steps"]) == 3


def test_analysis_endpoint_returns_reproducible_metadata():
    result = api_analyze(AnalysisRequest(regex="a{2,4}", input="aaa", repeats=2))
    assert result["parameters"]["repeats"] == 2
    assert result["result"]["matches"] is True
