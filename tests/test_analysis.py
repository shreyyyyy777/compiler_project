from regex_engine.analysis import analyze


def test_analysis_is_bounded_and_self_describing():
    report = analyze("[a-z]{2,4}", "test", repeats=3)
    assert report["procedure_version"] == 1
    assert len(report["workload_sha256"]) == 64
    assert report["parameters"]["warmups"] == 5
    assert report["parameters"]["repeats"] == 3
    assert report["result"]["matches"] is True
    assert report["result"]["nfa_states"] > 0
    assert report["result"]["matching"]["minimum_ns"] <= report["result"]["matching"]["maximum_ns"]
    assert report["result"]["minimization"]["status"] == "complete"
