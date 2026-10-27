"""Lazy (on-the-fly) subset construction: NFA -> DFA, one state at a time.

This is the piece that actually prevents NFA/DFA "state explosion". A
classic eager subset construction enumerates the full power set of NFA
states up front - for an n-state NFA that's up to 2^n DFA states, which
is fine for small textbook examples and unusable for real patterns.

`LazyDFA` instead treats each DFA state as a `frozenset` of NFA state ids
and only computes a transition (via epsilon-closure + move) the first
time it is actually needed while matching, caching the result. So the
work and memory used are bounded by the DFA states a given input actually
visits, not by the theoretical worst case - and a hard cap on the number
of cached states turns any remaining pathological pattern into a clean
error instead of unbounded memory growth.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .errors import RegexLimitError
from .nfa import NFA, ANY, CharSet, symbol_matches

MAX_DFA_STATES = 20_000

MAX_MINIMIZATION_STATES = 5_000
MAX_MINIMIZATION_CLASSES = 2_048


@dataclass
class DFAState:
    id: int
    nfa_states: frozenset
    is_accept: bool
    # char -> frozenset key of the target DFA state, filled in lazily
    transitions: dict = field(default_factory=dict)


def epsilon_closure(nfa: NFA, start_ids) -> frozenset:
    """Iterative (stack-based) epsilon closure - no recursion, so it is
    safe for NFAs with many states (long/large patterns)."""
    closure = set(start_ids)
    stack = list(start_ids)
    while stack:
        sid = stack.pop()
        for target in nfa.states[sid].epsilon:
            if target not in closure:
                closure.add(target)
                stack.append(target)
    return frozenset(closure)


def move(nfa: NFA, state_ids: frozenset, char: str) -> set:
    result = set()
    for sid in state_ids:
        trans = nfa.states[sid].transitions
        for symbol, targets in trans.items():
            if symbol_matches(symbol, char):
                result.update(targets)
    return result


def transition_symbols(nfa: NFA) -> frozenset:
    return frozenset(
        symbol
        for state in nfa.states.values()
        for symbol in state.transitions
    )


def character_signature(symbols: frozenset, char: str) -> frozenset:
    return frozenset(symbol for symbol in symbols if symbol_matches(symbol, char))


class LazyDFA:
    def __init__(self, nfa: NFA):
        self.nfa = nfa
        self._symbols = transition_symbols(nfa)
        self._cache: dict[frozenset, DFAState] = {}
        start_key = epsilon_closure(nfa, {nfa.start})
        self.start = self._register(start_key)

    def _register(self, key: frozenset) -> DFAState:
        state = self._cache.get(key)
        if state is not None:
            return state
        if len(self._cache) >= MAX_DFA_STATES:
            raise RegexLimitError(
                f"pattern too complex to evaluate safely - exceeded "
                f"{MAX_DFA_STATES} distinct DFA states"
            )
        state = DFAState(
            id=len(self._cache),
            nfa_states=key,
            is_accept=self.nfa.accept in key,
        )
        self._cache[key] = state
        return state

    def step(self, state: DFAState, char: str) -> DFAState | None:
        """Return the DFA state reached from `state` on `char`, computing
        and caching the transition the first time it's needed."""
        cache_key = character_signature(self._symbols, char)
        if cache_key not in state.transitions:
            next_ids = move(self.nfa, state.nfa_states, char)
            target_key = epsilon_closure(self.nfa, next_ids) if next_ids else frozenset()
            state.transitions[cache_key] = target_key
        else:
            target_key = state.transitions[cache_key]
        if not target_key:
            return None
        return self._register(target_key)

    @property
    def explored_state_count(self) -> int:
        return len(self._cache)

    def all_states(self):
        """All DFA states materialized so far (for visualization)."""
        return list(self._cache.values())


@dataclass(frozen=True)
class InputClass:
    id: int
    signature: frozenset
    representative: str
    label: str


@dataclass
class MinimizedDFAState:
    id: int
    original_state_ids: frozenset[int]
    is_accept: bool
    transitions: dict[int, int] = field(default_factory=dict)


class MinimizedDFA:
    def __init__(self, nfa: NFA, states: list[MinimizedDFAState], start_id: int, classes: list[InputClass]):
        self.nfa = nfa
        self.states = states
        self.start = states[start_id]
        self.classes = classes
        self._symbols = transition_symbols(nfa)
        self._class_by_signature = {item.signature: item.id for item in classes}

    def step(self, state: MinimizedDFAState, char: str) -> MinimizedDFAState:
        class_id = self._class_by_signature[character_signature(self._symbols, char)]
        return self.states[state.transitions[class_id]]


def build_input_classes(nfa: NFA) -> list[InputClass]:
    symbols = transition_symbols(nfa)
    mentioned: set[str] = set()
    for symbol in symbols:
        if isinstance(symbol, str):
            mentioned.add(symbol)
        elif isinstance(symbol, CharSet):
            mentioned.update(symbol.chars)

    candidates = sorted(mentioned)
    other = next(chr(codepoint) for codepoint in range(0x110000) if chr(codepoint) not in mentioned)
    candidates.append(other)

    grouped: dict[frozenset, list[str]] = {}
    for char in candidates:
        grouped.setdefault(character_signature(symbols, char), []).append(char)
    if len(grouped) > MAX_MINIMIZATION_CLASSES:
        raise RegexLimitError(
            f"DFA alphabet has more than {MAX_MINIMIZATION_CLASSES} distinguishable classes"
        )

    classes = []
    for class_id, (signature, chars) in enumerate(grouped.items()):
        includes_other = other in chars
        shown = [char for char in chars if char != other][:8]
        escaped = [repr(char)[1:-1] for char in shown]
        if includes_other:
            label = "any other char" if not escaped else ",".join(escaped) + ", other"
        else:
            label = ",".join(escaped)
            if len(chars) > len(shown):
                label += f", … ({len(chars)} chars)"
        classes.append(InputClass(class_id, signature, chars[0], label))
    return classes


def build_minimized_dfa(nfa: NFA) -> MinimizedDFA:
    classes = build_input_classes(nfa)
    start_key = epsilon_closure(nfa, {nfa.start})
    keys = [start_key]
    ids = {start_key: 0}
    transitions: list[dict[int, int]] = []
    cursor = 0
    while cursor < len(keys):
        key = keys[cursor]
        row: dict[int, int] = {}
        for item in classes:
            targets = move(nfa, key, item.representative)
            target_key = epsilon_closure(nfa, targets) if targets else frozenset()
            if target_key not in ids:
                if len(keys) >= MAX_MINIMIZATION_STATES:
                    raise RegexLimitError(
                        f"DFA minimization exceeds safety limit of {MAX_MINIMIZATION_STATES} states"
                    )
                ids[target_key] = len(keys)
                keys.append(target_key)
            row[item.id] = ids[target_key]
        transitions.append(row)
        cursor += 1

    accepting = {sid for sid, key in enumerate(keys) if nfa.accept in key}
    partitions = [group for group in (accepting, set(range(len(keys))) - accepting) if group]
    changed = True
    while changed:
        changed = False
        part_of = {sid: index for index, group in enumerate(partitions) for sid in group}
        refined: list[set[int]] = []
        for group in partitions:
            buckets: dict[tuple[int, ...], set[int]] = {}
            for sid in group:
                signature = tuple(part_of[transitions[sid][item.id]] for item in classes)
                buckets.setdefault(signature, set()).add(sid)
            refined.extend(buckets.values())
            changed |= len(buckets) > 1
        partitions = refined

    start_partition = next(group for group in partitions if 0 in group)
    ordered = [start_partition] + sorted(
        (group for group in partitions if group is not start_partition),
        key=min,
    )
    minimized_id = {sid: index for index, group in enumerate(ordered) for sid in group}
    states = []
    for new_id, group in enumerate(ordered):
        representative = min(group)
        states.append(
            MinimizedDFAState(
                id=new_id,
                original_state_ids=frozenset(group),
                is_accept=representative in accepting,
                transitions={
                    item.id: minimized_id[transitions[representative][item.id]]
                    for item in classes
                },
            )
        )
    return MinimizedDFA(nfa, states, 0, classes)
