# Regex Matching Engine

A from-scratch regular-expression matcher built for a Compiler Design
course project: **Regex → NFA (Thompson's construction) → DFA (lazy
subset construction) → MATCH / NO MATCH**, plus a browser dashboard for
live demos and testing evidence.

> **Picking this project up from someone else?** Read
> [HANDOFF.md](HANDOFF.md) first — current status, what's out of scope,
> and where everything lives. [CONTEXT.md](CONTEXT.md) has the
> engineering rationale behind the trickier design decisions.

## Why it's structured this way

The basic version of this project (parse a regex, build an NFA, build a
DFA, run it) is well understood but has two classic failure modes, which
this implementation specifically addresses:

1. **NFA/DFA state explosion.** Eagerly converting an NFA to a DFA
   (subset construction) can require up to 2^n DFA states for an
   n-state NFA. `regex_engine/dfa.py`'s `LazyDFA` avoids this by
   building DFA states **on demand**: a transition is only computed
   (via epsilon-closure + move) the first time it's actually needed
   while matching, and the result is cached. Memory/work is bounded by
   the states a given input actually visits, not the theoretical power
   set. A hard cap (`MAX_DFA_STATES`) turns any remaining pathological
   pattern into a clean error instead of unbounded memory growth.
2. **Long regexes / long inputs.** The parser and Thompson's-construction
   builder use loops (not recursion) for concatenation/alternation
   chains, so a very long flat pattern doesn't grow the Python call
   stack; explicit `(...)` nesting is recursion-bounded
   (`MAX_GROUP_NESTING`). Matching walks the input character by
   character through the lazy DFA in linear time with no backtracking.
3. **Ambiguous/invalid regex and invalid input.** The parser never lets a
   raw Python exception escape - malformed patterns (unmatched parens,
   dangling operators, empty alternation branches, bad escapes) raise a
   typed `RegexSyntaxError` with the offending position; oversized
   patterns/inputs raise `RegexLimitError`. `matcher.match()` catches
   both and returns a `MatchResult` with `matches=False` and an
   explanation - callers (including the API) never see a crash.

## Project layout

```
regex_engine/   the engine itself (parser, NFA, lazy DFA, matcher)
tests/          pytest suite (parser, NFA, DFA, matcher, hardening/limit tests)
server/         FastAPI app (match/automaton/test-suite endpoints) + predefined test cases
web/            static dashboard (no build step) served by the API
```

## Commands

### Setup (one-time)

```bash
cd /path/to/yohannshroff-useless-c-81944cc
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

### Run the tests

```bash
cd /path/to/yohannshroff-useless-c-81944cc
./.venv/bin/python -m pytest -q
```

### Run the dashboard

```bash
cd /path/to/yohannshroff-useless-c-81944cc
./.venv/bin/python -m uvicorn server.main:app --reload --port 8008
```

Then open http://127.0.0.1:8008 . Three tabs:

- **Match** - enter a regex and an input string, see MATCH/NO MATCH and
  the step-by-step DFA trace.
- **Automaton** - visualizes the NFA (Thompson's construction) or the
  lazy DFA for the current pattern.
- **Test Suite** - runs a predefined table of valid/invalid/boundary/
  malformed-regex cases and reports pass/fail (useful as review evidence).

## Supported syntax

Literals, `.` (any char), concatenation, `|` (alternation), `*`, `+`,
`?`, grouping `(...)`, and `\` to escape a metacharacter
(`\* \+ \? \| \( \) \. \\ \[ \] \^ \$`). An empty pattern `""` is valid
and matches only the empty string. Each atom may have at most one postfix
operator; stacked operators such as `a**` are rejected as malformed.

## Known limitations

- No character classes (`[abc]`), anchors (`^ $`), or backreferences -
  out of scope for the "basic" engine described in the project brief.
- `MAX_PATTERN_LENGTH` (20,000 chars), `MAX_GROUP_NESTING` (200 levels),
  `MAX_INPUT_LENGTH` (2,000,000 chars) and `MAX_DFA_STATES` (20,000
  cached states) are safety limits, not engine bugs - see
  `regex_engine/parser.py`, `regex_engine/dfa.py` and
  `regex_engine/matcher.py`.
