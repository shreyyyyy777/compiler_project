from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SyntaxDiagnostic:
    message: str
    code: str
    position: int | None
    end_position: int | None
    hint: str | None
    context: str | None
    pointer: str | None


class RegexSyntaxError(Exception):
    """Raised for ambiguous or malformed regular expressions.

    Carries the offending character index so callers (API/dashboard) can
    point the user at exactly where the pattern went wrong, instead of
    surfacing a raw traceback.
    """

    def __init__(
        self,
        message: str,
        position: int | None = None,
        *,
        end_position: int | None = None,
        code: str = "invalid_syntax",
        hint: str | None = None,
    ):
        self.message = message
        self.position = position
        self.end_position = end_position if end_position is not None else position
        self.code = code
        self.hint = hint
        if position is not None:
            super().__init__(f"{message} (at position {position})")
        else:
            super().__init__(message)

    def diagnostic(self, pattern: str, *, radius: int = 28) -> SyntaxDiagnostic:
        if self.position is None:
            return SyntaxDiagnostic(
                self.message, self.code, None, None, self.hint, None, None
            )

        start = max(0, self.position - radius)
        stop_at = max(self.position + 1, (self.end_position or self.position) + 1)
        stop = min(len(pattern), stop_at + radius)
        context = pattern[start:stop]
        pointer_start = self.position - start
        pointer_end = max(pointer_start + 1, (self.end_position or self.position) - start + 1)
        pointer = " " * pointer_start + "^" * max(1, pointer_end - pointer_start)
        return SyntaxDiagnostic(
            self.message,
            self.code,
            self.position,
            self.end_position,
            self.hint,
            context,
            pointer,
        )


class RegexLimitError(Exception):
    """Raised when a pattern or input exceeds a safety limit.

    Used for anything that could otherwise blow up resource usage: regex
    nesting too deep, pattern/input longer than the configured maximum, or
    the lazy DFA state cache growing past its cap. This is the graceful
    alternative to letting Python's recursion limit or memory blow up.
    """

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)
