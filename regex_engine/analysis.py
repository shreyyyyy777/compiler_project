"""Reproducible, bounded performance measurements for the engine."""

from __future__ import annotations

import hashlib
import platform
import statistics
import time

from . import parser as ast
from .dfa import LazyDFA, build_minimized_dfa
from .errors import RegexLimitError
from .matcher import MAX_INPUT_LENGTH
from .nfa import build_nfa

DEFAULT_WARMUPS = 5
DEFAULT_REPEATS = 25
MAX_ANALYSIS_REPEATS = 100


def _node_count(root: ast.Node) -> int:
    count = 0
    stack = [root]
    while stack:
        node = stack.pop()
        count += 1
        if isinstance(node, ast.Concat):
            stack.extend(node.parts)
        elif isinstance(node, ast.Union):
            stack.extend(node.branches)
        elif isinstance(node, (ast.Star, ast.Plus, ast.Optional, ast.Repeat)):
            stack.append(node.inner)
    return count


def _run(dfa: LazyDFA, text: str) -> bool:
    state = dfa.start
    for char in text:
        state = dfa.step(state, char)
        if state is None:
            return False
    return state.is_accept


def _summary(samples: list[int]) -> dict:
    ordered = sorted(samples)
    p95_index = min(len(ordered) - 1, (95 * len(ordered) + 99) // 100 - 1)
    return {
        "minimum_ns": ordered[0],
        "median_ns": int(statistics.median(ordered)),
        "p95_ns": ordered[p95_index],
        "maximum_ns": ordered[-1],
    }


def analyze(pattern: str, text: str, repeats: int = DEFAULT_REPEATS) -> dict:
    if not 1 <= repeats <= MAX_ANALYSIS_REPEATS:
        raise RegexLimitError(
            f"analysis repeats must be between 1 and {MAX_ANALYSIS_REPEATS}"
        )
    if len(text) > MAX_INPUT_LENGTH:
        raise RegexLimitError(
            f"input too long ({len(text)} chars, limit is {MAX_INPUT_LENGTH})"
        )

    compile_started = time.perf_counter_ns()
    tree = ast.parse(pattern)
    nfa = build_nfa(tree)
    compile_ns = time.perf_counter_ns() - compile_started

    minimization_started = time.perf_counter_ns()
    try:
        minimized = build_minimized_dfa(nfa)
        minimization = {
            "status": "complete",
            "elapsed_ns": time.perf_counter_ns() - minimization_started,
            "reachable_states_before": sum(
                len(state.original_state_ids) for state in minimized.states
            ),
            "states_after": len(minimized.states),
            "alphabet_classes": len(minimized.classes),
        }
    except RegexLimitError as error:
        minimization = {
            "status": "limit",
            "elapsed_ns": time.perf_counter_ns() - minimization_started,
            "error": error.message,
        }

    dfa = LazyDFA(nfa)
    expected = _run(dfa, text)
    for _ in range(DEFAULT_WARMUPS):
        assert _run(dfa, text) is expected

    samples = []
    for _ in range(repeats):
        started = time.perf_counter_ns()
        actual = _run(dfa, text)
        samples.append(time.perf_counter_ns() - started)
        assert actual is expected

    transition_count = sum(
        len(targets)
        for state in nfa.states.values()
        for targets in state.transitions.values()
    )
    epsilon_count = sum(len(state.epsilon) for state in nfa.states.values())
    checksum = hashlib.sha256((pattern + "\0" + text).encode("utf-8")).hexdigest()
    return {
        "procedure_version": 1,
        "workload_sha256": checksum,
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "parameters": {
            "pattern": pattern,
            "pattern_length": len(pattern),
            "input_length": len(text),
            "warmups": DEFAULT_WARMUPS,
            "repeats": repeats,
            "timer": "time.perf_counter_ns",
            "matching_mode": "warm lazy-DFA cache, full-string match",
        },
        "result": {
            "matches": expected,
            "compile_ns": compile_ns,
            "ast_nodes": _node_count(tree),
            "nfa_states": len(nfa.states),
            "nfa_symbol_transitions": transition_count,
            "nfa_epsilon_transitions": epsilon_count,
            "lazy_dfa_states_explored": dfa.explored_state_count,
            "matching": _summary(samples),
            "minimization": minimization,
        },
    }
