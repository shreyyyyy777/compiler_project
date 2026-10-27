from server.main import AutomatonRequest, api_automaton


def test_automaton_rejects_stacked_operators_cleanly():
    result = api_automaton(
        AutomatonRequest(regex="a" + "*" * 1_500, kind="dfa")
    )
    assert result["error_type"] == "syntax"
    assert result["nodes"] == []
    assert result["edges"] == []
