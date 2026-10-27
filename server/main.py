"""FastAPI backend for the Regex Matching Engine dashboard.

Serves the matching API, an NFA/DFA graph API for the visualization tab,
a predefined test-suite endpoint, and the static dashboard itself.
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from regex_engine import match as engine_match
from regex_engine.errors import RegexLimitError, RegexSyntaxError
from regex_engine.parser import parse
from regex_engine.nfa import build_nfa, symbol_label
from regex_engine.dfa import LazyDFA, build_input_classes, build_minimized_dfa
from regex_engine.simulation import simulate_as_dict
from regex_engine.analysis import analyze, DEFAULT_REPEATS, MAX_ANALYSIS_REPEATS
from server.test_suite import run_test_suite

app = FastAPI(title="Regex Matching Engine")

# Requests carry arbitrarily-sized strings from the browser; cap them at
# the door so a hostile/huge payload never even reaches the engine.
MAX_API_PATTERN_LEN = 20_000
MAX_API_INPUT_LEN = 2_000_000

NFA_RENDER_CAP = 500
DFA_RENDER_CAP = 300


class MatchRequest(BaseModel):
    regex: str = Field(max_length=MAX_API_PATTERN_LEN)
    input: str = Field(max_length=MAX_API_INPUT_LEN)


class AutomatonRequest(BaseModel):
    regex: str = Field(max_length=MAX_API_PATTERN_LEN)
    kind: Literal["nfa", "dfa", "min_dfa"] = "dfa"


class SimulationRequest(BaseModel):
    regex: str = Field(max_length=MAX_API_PATTERN_LEN)
    input: str = Field(max_length=MAX_API_INPUT_LEN)
    kind: Literal["nfa", "dfa"] = "dfa"


class AnalysisRequest(BaseModel):
    regex: str = Field(max_length=MAX_API_PATTERN_LEN)
    input: str = Field(max_length=MAX_API_INPUT_LEN)
    repeats: int = Field(default=DEFAULT_REPEATS, ge=1, le=MAX_ANALYSIS_REPEATS)


@app.post("/api/match")
def api_match(req: MatchRequest):
    result = engine_match(req.regex, req.input)
    return asdict(result)


def _build_nfa_graph(node) -> dict:
    nfa = build_nfa(node)
    ids = sorted(nfa.states.keys())
    truncated = len(ids) > NFA_RENDER_CAP
    if truncated:
        ids = ids[:NFA_RENDER_CAP]
    id_set = set(ids)

    nodes = [{"id": sid, "accept": sid == nfa.accept, "start": sid == nfa.start} for sid in ids]

    edge_labels: dict[tuple[int, int], list[str]] = {}
    for sid in ids:
        state = nfa.states[sid]
        for target in state.epsilon:
            if target in id_set:
                edge_labels.setdefault((sid, target), []).append("ε")  # epsilon
        for symbol, targets in state.transitions.items():
            label = symbol_label(symbol)
            for target in targets:
                if target in id_set:
                    edge_labels.setdefault((sid, target), []).append(label)

    edges = [
        {"from": f, "to": t, "label": ",".join(labels)}
        for (f, t), labels in edge_labels.items()
    ]
    return {"nodes": nodes, "edges": edges, "start": nfa.start, "truncated": truncated}


def _build_dfa_graph(node) -> dict:
    nfa = build_nfa(node)
    dfa = LazyDFA(nfa)
    classes = build_input_classes(nfa)

    nodes = []
    edge_labels: dict[tuple[int, int], list[str]] = {}
    visited = {dfa.start.id}
    queue = deque([dfa.start])
    truncated = False

    while queue:
        if len(visited) > DFA_RENDER_CAP:
            truncated = True
            break
        state = queue.popleft()
        nodes.append({"id": state.id, "accept": state.is_accept, "start": state.id == dfa.start.id})
        for item in classes:
            try:
                nxt = dfa.step(state, item.representative)
            except RegexLimitError:
                truncated = True
                continue
            if nxt is None:
                continue
            edge_labels.setdefault((state.id, nxt.id), []).append(item.label)
            if nxt.id not in visited:
                visited.add(nxt.id)
                queue.append(nxt)

    edges = []
    for (f, t), labels in edge_labels.items():
        text = ",".join(labels) if len(labels) <= 8 else f"{len(labels)} symbols"
        edges.append({"from": f, "to": t, "label": text})

    return {"nodes": nodes, "edges": edges, "start": dfa.start.id, "truncated": truncated}


def _build_minimized_dfa_graph(node) -> dict:
    nfa = build_nfa(node)
    dfa = build_minimized_dfa(nfa)
    drawable_states = [state for state in dfa.states if not state.is_dead]
    nodes = [
        {
            "id": state.id,
            "accept": state.is_accept,
            "start": state.id == dfa.start.id,
        }
        for state in drawable_states[:DFA_RENDER_CAP]
    ]
    visible = {node["id"] for node in nodes}
    edge_labels: dict[tuple[int, int], list[str]] = {}
    for state in drawable_states[:DFA_RENDER_CAP]:
        for item in dfa.classes:
            target = state.transitions[item.id]
            if target in visible:
                edge_labels.setdefault((state.id, target), []).append(f"C{item.id}")
    edges = [
        {
            "from": source,
            "to": target,
            "label": ",".join(labels) if len(labels) <= 5 else f"{len(labels)} input classes",
        }
        for (source, target), labels in edge_labels.items()
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "start": dfa.start.id,
        "truncated": len(drawable_states) > DFA_RENDER_CAP,
        "reachable_states_before": sum(
            len(state.original_state_ids) for state in dfa.states
        ),
        "states_after": len(dfa.states),
        "states_drawn": len(nodes),
        "dead_state_omitted": any(state.is_dead for state in dfa.states),
        "classes": [
            {"id": f"C{item.id}", "label": item.label}
            for item in dfa.classes
        ],
    }


@app.post("/api/automaton")
def api_automaton(req: AutomatonRequest):
    try:
        node = parse(req.regex)
        if req.kind == "nfa":
            return _build_nfa_graph(node)
        if req.kind == "min_dfa":
            return _build_minimized_dfa_graph(node)
        return _build_dfa_graph(node)
    except (RegexSyntaxError, RegexLimitError) as e:
        error_type = "syntax" if isinstance(e, RegexSyntaxError) else "limit"
        payload = {"error": e.message, "error_type": error_type, "nodes": [], "edges": []}
        if isinstance(e, RegexSyntaxError):
            payload.update(asdict(e.diagnostic(req.regex)))
        return payload


@app.post("/api/simulate")
def api_simulate(req: SimulationRequest):
    return simulate_as_dict(req.regex, req.input, req.kind)


@app.post("/api/analyze")
def api_analyze(req: AnalysisRequest):
    try:
        return analyze(req.regex, req.input, req.repeats)
    except RegexSyntaxError as error:
        return {
            "error": error.message,
            "error_type": "syntax",
            **asdict(error.diagnostic(req.regex)),
        }
    except RegexLimitError as error:
        return {"error": error.message, "error_type": "limit"}


@app.get("/api/tests")
def api_tests():
    results = run_test_suite()
    return {
        "results": results,
        "passed": sum(1 for r in results if r["passed"]),
        "total": len(results),
    }


WEB_DIR = Path(__file__).resolve().parent.parent / "web"
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="dashboard")
