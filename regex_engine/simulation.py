"""Bounded, deterministic step-by-step NFA and DFA simulations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .dfa import LazyDFA, epsilon_closure
from .errors import RegexLimitError, RegexSyntaxError
from .matcher import MAX_INPUT_LENGTH, compile_pattern
from .nfa import symbol_label, symbol_matches

MAX_SIMULATION_STEPS = 500
MAX_TRANSITIONS_PER_STEP = 200


@dataclass
class SimulationResult:
    kind: str
    matches: bool
    steps: list[dict] = field(default_factory=list)
    steps_truncated: bool = False
    dfa_states_explored: int = 0
    error: str | None = None
    error_type: str | None = None
    error_code: str | None = None
    error_position: int | None = None
    error_end_position: int | None = None
    error_hint: str | None = None
    error_context: str | None = None
    error_pointer: str | None = None


def _compile(pattern: str, kind: str):
    try:
        return compile_pattern(pattern), None
    except RegexSyntaxError as error:
        diagnostic = error.diagnostic(pattern)
        return None, SimulationResult(
            kind=kind,
            matches=False,
            error=error.message,
            error_type="syntax",
            error_code=diagnostic.code,
            error_position=diagnostic.position,
            error_end_position=diagnostic.end_position,
            error_hint=diagnostic.hint,
            error_context=diagnostic.context,
            error_pointer=diagnostic.pointer,
        )
    except RegexLimitError as error:
        return None, SimulationResult(
            kind=kind,
            matches=False,
            error=error.message,
            error_type="limit",
        )


def _input_limit(kind: str, text: str) -> SimulationResult | None:
    if len(text) <= MAX_INPUT_LENGTH:
        return None
    return SimulationResult(
        kind=kind,
        matches=False,
        error=f"input too long ({len(text)} chars, limit is {MAX_INPUT_LENGTH})",
        error_type="limit",
    )


def simulate_nfa(pattern: str, text: str) -> SimulationResult:
    if limited := _input_limit("nfa", text):
        return limited
    compiled, error = _compile(pattern, "nfa")
    if error:
        return error
    nfa = compiled.nfa
    active = epsilon_closure(nfa, {nfa.start})
    steps = [
        {
            "index": 0,
            "char": None,
            "before_states": [],
            "move_states": [nfa.start],
            "active_states": sorted(active),
            "transitions": [],
            "transitions_truncated": False,
            "accept": nfa.accept in active,
        }
    ]
    truncated = False
    consumed = 0
    for index, char in enumerate(text):
        moved: set[int] = set()
        transitions = []
        transitions_truncated = False
        for state_id in active:
            for symbol, targets in nfa.states[state_id].transitions.items():
                if not symbol_matches(symbol, char):
                    continue
                moved.update(targets)
                for target in targets:
                    if len(transitions) < MAX_TRANSITIONS_PER_STEP:
                        transitions.append(
                            {
                                "from": state_id,
                                "to": target,
                                "label": symbol_label(symbol),
                            }
                        )
                    else:
                        transitions_truncated = True
        next_active = epsilon_closure(nfa, moved) if moved else frozenset()
        consumed = index + 1
        if len(steps) < MAX_SIMULATION_STEPS:
            steps.append(
                {
                    "index": index + 1,
                    "char": char,
                    "before_states": sorted(active),
                    "move_states": sorted(moved),
                    "active_states": sorted(next_active),
                    "transitions": transitions,
                    "transitions_truncated": transitions_truncated,
                    "accept": nfa.accept in next_active,
                }
            )
        else:
            truncated = True
        active = next_active
        if not active:
            break
    return SimulationResult(
        kind="nfa",
        matches=bool(active) and nfa.accept in active and consumed == len(text),
        steps=steps,
        steps_truncated=truncated,
    )


def simulate_dfa(pattern: str, text: str) -> SimulationResult:
    if limited := _input_limit("dfa", text):
        return limited
    compiled, error = _compile(pattern, "dfa")
    if error:
        return error
    dfa = LazyDFA(compiled.nfa)
    state = dfa.start
    consumed = 0
    steps = [
        {
            "index": 0,
            "char": None,
            "from_state": None,
            "dfa_state": state.id,
            "nfa_states": sorted(state.nfa_states),
            "accept": state.is_accept,
            "dead": False,
        }
    ]
    truncated = False
    try:
        for index, char in enumerate(text):
            previous = state
            state = dfa.step(previous, char)
            consumed = index + 1
            if len(steps) < MAX_SIMULATION_STEPS:
                steps.append(
                    {
                        "index": consumed,
                        "char": char,
                        "from_state": previous.id,
                        "dfa_state": state.id if state else None,
                        "nfa_states": sorted(state.nfa_states) if state else [],
                        "accept": state.is_accept if state else False,
                        "dead": state is None,
                    }
                )
            else:
                truncated = True
            if state is None:
                break
    except RegexLimitError as limit_error:
        return SimulationResult(
            kind="dfa",
            matches=False,
            steps=steps,
            steps_truncated=True,
            dfa_states_explored=dfa.explored_state_count,
            error=limit_error.message,
            error_type="limit",
        )
    return SimulationResult(
        kind="dfa",
        matches=state is not None and state.is_accept and consumed == len(text),
        steps=steps,
        steps_truncated=truncated,
        dfa_states_explored=dfa.explored_state_count,
    )


def simulate(pattern: str, text: str, kind: str = "dfa") -> SimulationResult:
    if kind == "nfa":
        return simulate_nfa(pattern, text)
    if kind == "dfa":
        return simulate_dfa(pattern, text)
    raise ValueError("kind must be 'nfa' or 'dfa'")


def simulate_as_dict(pattern: str, text: str, kind: str = "dfa") -> dict:
    return asdict(simulate(pattern, text, kind))
