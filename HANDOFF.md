# Handoff Notes

This project is being handed off — the original author (Yohann) is no
longer actively working on it. This document is the "read this first"
for whoever picks it up next. It's not a substitute for the
[README](README.md) (setup/run/architecture) or [CONTEXT.md](CONTEXT.md)
(design rationale) — read those too.

## Status: V2 upgrades implemented on the verified V1 baseline

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
- Character classes, ranges, negation, and bounded/unbounded numeric
  quantifiers are implemented with explicit expansion budgets.
- Complete DFA construction and partition-refinement minimization are
  available on demand without replacing the safe lazy matching path.
- Deterministic NFA/DFA simulations, reproducible performance analysis,
  and structured syntax diagnostics are available through the API and UI.
- A FastAPI backend (`server/`) and no-build-step HTML/JS dashboard
  (`web/`) expose Match, Simulation, Automaton, Performance, and Test Suite.

The authoritative test count is the output of the current command below;
do not reuse the older 74/82-test counts from historical notes.

The dashboard has been manually verified end-to-end in a browser
(match/no-match, error banner for invalid regex, NFA graph, DFA graph,
test suite table all render correctly) as of the last commit.

## What's deliberately out of scope (not bugs)

- No anchors, capture groups, backreferences, lookaround, shorthand
  classes, mode flags, or substring search.
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
cd /Users/shrey/Documents/compiler/project
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
PYTHONDONTWRITEBYTECODE=1 ./.venv/bin/python -m pytest -q -p no:cacheprovider
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
| Step simulation | `regex_engine/simulation.py` |
| Performance procedure | `regex_engine/analysis.py`, `scripts/benchmark.py` |
| Ties it together / public API | `regex_engine/matcher.py` |
| HTTP API | `server/main.py` |
| Predefined valid/invalid/boundary test cases (also feeds the dashboard's Test Suite tab) | `server/test_suite.py` |
| Dashboard UI | `web/index.html`, `web/app.js`, `web/style.css` |
| Tests | `tests/` (one file per engine module, plus `test_limits.py` for the hardening requirements) |

See `docs/V2_SEMANTICS.md` before changing syntax or budgets.

## Repo / ownership

- GitHub: https://github.com/yohannshroff/useless-c (`main` branch)
- No open PRs or branches other than `main` as of handoff.
- No secrets, API keys, or external service dependencies — everything
  runs locally with no network calls.
