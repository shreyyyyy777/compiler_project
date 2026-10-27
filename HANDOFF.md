# Handoff Notes

This project is being handed off — the original author (Yohann) is no
longer actively working on it. This document is the "read this first"
for whoever picks it up next. It's not a substitute for the
[README](README.md) (setup/run/architecture) or [CONTEXT.md](CONTEXT.md)
(design rationale) — read those too.

## Status: functionally complete for the "basic engine" scope

Everything in the original brief plus the three hardening requirements
is implemented and tested:

- Regex → AST (recursive-descent parser) → NFA (Thompson's construction)
  → DFA (lazy/on-demand subset construction) → MATCH / NO MATCH.
- NFA/DFA state explosion handled via lazy DFA construction with a hard
  state cap.
- Long patterns and long input strings handled in linear time without
  recursion blowing the stack.
- Malformed/ambiguous regex and oversized input rejected cleanly via
  typed errors (`RegexSyntaxError`, `RegexLimitError`) — no raw
  tracebacks reach the API or dashboard.
- A FastAPI backend (`server/`) and a no-build-step HTML/JS dashboard
  (`web/`) with three tabs: Match, Automaton (NFA/DFA graph), Test Suite.

**82 tests pass** (`./.venv/bin/python -m pytest -q`) covering the
parser, NFA construction, lazy DFA, matcher, and the three hardening
requirements specifically (`tests/test_limits.py`).

The dashboard has been manually verified end-to-end in a browser
(match/no-match, error banner for invalid regex, NFA graph, DFA graph,
test suite table all render correctly) as of the last commit.

## What's deliberately out of scope (not bugs)

- No character classes (`[abc]`, `[^abc]`), anchors (`^`/`$`), numeric
  quantifiers (`{m,n}`), or backreferences. The project brief only
  asked for the basic operator set (literals, `.`, `|`, `*`, `+`, `?`,
  grouping, escapes). If a professor/spec now asks for more, start in
  `regex_engine/parser.py` (add AST node types + grammar rules),
  `regex_engine/nfa.py` (add a Thompson's construction case), and
  `regex_engine/dfa.py`/`matcher.py` will generally need no changes
  since they operate on the NFA, not the syntax.
- Safety limits (`MAX_PATTERN_LENGTH`, `MAX_GROUP_NESTING`,
  `MAX_INPUT_LENGTH`, `MAX_DFA_STATES` — see `regex_engine/parser.py`,
  `regex_engine/matcher.py`, `regex_engine/dfa.py`) are conservative
  defaults, not tuned against real load. Adjust if a real use case
  needs bigger patterns/inputs than the defaults allow.
- No auth/rate-limiting on the FastAPI endpoints — it's a local demo
  tool, not deployed anywhere. Don't put this on the open internet
  as-is.
- No CI configured (no `.github/workflows`). Tests are only run
  manually.

## How to pick this back up

```bash
cd shrey   # or wherever this repo is checked out
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python -m pytest -q                              # should show "74 passed"
./.venv/bin/python -m uvicorn server.main:app --reload --port 8008
# open http://127.0.0.1:8008
```

Dependencies are pinned to exact versions in `requirements.txt` (as of
2026-09-16) for reproducibility — bump deliberately, not accidentally.

## Where things live

| Concern | File |
|---|---|
| Parsing / grammar / syntax errors | `regex_engine/parser.py`, `regex_engine/errors.py` |
| NFA construction (Thompson's) | `regex_engine/nfa.py` |
| DFA construction (lazy subset construction) | `regex_engine/dfa.py` |
| Ties it together / public API | `regex_engine/matcher.py` |
| HTTP API | `server/main.py` |
| Predefined valid/invalid/boundary test cases (also feeds the dashboard's Test Suite tab) | `server/test_suite.py` |
| Dashboard UI | `web/index.html`, `web/app.js`, `web/style.css` |
| Tests | `tests/` (one file per engine module, plus `test_limits.py` for the hardening requirements) |

## Repo / ownership

- GitHub: https://github.com/yohannshroff/useless-c (`main` branch)
- No open PRs or branches other than `main` as of handoff.
- No secrets, API keys, or external service dependencies — everything
  runs locally with no network calls.
