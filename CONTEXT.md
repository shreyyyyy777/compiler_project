# Engineering Context

Background and rationale for anyone (human or AI assistant) continuing
this codebase — the "why", not the "what". For status/setup/file map see
[HANDOFF.md](HANDOFF.md); for architecture/usage see [README.md](README.md).

## Design decisions and why they were made

- **Lazy DFA instead of eager subset construction**
  (`regex_engine/dfa.py`). An eager NFA→DFA conversion enumerates the
  full power set of NFA states up front (up to 2^n for an n-state NFA).
  `LazyDFA` computes a transition only the first time it's actually
  needed during matching and caches it by `frozenset` key, so cost is
  bounded by states actually visited, not the theoretical worst case.
  `MAX_DFA_STATES` is a backstop for patterns that still discover many
  distinct states along a single input (e.g. wide alternation over many
  optional literals).

- **Loops, not recursion, for concat/alternation chains**
  (`regex_engine/parser.py`, `regex_engine/nfa.py`). A regex like
  `"a" * 50000` must not blow the Python call stack. Only explicit
  `(...)` grouping recurses, and that's capped by `MAX_GROUP_NESTING`.
  If you add a new AST node type that can appear in a long flat
  sequence, keep this property — don't fold it into recursive
  concat/union parsing.

- **Two error types, never a bare exception** (`regex_engine/errors.py`).
  `RegexSyntaxError` = the pattern itself is ambiguous/malformed.
  `RegexLimitError` = the pattern or input is valid but exceeds a safety
  limit. `matcher.match()` catches both and returns a `MatchResult`
  instead of raising, so the API layer never needs its own try/except
  around the engine. If you add a new failure mode, reuse one of these
  two types rather than inventing a third — callers pattern-match on
  `error_type` (`"syntax" | "limit" | None`).

- **`compile_pattern()` is `functools.lru_cache`'d**
  (`regex_engine/matcher.py`). Each cached `CompiledPattern` owns a
  `LazyDFA` whose internal state cache grows across calls (that's the
  point — repeated dashboard queries against the same regex reuse
  discovered DFA states). Don't assume `compile_pattern(p)` returns a
  fresh/empty DFA each call; tests that need a clean `LazyDFA` construct
  one directly (see `tests/test_dfa.py`) instead of going through
  `compile_pattern`.

- **Safety limits are conservative defaults, not measured tuning.**
  `MAX_PATTERN_LENGTH` (20,000), `MAX_GROUP_NESTING` (200),
  `MAX_INPUT_LENGTH` (2,000,000), `MAX_DFA_STATES` (20,000). Chosen to
  be generous for a course-project demo while still bounding worst-case
  memory/CPU. If you raise them, re-run `tests/test_limits.py` — a few
  tests there temporarily shrink `MAX_DFA_STATES` via monkeypatching
  (`dfa_mod.MAX_DFA_STATES = ...`) to keep the explosion test fast; they
  restore it in a `finally` block.

- **No character classes / anchors / backreferences.** Out of scope by
  the original project brief (basic operator set only: literals, `.`,
  `|`, `*`, `+`, `?`, grouping, escapes). See HANDOFF.md for where to
  add them if scope grows.

- **Plain HTML/JS dashboard, no build step** (`web/`). Chosen so the
  whole project runs with just a Python venv — no npm/node dependency.
  The automaton graph (`web/app.js`) is a hand-rolled SVG layout (BFS
  layering + quadratic-bezier edges), not a charting library. If the
  graphs need to get fancier, that's the place to swap in a real
  layout/graph library — it wasn't a deliberate constraint, just the
  simplest thing that worked for a course demo.

## Conventions

- No docstrings/comments explaining *what* code does — names should
  carry that. Comments exist only where they explain *why* (see
  `dfa.py`, `parser.py` module docstrings for examples of the level of
  detail expected).
- Dataclasses for AST nodes (`regex_engine/parser.py`) and NFA/DFA state
  (`regex_engine/nfa.py`, `regex_engine/dfa.py`) — equality/repr come
  free, which the parser tests rely on (`p.parse("a") == p.Literal("a")`).
- Every engine module has a matching `tests/test_*.py`. Keep that 1:1
  mapping if you add a new module.

## Known rough edges

- The DFA visualization endpoint (`_build_dfa_graph` in `server/main.py`)
  re-derives the alphabet from the AST and does its own bounded BFS
  separate from `LazyDFA`'s matching path — it's correct but is a
  second traversal implementation. If matching and visualization ever
  disagree, this is the first place to check.
- `server/test_suite.py`'s `CASES` list is hand-maintained and feeds
  both the dashboard's Test Suite tab and (indirectly) review/demo
  evidence — if you change matcher behavior, check whether any case's
  `expected` value needs updating too.
