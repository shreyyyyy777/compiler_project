class RegexSyntaxError(Exception):
    """Raised for ambiguous or malformed regular expressions.

    Carries the offending character index so callers (API/dashboard) can
    point the user at exactly where the pattern went wrong, instead of
    surfacing a raw traceback.
    """

    def __init__(self, message: str, position: int | None = None):
        self.message = message
        self.position = position
        if position is not None:
            super().__init__(f"{message} (at position {position})")
        else:
            super().__init__(message)


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
