"""Thompson's construction: AST -> NFA.

Each AST node compiles to a small NFA "fragment" (a start state id and an
accept state id) built out of a constant number of new states and
epsilon-transitions per node. Total NFA size is therefore O(len(pattern))
- Thompson's construction never explodes on its own; it's the naive
NFA -> DFA power-set conversion that can, which is why dfa.py builds the
DFA lazily instead of eagerly enumerating all subsets up front.

Concatenation and alternation fold their (already-compiled) child
fragments in a loop rather than recursing per sibling, so a flat pattern
with many parts (e.g. `abcdefg...` thousands of characters long) adds no
extra call-stack depth beyond the AST's own nesting.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import parser as ast
from .errors import RegexLimitError

# Sentinel transition key used for `.` (matches any single character).
ANY = object()
MAX_NFA_STATES = 50_000

EPSILON = "epsilon"


@dataclass(frozen=True)
class CharSet:
    chars: frozenset[str]
    negated: bool = False


def symbol_matches(symbol, char: str) -> bool:
    if symbol is ANY:
        return True
    if isinstance(symbol, CharSet):
        contains = char in symbol.chars
        return not contains if symbol.negated else contains
    return symbol == char


def symbol_label(symbol) -> str:
    if symbol is ANY:
        return "any char"
    if isinstance(symbol, CharSet):
        prefix = "[^" if symbol.negated else "["
        escaped = "".join(
            "\\" + char if char in "\\]^-" else char
            for char in sorted(symbol.chars)
        )
        if len(escaped) > 24:
            escaped = escaped[:21] + "..."
        return prefix + escaped + "]"
    return symbol


@dataclass
class NFAState:
    id: int
    # symbol -> targets (symbol is a literal, CharSet, or ANY)
    transitions: dict = field(default_factory=dict)
    epsilon: set = field(default_factory=set)

    def add(self, symbol, target: int) -> None:
        self.transitions.setdefault(symbol, set()).add(target)

    def add_epsilon(self, target: int) -> None:
        self.epsilon.add(target)


@dataclass
class NFA:
    states: dict  # id -> NFAState
    start: int
    accept: int

    def new_state(self) -> int:
        sid = len(self.states)
        self.states[sid] = NFAState(sid)
        return sid


@dataclass
class _Fragment:
    start: int
    accept: int


class _Builder:
    def __init__(self):
        self.states: dict[int, NFAState] = {}

    def new_state(self) -> int:
        if len(self.states) >= MAX_NFA_STATES:
            raise RegexLimitError(
                f"expanded NFA exceeds safety limit of {MAX_NFA_STATES} states"
            )
        sid = len(self.states)
        self.states[sid] = NFAState(sid)
        return sid

    def eps(self, src: int, dst: int) -> None:
        self.states[src].add_epsilon(dst)

    def compile(self, node: ast.Node) -> _Fragment:
        if isinstance(node, ast.Empty):
            return self._empty()
        if isinstance(node, ast.Literal):
            return self._literal(node.char)
        if isinstance(node, ast.AnyChar):
            return self._any()
        if isinstance(node, ast.CharClass):
            return self._char_class(node)
        if isinstance(node, ast.Concat):
            return self._concat(node.parts)
        if isinstance(node, ast.Union):
            return self._union(node.branches)
        if isinstance(node, ast.Star):
            return self._star(self.compile(node.inner))
        if isinstance(node, ast.Plus):
            return self._plus(self.compile(node.inner))
        if isinstance(node, ast.Optional):
            return self._optional(self.compile(node.inner))
        if isinstance(node, ast.Repeat):
            return self._repeat(node)
        raise TypeError(f"unknown AST node type: {type(node).__name__}")

    def _empty(self) -> _Fragment:
        s, a = self.new_state(), self.new_state()
        self.eps(s, a)
        return _Fragment(s, a)

    def _literal(self, char: str) -> _Fragment:
        s, a = self.new_state(), self.new_state()
        self.states[s].add(char, a)
        return _Fragment(s, a)

    def _any(self) -> _Fragment:
        s, a = self.new_state(), self.new_state()
        self.states[s].add(ANY, a)
        return _Fragment(s, a)

    def _char_class(self, node: ast.CharClass) -> _Fragment:
        s, a = self.new_state(), self.new_state()
        self.states[s].add(CharSet(node.chars, node.negated), a)
        return _Fragment(s, a)

    def _concat(self, parts: list[ast.Node]) -> _Fragment:
        if not parts:
            return self._empty()
        frag = self.compile(parts[0])
        for part in parts[1:]:
            nxt = self.compile(part)
            self.eps(frag.accept, nxt.start)
            frag = _Fragment(frag.start, nxt.accept)
        return frag

    def _union(self, branches: list[ast.Node]) -> _Fragment:
        s, a = self.new_state(), self.new_state()
        for branch in branches:
            frag = self.compile(branch)
            self.eps(s, frag.start)
            self.eps(frag.accept, a)
        return _Fragment(s, a)

    def _star(self, inner: _Fragment) -> _Fragment:
        s, a = self.new_state(), self.new_state()
        self.eps(s, inner.start)
        self.eps(s, a)
        self.eps(inner.accept, inner.start)
        self.eps(inner.accept, a)
        return _Fragment(s, a)

    def _plus(self, inner: _Fragment) -> _Fragment:
        a = self.new_state()
        self.eps(inner.accept, inner.start)
        self.eps(inner.accept, a)
        return _Fragment(inner.start, a)

    def _optional(self, inner: _Fragment) -> _Fragment:
        s, a = self.new_state(), self.new_state()
        self.eps(s, inner.start)
        self.eps(s, a)
        self.eps(inner.accept, a)
        return _Fragment(s, a)

    def _repeat(self, node: ast.Repeat) -> _Fragment:
        fragments = [self.compile(node.inner) for _ in range(node.minimum)]
        if node.maximum is None:
            fragments.append(self._star(self.compile(node.inner)))
        else:
            fragments.extend(
                self._optional(self.compile(node.inner))
                for _ in range(node.maximum - node.minimum)
            )
        if not fragments:
            return self._empty()
        result = fragments[0]
        for fragment in fragments[1:]:
            self.eps(result.accept, fragment.start)
            result = _Fragment(result.start, fragment.accept)
        return result


def build_nfa(node: ast.Node) -> NFA:
    builder = _Builder()
    frag = builder.compile(node)
    return NFA(states=builder.states, start=frag.start, accept=frag.accept)
