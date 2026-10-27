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
from regex_engine.parser import parse, Literal as LiteralNode, Concat, Union, Star, Plus, Optional
from regex_engine.nfa import build_nfa, ANY
from regex_engine.dfa import LazyDFA
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
    kind: Literal["nfa", "dfa"] = "dfa"


@app.post("/api/match")
def api_match(req: MatchRequest):
    result = engine_match(req.regex, req.input)
    return asdict(result)


def _collect_alphabet(node) -> set[str]:
    """Iterative (stack-based) walk of the AST to gather every literal
    character used - deliberately not recursive, for the same reason
    the parser/NFA builder avoid recursion on long flat patterns."""
    alphabet: set[str] = set()
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, LiteralNode):
            alphabet.add(n.char)
        elif isinstance(n, Concat):
            stack.extend(n.parts)
        elif isinstance(n, Union):
            stack.extend(n.branches)
        elif isinstance(n, (Star, Plus, Optional)):
            stack.append(n.inner)
    return alphabet


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
            label = "any char" if symbol is ANY else symbol
            for target in targets:
                if target in id_set:
                    edge_labels.setdefault((sid, target), []).append(label)

    edges = [
        {"from": f, "to": t, "label": ",".join(labels)}
        for (f, t), labels in edge_labels.items()
    ]
    return {"nodes": nodes, "edges": edges, "start": nfa.start, "truncated": truncated}


def _build_dfa_graph(node) -> dict:
    alphabet = sorted(_collect_alphabet(node))
    other_symbol = "\x00"  # stands in for "any character not in the pattern"
    symbols = alphabet + [other_symbol]

    nfa = build_nfa(node)
    dfa = LazyDFA(nfa)

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
        for symbol in symbols:
            try:
                nxt = dfa.step(state, symbol)
            except RegexLimitError:
                truncated = True
                continue
            if nxt is None:
                continue
            label = "any other char" if symbol == other_symbol else symbol
            edge_labels.setdefault((state.id, nxt.id), []).append(label)
            if nxt.id not in visited:
                visited.add(nxt.id)
                queue.append(nxt)

    edges = []
    for (f, t), labels in edge_labels.items():
        text = ",".join(labels) if len(labels) <= 8 else f"{len(labels)} symbols"
        edges.append({"from": f, "to": t, "label": text})

    return {"nodes": nodes, "edges": edges, "start": dfa.start.id, "truncated": truncated}


@app.post("/api/automaton")
def api_automaton(req: AutomatonRequest):
    try:
        node = parse(req.regex)
        if req.kind == "nfa":
            return _build_nfa_graph(node)
        return _build_dfa_graph(node)
    except (RegexSyntaxError, RegexLimitError) as e:
        error_type = "syntax" if isinstance(e, RegexSyntaxError) else "limit"
        return {"error": e.message, "error_type": error_type, "nodes": [], "edges": []}


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
