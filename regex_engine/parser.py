"""Recursive-descent parser: regex source string -> AST.

Grammar (standard regex precedence, low to high):

    union   := concat ('|' concat)*
    concat  := repeat*
    repeat  := atom ('*' | '+' | '?')*
    atom    := literal | '.' | '(' union ')' | '\\' escaped

Concatenation and alternation are parsed with loops (not left/right
recursion), so a very long *flat* pattern (e.g. 50,000 literals in a row)
never grows the Python call stack. The only thing that recurses is explicit
`(...)` grouping, and that nesting depth is capped so a pathologically
deep pattern fails with a clear error instead of a stack overflow.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .errors import RegexSyntaxError, RegexLimitError

MAX_PATTERN_LENGTH = 20_000
MAX_GROUP_NESTING = 200

# Characters that may be escaped with a backslash to mean themselves.
ESCAPABLE = set("\\|*+?().[]^$")


# ---------------------------------------------------------------------------
# AST
# ---------------------------------------------------------------------------

class Node:
    """Base class for AST nodes."""


@dataclass
class Empty(Node):
    """Matches only the empty string."""


@dataclass
class Literal(Node):
    char: str


@dataclass
class AnyChar(Node):
    """The `.` wildcard: matches any single character."""


@dataclass
class Concat(Node):
    parts: list[Node] = field(default_factory=list)


@dataclass
class Union(Node):
    branches: list[Node] = field(default_factory=list)


@dataclass
class Star(Node):
    inner: Node


@dataclass
class Plus(Node):
    inner: Node


@dataclass
class Optional(Node):
    inner: Node


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class _Parser:
    def __init__(self, pattern: str):
        self.pattern = pattern
        self.pos = 0
        self.n = len(pattern)
        self.depth = 0

    def peek(self) -> str | None:
        return self.pattern[self.pos] if self.pos < self.n else None

    def advance(self) -> str:
        c = self.pattern[self.pos]
        self.pos += 1
        return c

    # union := concat ('|' concat)*
    def parse_union(self) -> Node:
        branches = [self.parse_concat()]
        while self.peek() == "|":
            self.advance()
            branches.append(self.parse_concat())
        if len(branches) == 1:
            return branches[0]
        return Union(branches)

    # concat := repeat+   (stops at '|', ')', or end of input)
    #
    # A concat must produce at least one atom - reaching '|', ')' or end
    # of input with nothing parsed means an empty alternation branch, an
    # empty group `()`, or a trailing `|`, all of which are treated as
    # ambiguous/invalid rather than silently matching the empty string.
    # (A *fully* empty top-level pattern `""` is handled separately in
    # `parse()` before the parser ever gets here, so it stays valid.)
    def parse_concat(self) -> Node:
        parts: list[Node] = []
        while self.peek() is not None and self.peek() not in ("|", ")"):
            parts.append(self.parse_repeat())
        if not parts:
            raise RegexSyntaxError(
                "empty expression - expected a pattern here (empty alternation "
                "branch, empty group, or trailing '|')",
                self.pos,
            )
        if len(parts) == 1:
            return parts[0]
        return Concat(parts)

    # repeat := atom ('*' | '+' | '?')?
    def parse_repeat(self) -> Node:
        node = self.parse_atom()
        if self.peek() in ("*", "+", "?"):
            op = self.advance()
            if op == "*":
                node = Star(node)
            elif op == "+":
                node = Plus(node)
            else:
                node = Optional(node)
            if self.peek() in ("*", "+", "?"):
                raise RegexSyntaxError(
                    f"stacked operator '{self.peek()}' is not supported",
                    self.pos,
                )
        return node

    def parse_atom(self) -> Node:
        c = self.peek()

        if c is None:
            raise RegexSyntaxError(
                "unexpected end of pattern, expected a character, '.', '(' or an escape",
                self.pos,
            )

        if c == "(":
            self.depth += 1
            if self.depth > MAX_GROUP_NESTING:
                raise RegexLimitError(
                    f"pattern nesting too deep (limit is {MAX_GROUP_NESTING} levels of '(...)')"
                )
            self.advance()
            inner = self.parse_union()
            if self.peek() != ")":
                raise RegexSyntaxError("unmatched '(' - missing closing ')'", self.pos)
            self.advance()
            self.depth -= 1
            return inner

        if c == ")":
            raise RegexSyntaxError("unmatched ')' - no matching '(' before it", self.pos)

        if c in ("*", "+", "?"):
            raise RegexSyntaxError(
                f"dangling operator '{c}' - nothing before it to repeat", self.pos
            )

        if c == "\\":
            escape_pos = self.pos
            self.advance()
            if self.pos >= self.n:
                raise RegexSyntaxError(
                    "trailing '\\' - pattern ends with an incomplete escape sequence",
                    escape_pos,
                )
            esc = self.advance()
            if esc not in ESCAPABLE:
                raise RegexSyntaxError(
                    f"unknown escape sequence '\\{esc}'", escape_pos
                )
            return Literal(esc)

        if c == ".":
            self.advance()
            return AnyChar()

        self.advance()
        return Literal(c)


def parse(pattern: str) -> Node:
    """Parse `pattern` into an AST.

    Raises:
        RegexSyntaxError: for ambiguous/malformed syntax (unmatched
            parens, dangling operators, bad escapes, ...).
        RegexLimitError: if the pattern is longer than MAX_PATTERN_LENGTH
            or nests groups deeper than MAX_GROUP_NESTING.
    """
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise RegexLimitError(
            f"pattern too long ({len(pattern)} chars, limit is {MAX_PATTERN_LENGTH})"
        )

    if pattern == "":
        # A fully empty pattern is valid and matches only the empty
        # string. Anything else that bottoms out empty (empty alternation
        # branch, empty group, trailing '|') is rejected in parse_concat.
        return Empty()

    parser = _Parser(pattern)
    node = parser.parse_union()
    if parser.pos != parser.n:
        # Leftover input can only be a stray ')' at this point.
        raise RegexSyntaxError("unmatched ')' - no matching '(' before it", parser.pos)
    return node
