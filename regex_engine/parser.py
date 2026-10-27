"""Recursive-descent parser: regex source string -> AST.

Grammar (standard regex precedence, low to high):

    union   := concat ('|' concat)*
    concat  := repeat*
    repeat  := atom ('*' | '+' | '?' | numeric)?
    numeric := '{' integer ('}' | ',' integer? '}')
    atom    := literal | '.' | class | '(' union ')' | '\\' escaped

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
MAX_REPEAT_COUNT = 1_000
MAX_CLASS_CHARACTERS = 4_096

# Characters that may be escaped with a backslash to mean themselves.
ESCAPABLE = set("\\|*+?().[]^${}-")
CLASS_ESCAPABLE = set("\\[]^-")


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


@dataclass(frozen=True)
class CharClass(Node):
    chars: frozenset[str]
    negated: bool = False


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


@dataclass
class Repeat(Node):
    inner: Node
    minimum: int
    maximum: int | None


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
                code="empty_expression",
                hint="Provide an expression on both sides of '|' and inside groups.",
            )
        if len(parts) == 1:
            return parts[0]
        return Concat(parts)

    # repeat := atom ('*' | '+' | '?' | numeric)?
    def parse_repeat(self) -> Node:
        node = self.parse_atom()
        op = self.peek()
        if op in ("*", "+", "?"):
            self.advance()
            if op == "*":
                node = Star(node)
            elif op == "+":
                node = Plus(node)
            else:
                node = Optional(node)
        elif op == "{":
            node = self.parse_numeric_quantifier(node)

        if self.peek() in ("*", "+", "?", "{"):
            raise RegexSyntaxError(
                f"stacked quantifier '{self.peek()}' is not supported",
                self.pos,
                code="stacked_quantifier",
                hint="Apply only one quantifier to each atom or group.",
            )
        return node

    def parse_numeric_quantifier(self, node: Node) -> Node:
        start = self.pos
        self.advance()  # {
        if not (self.peek() and self.peek().isdigit()):
            raise RegexSyntaxError(
                "numeric quantifier requires a lower bound",
                self.pos,
                code="invalid_quantifier",
                hint="Use {m}, {m,n}, or {m,} with decimal integers.",
            )

        minimum = self.parse_integer()
        if self.peek() == "}":
            self.advance()
            maximum: int | None = minimum
        elif self.peek() == ",":
            self.advance()
            maximum = self.parse_integer() if self.peek() and self.peek().isdigit() else None
            if self.peek() != "}":
                raise RegexSyntaxError(
                    "unterminated numeric quantifier - missing closing '}'",
                    self.pos,
                    code="unterminated_quantifier",
                    hint="Use {m}, {m,n}, or {m,}.",
                )
            self.advance()
        elif self.peek() is None:
            raise RegexSyntaxError(
                "unterminated numeric quantifier - missing closing '}'",
                self.pos,
                code="unterminated_quantifier",
                hint="Use {m}, {m,n}, or {m,}.",
            )
        else:
            raise RegexSyntaxError(
                "invalid numeric quantifier",
                self.pos,
                code="invalid_quantifier",
                hint="Use {m}, {m,n}, or {m,}.",
            )

        if maximum is not None and maximum < minimum:
            raise RegexSyntaxError(
                f"numeric quantifier upper bound {maximum} is smaller than lower bound {minimum}",
                start,
                end_position=self.pos - 1,
                code="reversed_quantifier_range",
            )
        largest = minimum if maximum is None else maximum
        if largest > MAX_REPEAT_COUNT:
            raise RegexLimitError(
                f"numeric quantifier exceeds repeat limit {MAX_REPEAT_COUNT}"
            )
        return Repeat(node, minimum, maximum)

    def parse_integer(self) -> int:
        value = 0
        while self.peek() and self.peek().isdigit():
            value = value * 10 + int(self.advance())
            if value > MAX_REPEAT_COUNT:
                raise RegexLimitError(
                    f"numeric quantifier exceeds repeat limit {MAX_REPEAT_COUNT}"
                )
        return value

    def parse_atom(self) -> Node:
        c = self.peek()

        if c is None:
            raise RegexSyntaxError(
                "unexpected end of pattern, expected a character, '.', '(' or an escape",
                self.pos,
            )

        if c == "(":
            opening_pos = self.pos
            self.depth += 1
            if self.depth > MAX_GROUP_NESTING:
                raise RegexLimitError(
                    f"pattern nesting too deep (limit is {MAX_GROUP_NESTING} levels of '(...)')"
                )
            self.advance()
            inner = self.parse_union()
            if self.peek() != ")":
                raise RegexSyntaxError(
                    "unmatched '(' - missing closing ')'",
                    opening_pos,
                    code="unmatched_open_group",
                    hint="Add a closing ')' for this group.",
                )
            self.advance()
            self.depth -= 1
            return inner

        if c == ")":
            raise RegexSyntaxError(
                "unmatched ')' - no matching '(' before it",
                self.pos,
                code="unmatched_close_group",
                hint="Remove this ')' or add a matching '(' before it.",
            )

        if c in ("*", "+", "?", "{"):
            raise RegexSyntaxError(
                f"dangling quantifier '{c}' - nothing before it to repeat",
                self.pos,
                code="dangling_quantifier",
            )

        if c == "}":
            raise RegexSyntaxError(
                "unmatched '}' - escape it as '\\}' to match a literal brace",
                self.pos,
                code="unmatched_quantifier_brace",
            )

        if c == "\\":
            escape_pos = self.pos
            self.advance()
            if self.pos >= self.n:
                raise RegexSyntaxError(
                    "trailing '\\' - pattern ends with an incomplete escape sequence",
                    escape_pos,
                    code="trailing_escape",
                    hint="Add a character after '\\' or remove the backslash.",
                )
            esc = self.advance()
            if esc not in ESCAPABLE:
                raise RegexSyntaxError(
                    f"unknown escape sequence '\\{esc}'",
                    escape_pos,
                    end_position=self.pos - 1,
                    code="unknown_escape",
                    hint="Only regex metacharacters need escaping.",
                )
            return Literal(esc)

        if c == ".":
            self.advance()
            return AnyChar()

        if c == "[":
            return self.parse_class()

        self.advance()
        return Literal(c)

    def parse_class(self) -> Node:
        opening = self.pos
        self.advance()
        negated = self.peek() == "^"
        if negated:
            self.advance()

        chars: set[str] = set()
        while True:
            if self.peek() is None:
                raise RegexSyntaxError(
                    "unterminated character class - missing closing ']'",
                    opening,
                    code="unterminated_character_class",
                    hint="Add ']' or escape '[' as '\\['.",
                )
            if self.peek() == "]":
                if not chars:
                    raise RegexSyntaxError(
                        "empty character class is not allowed",
                        opening,
                        end_position=self.pos,
                        code="empty_character_class",
                    )
                self.advance()
                return CharClass(frozenset(chars), negated)

            range_start, range_start_pos = self.parse_class_character()
            if self.peek() == "-":
                dash_pos = self.pos
                self.advance()
                if self.peek() in (None, "]"):
                    raise RegexSyntaxError(
                        "character range is missing its end",
                        dash_pos,
                        code="invalid_character_range",
                        hint="Escape '-' as '\\-' to match a literal hyphen.",
                    )
                range_end, range_end_pos = self.parse_class_character()
                if ord(range_start) > ord(range_end):
                    raise RegexSyntaxError(
                        f"character range '{range_start}-{range_end}' is descending",
                        range_start_pos,
                        end_position=range_end_pos,
                        code="descending_character_range",
                    )
                range_size = ord(range_end) - ord(range_start) + 1
                if len(chars) + range_size > MAX_CLASS_CHARACTERS:
                    raise RegexLimitError(
                        f"character class expands beyond {MAX_CLASS_CHARACTERS} characters"
                    )
                chars.update(chr(codepoint) for codepoint in range(ord(range_start), ord(range_end) + 1))
            else:
                chars.add(range_start)
                if len(chars) > MAX_CLASS_CHARACTERS:
                    raise RegexLimitError(
                        f"character class expands beyond {MAX_CLASS_CHARACTERS} characters"
                    )

    def parse_class_character(self) -> tuple[str, int]:
        position = self.pos
        char = self.advance()
        if char == "-":
            raise RegexSyntaxError(
                "literal '-' inside a character class must be escaped",
                position,
                code="unescaped_class_hyphen",
                hint="Write '\\-' for a literal hyphen.",
            )
        if char != "\\":
            return char, position
        if self.peek() is None:
            raise RegexSyntaxError(
                "trailing '\\' inside character class",
                position,
                code="trailing_class_escape",
            )
        escaped = self.advance()
        if escaped not in CLASS_ESCAPABLE:
            raise RegexSyntaxError(
                f"unknown character-class escape '\\{escaped}'",
                position,
                end_position=self.pos - 1,
                code="unknown_class_escape",
                hint="Escape only '\\', '[', ']', '^', or '-' inside a class.",
            )
        return escaped, position


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
        raise RegexSyntaxError(
            "unmatched ')' - no matching '(' before it",
            parser.pos,
            code="unmatched_close_group",
        )
    return node
